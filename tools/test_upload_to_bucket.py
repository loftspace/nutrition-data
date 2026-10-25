"""Tests for tools/upload_to_bucket.py. Run: python -m unittest discover -s tools -v

No network: uploads go through a fake opener that records the requests.
"""
import gzip
import hashlib
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
import upload_to_bucket as up  # noqa: E402


def make_db(path, db_version='2026.10.25', schema_version='2', variant='full'):
    db = sqlite3.connect(path)
    db.execute('create table meta (key text primary key, value text)')
    db.executemany('insert into meta values (?, ?)', [
        ('db_version', db_version), ('schema_version', schema_version), ('variant', variant)])
    db.commit()
    db.close()


def sha(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def make_out(tmp, full_version='2026.10.25', open_version='2026.10.25', checksums=True):
    """Builds an out/ folder shaped like the one release-db.yml leaves behind."""
    for name, version, variant in (('products.sqlite', full_version, 'full'),
                                   ('products-open.sqlite', open_version, 'open')):
        raw = os.path.join(tmp, name)
        make_db(raw, version, '2', variant)
        with open(raw, 'rb') as src, gzip.open(raw + '.gz', 'wb') as dst:
            dst.write(src.read())
    if checksums:
        lines = []
        for name in ('products.sqlite', 'products-open.sqlite', 'products.sqlite.gz', 'products-open.sqlite.gz'):
            lines.append('%s  out/%s' % (sha(os.path.join(tmp, name)), name))
        with open(os.path.join(tmp, 'checksums.txt'), 'w', newline='\n') as f:
            f.write('\n'.join(lines) + '\n')
    return tmp


class FakeResponse:
    status = 200

    def __init__(self, body=b'{"Key": "x"}'):
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeOpener:
    def __init__(self):
        self.requests = []

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        return FakeResponse()


class TestNaming(unittest.TestCase):
    def test_versioned_path(self):
        self.assertEqual(up.versioned_path('2026.10.25', 'products.sqlite.gz'), 'db-2026.10.25/products.sqlite.gz')

    def test_db_version_must_be_a_date_version(self):
        for ok in ('2026.10.25', '2026.10.25.2'):
            up.check_db_version(ok)
        for bad in ('', '2026-10-25', '../x', '2026.10.25/..', 'latest', '2026.1.5'):
            with self.assertRaises(ValueError, msg=bad):
                up.check_db_version(bad)

    def test_plan_order_puts_latest_json_last(self):
        plan = up.upload_plan('2026.10.25')
        paths = [p for p, _ in plan]
        self.assertEqual(paths, [
            'db-2026.10.25/products.sqlite.gz',
            'db-2026.10.25/products-open.sqlite.gz',
            'db-2026.10.25/checksums.txt',
            'products.sqlite.gz',
            'products-open.sqlite.gz',
            'checksums.txt',
            'latest.json',
        ])

    def test_object_url(self):
        self.assertEqual(up.object_url('https://abc.supabase.co/', 'products', 'db-2026.10.25/checksums.txt'),
                         'https://abc.supabase.co/storage/v1/object/products/db-2026.10.25/checksums.txt')


class TestLatest(unittest.TestCase):
    def setUp(self):
        self.tmp = make_out(tempfile.mkdtemp())

    def test_latest_json_has_versions_paths_and_sha256(self):
        latest = up.build_latest(self.tmp)
        self.assertEqual(latest['db_version'], '2026.10.25')
        self.assertEqual(latest['schema_version'], 2)
        files = latest['files']
        self.assertEqual(sorted(files), ['checksums.txt', 'products-open.sqlite.gz', 'products.sqlite.gz'])
        full = files['products.sqlite.gz']
        self.assertEqual(full['path'], 'db-2026.10.25/products.sqlite.gz')
        self.assertEqual(full['sha256'], sha(os.path.join(self.tmp, 'products.sqlite.gz')))
        self.assertEqual(full['sha256_uncompressed'], sha(os.path.join(self.tmp, 'products.sqlite')))
        self.assertEqual(full['bytes'], os.path.getsize(os.path.join(self.tmp, 'products.sqlite.gz')))
        self.assertEqual(full['variant'], 'full')
        self.assertEqual(files['products-open.sqlite.gz']['variant'], 'open')
        self.assertEqual(files['checksums.txt']['sha256'], sha(os.path.join(self.tmp, 'checksums.txt')))
        self.assertNotIn('sha256_uncompressed', files['checksums.txt'])

    def test_db_version_argument_must_match_the_files(self):
        self.assertEqual(up.build_latest(self.tmp, expect_db_version='2026.10.25')['db_version'], '2026.10.25')
        with self.assertRaises(ValueError):
            up.build_latest(self.tmp, expect_db_version='2026.10.26')

    def test_variants_with_different_db_versions_fail(self):
        tmp = make_out(tempfile.mkdtemp(), open_version='2026.10.24')
        with self.assertRaises(ValueError):
            up.build_latest(tmp)

    def test_checksums_txt_must_agree_with_the_files(self):
        with open(os.path.join(self.tmp, 'checksums.txt'), 'a', newline='\n') as f:
            f.write('%s  out/products.sqlite.gz\n' % ('0' * 64))
        with self.assertRaises(ValueError):
            up.build_latest(self.tmp)

    def test_missing_file_fails(self):
        os.remove(os.path.join(self.tmp, 'products-open.sqlite.gz'))
        with self.assertRaises(FileNotFoundError):
            up.build_latest(self.tmp)

    def test_missing_schema_version_is_an_error_not_a_default(self):
        tmp = tempfile.mkdtemp()
        make_out(tmp)
        raw = os.path.join(tmp, 'products.sqlite')
        db = sqlite3.connect(raw)
        db.execute("delete from meta where key = 'schema_version'")
        db.commit()
        db.close()
        with open(raw, 'rb') as src, gzip.open(raw + '.gz', 'wb') as dst:
            dst.write(src.read())
        os.remove(os.path.join(tmp, 'checksums.txt'))
        with self.assertRaises(ValueError):
            up.build_latest(tmp)


class TestUpload(unittest.TestCase):
    def setUp(self):
        self.tmp = make_out(tempfile.mkdtemp())
        self.key = 'test-service-key-not-real'

    def run_main(self, argv, env, opener):
        out = io.StringIO()
        with redirect_stdout(out):
            code = up.main(argv, env=env, opener=opener)
        return code, out.getvalue()

    def test_dry_run_needs_no_key_and_sends_nothing(self):
        opener = FakeOpener()
        code, out = self.run_main(['--dir', self.tmp, '--dry-run'], {}, opener)
        self.assertEqual(code, 0)
        self.assertEqual(opener.requests, [])
        self.assertIn('db-2026.10.25/products.sqlite.gz', out)
        self.assertIn('latest.json', out)

    def test_missing_key_fails_before_any_request(self):
        opener = FakeOpener()
        with self.assertRaises(SystemExit):
            self.run_main(['--dir', self.tmp], {'SUPABASE_URL': 'https://abc.supabase.co'}, opener)
        self.assertEqual(opener.requests, [])

    def test_upload_upserts_every_object_and_never_prints_the_key(self):
        opener = FakeOpener()
        env = {'SUPABASE_URL': 'https://abc.supabase.co', 'SUPABASE_SERVICE_ROLE_KEY': self.key}
        code, out = self.run_main(['--dir', self.tmp, '--db-version', '2026.10.25'], env, opener)
        self.assertEqual(code, 0)
        self.assertNotIn(self.key, out)
        urls = [r.full_url for r in opener.requests]
        self.assertEqual(urls[0], 'https://abc.supabase.co/storage/v1/object/products/db-2026.10.25/products.sqlite.gz')
        self.assertEqual(urls[-1], 'https://abc.supabase.co/storage/v1/object/products/latest.json')
        self.assertEqual(len(urls), 7)
        for r in opener.requests:
            self.assertEqual(r.get_method(), 'POST')
            self.assertEqual(r.get_header('X-upsert'), 'true')
            self.assertEqual(r.get_header('Authorization'), 'Bearer ' + self.key)
            self.assertEqual(r.get_header('Apikey'), self.key)
        latest = json.loads(opener.requests[-1].data)
        self.assertEqual(latest['db_version'], '2026.10.25')
        self.assertEqual(opener.requests[-1].get_header('Content-type'), 'application/json')
        self.assertEqual(opener.requests[-1].get_header('Cache-control'), 'no-cache')
        with open(os.path.join(self.tmp, 'products.sqlite.gz'), 'rb') as f:
            self.assertEqual(opener.requests[0].data, f.read())

    def test_file_over_the_bucket_limit_fails_before_any_request(self):
        opener = FakeOpener()
        env = {'SUPABASE_URL': 'https://abc.supabase.co', 'SUPABASE_SERVICE_ROLE_KEY': self.key}
        old = up.MAX_BYTES
        up.MAX_BYTES = 10
        try:
            with self.assertRaises(SystemExit):
                self.run_main(['--dir', self.tmp], env, opener)
        finally:
            up.MAX_BYTES = old
        self.assertEqual(opener.requests, [])


if __name__ == '__main__':
    unittest.main()
