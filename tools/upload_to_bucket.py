"""Upload the slim product databases to the private Supabase Storage bucket "products".

Used by .github/workflows/release-db.yml and from Max's machine. Standard library only.

Reads products.sqlite.gz, products-open.sqlite.gz and checksums.txt from --dir, takes
db_version and schema_version from the files' own meta table, checks every sha256 against
checksums.txt, then uploads (upsert, so a newer file replaces an older one):

    db-<db_version>/products.sqlite.gz        kept per version
    db-<db_version>/products-open.sqlite.gz
    db-<db_version>/checksums.txt
    products.sqlite.gz                        always the newest
    products-open.sqlite.gz
    checksums.txt
    latest.json                               uploaded last: db_version, schema_version, sha256 of each file

The service role key is read from the SUPABASE_SERVICE_ROLE_KEY environment variable and the
project URL from SUPABASE_URL (or --url). The key is never read from a file and never printed.

    python tools/upload_to_bucket.py --dir out --dry-run
    python tools/upload_to_bucket.py --dir out --db-version 2026.10.25
"""
import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import urllib.error
import urllib.request

BUCKET = 'products'
# The bucket's file_size_limit (Makro supabase/migrations/20261018120000_products_bucket.sql).
MAX_BYTES = 52428800
DB_FILES = (('products.sqlite.gz', 'full'), ('products-open.sqlite.gz', 'open'))
CHECKSUMS = 'checksums.txt'
LATEST = 'latest.json'
CONTENT_TYPES = {'.gz': 'application/gzip', '.txt': 'text/plain; charset=utf-8', '.json': 'application/json'}
DB_VERSION_RE = re.compile(r'^\d{4}\.\d{2}\.\d{2}(\.\d+)?$')
KEY_ENV = 'SUPABASE_SERVICE_ROLE_KEY'
URL_ENV = 'SUPABASE_URL'


def check_db_version(v):
    if not isinstance(v, str) or not DB_VERSION_RE.match(v):
        raise ValueError('db_version must look like 2026.10.25 (optionally .N), got %r' % (v,))
    return v


def versioned_path(db_version, name):
    return 'db-%s/%s' % (check_db_version(db_version), name)


def upload_plan(db_version):
    """(object path, local file name) in upload order. latest.json goes last, so it only
    points at a version once every file of that version is in the bucket."""
    names = [n for n, _ in DB_FILES] + [CHECKSUMS]
    plan = [(versioned_path(db_version, n), n) for n in names]
    plan += [(n, n) for n in names]
    plan.append((LATEST, LATEST))
    return plan


def object_url(base_url, bucket, path):
    return '%s/storage/v1/object/%s/%s' % (base_url.rstrip('/'), bucket, path)


