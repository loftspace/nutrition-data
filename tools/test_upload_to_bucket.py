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
import urllib.error
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


ALL_FOUR = ('products.sqlite', 'products-open.sqlite', 'products.sqlite.gz', 'products-open.sqlite.gz')


def make_out(tmp, full_version='2026.10.25', open_version='2026.10.25', checksums=True, schema_version='2',
             checksum_names=ALL_FOUR, extra_meta=None):
    """Builds an out/ folder shaped like the one release-db.yml leaves behind."""
    for name, version, variant in (('products.sqlite', full_version, 'full'),
                                   ('products-open.sqlite', open_version, 'open')):
        raw = os.path.join(tmp, name)
        make_db(raw, version, schema_version, variant)
        if extra_meta:
            db = sqlite3.connect(raw)
            db.executemany('insert into meta values (?, ?)', extra_meta)
            db.commit()
            db.close()
        with open(raw, 'rb') as src, gzip.open(raw + '.gz', 'wb') as dst:
            dst.write(src.read())
    if checksums:
        lines = []
        for name in checksum_names:
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


def http_error(req, code, body):
    return urllib.error.HTTPError(req.full_url, code, 'error', {}, io.BytesIO(body))


class FakeOpener:
    """A fake Storage API. `store` maps object path to bytes. POST without x-upsert on an existing
    object answers 409, like Supabase; GET of a missing object answers 400 with statusCode 404."""
    PREFIX = '/storage/v1/object/products/'

    def __init__(self, store=None, fail_with=None):
        self.requests = []
        self.store = {} if store is None else store
        self.fail_with = fail_with

    def posts(self):
        return [r for r in self.requests if r.get_method() == 'POST']

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        path = req.full_url.split(self.PREFIX, 1)[1]
        if req.get_method() == 'GET':
            if path not in self.store:
                raise http_error(req, 400, b'{"statusCode":"404","error":"not_found","message":"Object not found"}')
            return FakeResponse(self.store[path])
        if self.fail_with:
            raise http_error(req, *self.fail_with)
        if path in self.store and req.get_header('X-upsert') != 'true':
            raise http_error(req, 409, b'{"statusCode":"409","error":"Duplicate","message":"The resource already exists"}')
        self.store[path] = req.data
        return FakeResponse()


