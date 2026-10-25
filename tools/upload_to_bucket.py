"""Upload the slim product databases to the private Supabase Storage bucket "products".

Used by .github/workflows/release-db.yml and from Max's machine. Standard library only.

Reads products.sqlite.gz, products-open.sqlite.gz and checksums.txt from --dir, takes
db_version and schema_version from the files' own meta table, checks every sha256 against
checksums.txt, then uploads:

    db-<db_version>/products.sqlite.gz        written once, never replaced
    db-<db_version>/products-open.sqlite.gz
    db-<db_version>/checksums.txt
    products.sqlite.gz                        upsert: always the newest
    products-open.sqlite.gz
    checksums.txt
    latest.json                               upsert, uploaded last: db_version, schema_version, sha256 of each file

A db-<db_version>/ object that already exists is left alone when its sha256 matches and is an
error when it does not, so a rebuilt file can never change a published version. A db_version
older than the one in the bucket's latest.json is refused unless --force is given. Only
latest.json points at a consistent set; the root files are replaced one by one.

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
# products-db.md: YYYY.MM.DD, with -2, -3 for a second build the same day.
DB_VERSION_RE = re.compile(r'^(\d{4})\.(\d{2})\.(\d{2})(?:-(\d+))?$')
# The oldest schema the Makro clients read (products-db.md v1 is schema_version 2).
MIN_SCHEMA_VERSION = 2
ALL_CHECKSUM_NAMES = ('products.sqlite', 'products-open.sqlite', 'products.sqlite.gz', 'products-open.sqlite.gz')
KEY_ENV = 'SUPABASE_SERVICE_ROLE_KEY'
URL_ENV = 'SUPABASE_URL'


def check_db_version(v):
    if not isinstance(v, str) or not DB_VERSION_RE.match(v):
        raise ValueError('db_version must look like 2026.10.25 or 2026.10.25-2, got %r' % (v,))
    return v


def version_key(v):
    """Sort key for a db_version: the date, then the build of that day (no suffix is build 1)."""
    y, m, d, n = DB_VERSION_RE.match(check_db_version(v)).groups()
    return (int(y), int(m), int(d), int(n) if n else 1)


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
    if schema_version < MIN_SCHEMA_VERSION:
        raise ValueError('schema_version %d is older than %d, which the clients need'
                         % (schema_version, MIN_SCHEMA_VERSION))
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
    missing = [n for n in ALL_CHECKSUM_NAMES if n not in {name for name, _ in listed}]
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


def send(opener, req, key):
    """Runs a request and returns (status, body). HTTP errors come back as a status, with the key
    blanked out of the body; network errors stop the script."""
    try:
        with opener(req, timeout=300) as resp:
            return getattr(resp, 'status', 200), resp.read()
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read().replace(key.encode('utf-8'), b'***')
        finally:
            e.close()
    except urllib.error.URLError as e:
        raise SystemExit('%s %s failed: %s' % (req.get_method(), req.full_url, e.reason))


def is_not_found(status, body):
    # Supabase Storage answers a missing object with 404, or 400 and statusCode "404" in the body.
    return status == 404 or (status == 400 and (b'"404"' in body or b'not_found' in body))


def is_duplicate(status, body):
    # The same for an existing object without x-upsert: 409, or 400 and statusCode "409".
    return status == 409 or (status == 400 and (b'"409"' in body or b'Duplicate' in body))


def request(base_url, key, method, path, body=None, headers=()):
    req = urllib.request.Request(object_url(base_url, BUCKET, path), data=body, method=method)
    req.add_header('Authorization', 'Bearer ' + key)
    req.add_header('apikey', key)
    for k, v in headers:
        req.add_header(k, v)
    return req


def fail(what, path, status, body):
    raise SystemExit('%s of %s failed: HTTP %s %s' % (what, path, status, body.decode('utf-8', 'replace')[:500]))


def download(base_url, key, path, opener):
    """The object's bytes, or None when it does not exist."""
    status, body = send(opener, request(base_url, key, 'GET', path), key)
    if is_not_found(status, body):
        return None
    if status >= 300:
        fail('download', path, status, body)
    return body


def upload(base_url, key, path, body, ctype, opener, upsert):
    """Uploads one object. Without upsert an existing object is kept if it has the same bytes
    and is an error if it does not. Returns 'uploaded' or 'unchanged'."""
    req = request(base_url, key, 'POST', path, body, [
        ('x-upsert', 'true' if upsert else 'false'),
        ('Content-Type', ctype),
        # no-cache everywhere: the root objects change, and the app checks sha256.
        ('Cache-Control', 'no-cache'),
    ])
    status, resp = send(opener, req, key)
    if status < 300:
        return 'uploaded'
    if not upsert and is_duplicate(status, resp):
        existing = download(base_url, key, path, opener)
        if existing is not None and hashlib.sha256(existing).digest() == hashlib.sha256(body).digest():
            return 'unchanged'
        raise SystemExit('%s/%s already exists with different content; a published db_version is never '
                         'replaced, build a new one (for example %s-2)' % (BUCKET, path, path.split('/')[0][3:]))
    fail('upload', path, status, resp)


def main(argv=None, env=None, opener=None):
    env = os.environ if env is None else env
    opener = urllib.request.urlopen if opener is None else opener
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--dir', required=True, help='folder with the .gz files and checksums.txt')
    ap.add_argument('--db-version', help='fail unless the files carry this db_version')
    ap.add_argument('--url', help='project URL, default $%s' % URL_ENV)
    ap.add_argument('--dry-run', action='store_true', help='check the files and print the plan, upload nothing')
    ap.add_argument('--force', action='store_true',
                    help='allow a db_version older than the one latest.json in the bucket points at')
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

    current = download(base_url, key, LATEST, opener)
    if current is not None:
        try:
            current_version = json.loads(current.decode('utf-8'))['db_version']
            older = version_key(latest['db_version']) < version_key(current_version)
        except (ValueError, KeyError, TypeError):
            raise SystemExit('the bucket has a latest.json this script cannot read; check it by hand')
        if older and not a.force:
            raise SystemExit('the bucket already points at db_version %s, newer than %s; pass --force to go back'
                             % (current_version, latest['db_version']))

    for path, name in plan:
        if name == LATEST:
            body = body_latest
        else:
            with open(os.path.join(a.dir, name), 'rb') as f:
                body = f.read()
        upsert = not path.startswith('db-')
        result = upload(base_url, key, path, body, content_type(name), opener, upsert)
        print('%s %s -> %s/%s (%d bytes)' % (result, name, BUCKET, path, len(body)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