def sha256_file(path, opener=open):
    h = hashlib.sha256()
    with opener(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def read_meta(gz_path):
    """The meta table of a gzipped products database, as a dict."""
    fd, tmp = tempfile.mkstemp(suffix='.sqlite')
    os.close(fd)
    try:
        with gzip.open(gz_path, 'rb') as src, open(tmp, 'wb') as dst:
            shutil.copyfileobj(src, dst)
        db = sqlite3.connect('file:%s?mode=ro' % tmp, uri=True)
        try:
            return dict(db.execute('select key, value from meta'))
        finally:
            db.close()
    finally:
        os.remove(tmp)


def read_checksums(path):
    """checksums.txt as a list of (file name, sha256). `sha256sum` output, paths reduced to the name."""
    out = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            digest, name = line.split(None, 1)
            out.append((os.path.basename(name.lstrip('*')), digest.lower()))
    return out


def build_latest(directory, expect_db_version=None):
    """Checks the files in `directory` and returns the latest.json content."""
    files = {}
    versions = set()
    schemas = set()
    for name, variant in DB_FILES:
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        meta = read_meta(path)
        for key in ('db_version', 'schema_version'):
            if not meta.get(key):
                raise ValueError('%s has no %s in its meta table' % (name, key))
        if meta.get('variant') not in (None, variant):
            raise ValueError('%s says variant %r, expected %r' % (name, meta['variant'], variant))
        versions.add(meta['db_version'])
        schemas.add(meta['schema_version'])
        files[name] = {
            'path': None,
            'variant': variant,
            'bytes': os.path.getsize(path),
            'sha256': sha256_file(path),
            'sha256_uncompressed': sha256_file(path, gzip.open),
        }
    if len(versions) != 1 or len(schemas) != 1:
        raise ValueError('the two variants disagree: db_version %s, schema_version %s'
                         % (sorted(versions), sorted(schemas)))
    db_version = check_db_version(versions.pop())
    schema_version = int(schemas.pop())
    if expect_db_version is not None and expect_db_version != db_version:
        raise ValueError('--db-version %s does not match the files (%s)' % (expect_db_version, db_version))

    checksums_path = os.path.join(directory, CHECKSUMS)
    if not os.path.isfile(checksums_path):
        raise FileNotFoundError(checksums_path)
    known = {}
    for name, info in files.items():
        known[name] = info['sha256']
        known[name[:-len('.gz')]] = info['sha256_uncompressed']
    listed = read_checksums(checksums_path)
    for name, digest in listed:
        if name in known and known[name] != digest:
            raise ValueError('checksums.txt says %s is %s, the file is %s' % (name, digest, known[name]))
    missing = [n for n in files if n not in {name for name, _ in listed}]
    if missing:
        raise ValueError('checksums.txt does not list %s' % ', '.join(missing))
    files[CHECKSUMS] = {
        'path': None,
        'bytes': os.path.getsize(checksums_path),
        'sha256': sha256_file(checksums_path),
    }
    for name in files:
        files[name]['path'] = versioned_path(db_version, name)
    return {'db_version': db_version, 'schema_version': schema_version, 'files': files}


def content_type(name):
    return CONTENT_TYPES.get(os.path.splitext(name)[1], 'application/octet-stream')


def upload(base_url, key, path, body, ctype, opener, cache_control):
    req = urllib.request.Request(object_url(base_url, BUCKET, path), data=body, method='POST')
    req.add_header('Authorization', 'Bearer ' + key)
    req.add_header('apikey', key)
    req.add_header('x-upsert', 'true')
    req.add_header('Content-Type', ctype)
    req.add_header('Cache-Control', cache_control)
    try:
        with opener(req, timeout=300) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode('utf-8', 'replace')[:500]
        raise SystemExit('upload of %s failed: HTTP %s %s' % (path, e.code, detail))


def main(argv=None, env=None, opener=None):
    env = os.environ if env is None else env
    opener = urllib.request.urlopen if opener is None else opener
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--dir', required=True, help='folder with the .gz files and checksums.txt')
    ap.add_argument('--db-version', help='fail unless the files carry this db_version')
    ap.add_argument('--url', help='project URL, default $%s' % URL_ENV)
    ap.add_argument('--dry-run', action='store_true', help='check the files and print the plan, upload nothing')
    a = ap.parse_args(argv)
    if a.db_version is not None:
        check_db_version(a.db_version)

    latest = build_latest(a.dir, a.db_version)
    body_latest = (json.dumps(latest, indent=2, sort_keys=True) + '\n').encode('utf-8')
    for name, info in latest['files'].items():
        if info['bytes'] > MAX_BYTES:
            raise SystemExit('%s is %d bytes, over the bucket limit of %d' % (name, info['bytes'], MAX_BYTES))

    plan = upload_plan(latest['db_version'])
    print('db_version %s, schema_version %d' % (latest['db_version'], latest['schema_version']))
    if a.dry_run:
        for path, name in plan:
            print('would upload %s -> %s/%s' % (name, BUCKET, path))
        print(body_latest.decode('utf-8'), end='')
        return 0

    base_url = a.url or env.get(URL_ENV)
    key = env.get(KEY_ENV)
    if not base_url:
        raise SystemExit('set %s or pass --url' % URL_ENV)
    if not key:
        raise SystemExit('set the %s environment variable (never put it in a file)' % KEY_ENV)

    for path, name in plan:
        if name == LATEST:
            body = body_latest
        else:
            with open(os.path.join(a.dir, name), 'rb') as f:
                body = f.read()
        # no-cache everywhere: a re-run of the same db_version replaces the files, and the app checks sha256.
        upload(base_url, key, path, body, content_type(name), opener, 'no-cache')
        print('uploaded %s -> %s/%s (%d bytes)' % (name, BUCKET, path, len(body)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