class TestNaming(unittest.TestCase):
    def test_versioned_path(self):
        self.assertEqual(up.versioned_path('2026.10.25', 'products.sqlite.gz'), 'db-2026.10.25/products.sqlite.gz')

    def test_db_version_must_be_a_date_version(self):
        # products-db.md: YYYY.MM.DD, with -2, -3 for a second build the same day.
        for ok in ('2026.10.25', '2026.10.25-2', '2026.10.25-13'):
            up.check_db_version(ok)
        for bad in ('', '2026-10-25', '../x', '2026.10.25/..', 'latest', '2026.1.5', '2026.10.25.2', '2026.10.25-'):
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

    def test_versions_order_by_date_then_build_number(self):
        order = ['2026.10.24', '2026.10.25', '2026.10.25-2', '2026.10.25-10', '2026.11.01']
        keys = [up.version_key(v) for v in order]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(len(set(keys)), len(keys))

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

    def test_checksums_txt_must_list_all_four_files(self):
        for dropped in ALL_FOUR:
            tmp = make_out(tempfile.mkdtemp(), checksum_names=[n for n in ALL_FOUR if n != dropped])
            with self.assertRaises(ValueError, msg=dropped):
                up.build_latest(tmp)

    def test_schema_version_below_2_fails(self):
        tmp = make_out(tempfile.mkdtemp(), schema_version='1')
        with self.assertRaises(ValueError):
            up.build_latest(tmp)

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

    def env(self):
        return {'SUPABASE_URL': 'https://abc.supabase.co', 'SUPABASE_SERVICE_ROLE_KEY': self.key}

    def test_dry_run_still_checks_the_db_version(self):
        opener = FakeOpener()
        with self.assertRaises(ValueError):
            self.run_main(['--dir', self.tmp, '--dry-run', '--db-version', '2026.10.26'], {}, opener)
        self.assertEqual(opener.requests, [])

    def test_upload_sends_every_object_and_never_prints_the_key(self):
        opener = FakeOpener()
        code, out = self.run_main(['--dir', self.tmp, '--db-version', '2026.10.25'], self.env(), opener)
        self.assertEqual(code, 0)
        self.assertNotIn(self.key, out)
        posts = opener.posts()
        urls = [r.full_url for r in posts]
        self.assertEqual(urls[0], 'https://abc.supabase.co/storage/v1/object/products/db-2026.10.25/products.sqlite.gz')
        self.assertEqual(urls[-1], 'https://abc.supabase.co/storage/v1/object/products/latest.json')
        self.assertEqual(len(urls), 7)
        for r in opener.requests:
            self.assertEqual(r.get_header('Authorization'), 'Bearer ' + self.key)
            self.assertEqual(r.get_header('Apikey'), self.key)
        latest = json.loads(posts[-1].data)
        self.assertEqual(latest['db_version'], '2026.10.25')
        self.assertEqual(posts[-1].get_header('Content-type'), 'application/json')
        self.assertEqual(posts[-1].get_header('Cache-control'), 'no-cache')
        with open(os.path.join(self.tmp, 'products.sqlite.gz'), 'rb') as f:
            self.assertEqual(posts[0].data, f.read())

    def test_dash_n_db_version_uploads_under_its_own_folder(self):
        tmp = make_out(tempfile.mkdtemp(), full_version='2026.10.25-2', open_version='2026.10.25-2')
        opener = FakeOpener()
        code, _ = self.run_main(['--dir', tmp, '--db-version', '2026.10.25-2'], self.env(), opener)
        self.assertEqual(code, 0)
        self.assertIn('db-2026.10.25-2/products.sqlite.gz', opener.store)

    def test_versioned_objects_are_never_overwritten_root_objects_are(self):
        opener = FakeOpener()
        self.run_main(['--dir', self.tmp], self.env(), opener)
        for r in opener.posts():
            path = r.full_url.split(FakeOpener.PREFIX, 1)[1]
            expected = 'false' if path.startswith('db-') else 'true'
            self.assertEqual(r.get_header('X-upsert'), expected, path)

    def test_rerun_with_identical_files_succeeds(self):
        opener = FakeOpener()
        self.run_main(['--dir', self.tmp], self.env(), opener)
        code, _ = self.run_main(['--dir', self.tmp], self.env(), opener)
        self.assertEqual(code, 0)

    def test_rerun_with_a_rebuilt_file_for_the_same_version_fails(self):
        opener = FakeOpener()
        self.run_main(['--dir', self.tmp], self.env(), opener)
        before = dict(opener.store)
        rebuilt = make_out(tempfile.mkdtemp(), extra_meta=[('built_at', 'later')])
        with self.assertRaises(SystemExit):
            self.run_main(['--dir', rebuilt], self.env(), opener)
        self.assertEqual(opener.store, before)

    def test_older_db_version_than_the_bucket_is_refused(self):
        newer = make_out(tempfile.mkdtemp(), full_version='2026.10.25-2', open_version='2026.10.25-2')
        opener = FakeOpener()
        self.run_main(['--dir', newer], self.env(), opener)
        latest_before = opener.store['latest.json']
        n = len(opener.requests)
        with self.assertRaises(SystemExit):
            self.run_main(['--dir', self.tmp], self.env(), opener)
        self.assertEqual([r.get_method() for r in opener.requests[n:]], ['GET'])
        self.assertEqual(opener.store['latest.json'], latest_before)
        code, _ = self.run_main(['--dir', self.tmp, '--force'], self.env(), opener)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(opener.store['latest.json'])['db_version'], '2026.10.25')

    def test_http_error_exits_without_echoing_the_key(self):
        body = ('{"message":"bad key %s"}' % self.key).encode('utf-8')
        opener = FakeOpener(fail_with=(403, body))
        with self.assertRaises(SystemExit) as cm:
            self.run_main(['--dir', self.tmp], self.env(), opener)
        msg = str(cm.exception.code)
        self.assertIn('403', msg)
        self.assertNotIn(self.key, msg)
        self.assertEqual(len(opener.posts()), 1)

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
