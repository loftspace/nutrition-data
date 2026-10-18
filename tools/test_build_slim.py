"""Tests for tools/build_slim.py. Run: python -m unittest discover -s tools -v

Builds the real slim databases from the committed shards once, then checks them.
"""
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import build_slim  # noqa: E402

DATA = os.path.join(os.path.dirname(__file__), '..', 'data')
TMP = tempfile.mkdtemp()
FULL = os.path.join(TMP, 'full.sqlite')
OPEN = os.path.join(TMP, 'open.sqlite')


def setUpModule():
    build_slim.build(DATA, FULL, '2026.10.18', 'full', built_at='2026-10-18T00:00:00Z', source_commit='test')
    build_slim.build(DATA, OPEN, '2026.10.18', 'open')


def q(path, sql, *args):
    c = sqlite3.connect(path)
    try:
        return c.execute(sql, args).fetchall()
    finally:
        c.close()


class Normalise(unittest.TestCase):
    def test_norwegian_letters(self):
        n = build_slim.normalise
        self.assertEqual(n('Kjøttdeig'), 'kjottdeig')
        self.assertEqual(n('Bæreposer'), 'baereposer')
        self.assertEqual(n('Håndkjøpt Å'), 'handkjopt a')

    def test_other_accents_and_empty(self):
        n = build_slim.normalise
        self.assertEqual(n('Crème fraîche'), 'creme fraiche')
        self.assertEqual(n(None), '')
        self.assertEqual(n(''), '')


class FullVariant(unittest.TestCase):
    def test_meta(self):
        meta = dict(q(FULL, 'select key, value from meta'))
        self.assertEqual(meta['db_version'], '2026.10.18')
        self.assertEqual(meta['schema_version'], '1')
        self.assertEqual(meta['variant'], 'full')
        self.assertEqual(int(meta['product_count']), q(FULL, 'select count(*) from products')[0][0])
        self.assertEqual(q(FULL, 'pragma user_version')[0][0], 1)

    def test_only_visible_norway_products_with_a_name(self):
        self.assertEqual(q(FULL, "select count(*) from products where trim(name) = ''")[0][0], 0)
        self.assertGreater(q(FULL, 'select count(*) from products')[0][0], 100000)

    def test_unknown_nutrients_stay_null(self):
        # Unknown is never zero: some products must have no kcal at all.
        self.assertGreater(q(FULL, 'select count(*) from products where kcal is null')[0][0], 0)

    def test_search_finds_norwegian_foods(self):
        for word in ('skyr', 'kjottdeig', 'havregryn'):
            n = q(FULL, 'select count(*) from products_fts where products_fts match ?', word + '*')[0][0]
            self.assertGreater(n, 0, word)

    def test_barcode_lookup_uses_all_eans(self):
        ean = q(FULL, 'select ean from product_eans limit 1')[0][0]
        self.assertTrue(q(FULL, 'select 1 from product_eans where ean = ?', ean))

    def test_redirects_point_at_existing_products(self):
        bad = q(FULL, 'select count(*) from redirects where new_id not in (select id from products)')[0][0]
        self.assertEqual(bad, 0)
        self.assertGreater(q(FULL, 'select count(*) from redirects')[0][0], 0)


class OpenVariant(unittest.TestCase):
    def test_only_open_sources(self):
        marks = ','.join('?' * len(build_slim.OPEN_SOURCES))
        n = q(OPEN, 'select count(*) from products where source not in (%s)' % marks, *build_slim.OPEN_SOURCES)[0][0]
        self.assertEqual(n, 0)

    def test_smaller_than_full_and_labelled(self):
        self.assertLess(q(OPEN, 'select count(*) from products')[0][0], q(FULL, 'select count(*) from products')[0][0])
        self.assertEqual(dict(q(OPEN, 'select key, value from meta'))['variant'], 'open')


class StableIds(unittest.TestCase):
    def test_old_ids_still_resolve(self):
        """Every id in the previous release is a product, a redirect or a removed id in the next."""
        prev = os.path.join(TMP, 'prev.sqlite')
        nxt = os.path.join(TMP, 'next.sqlite')
        build_slim.build(DATA, prev, '2026.10.17', 'full')
        # Fake a previous release with ids the new build does not have.
        c = sqlite3.connect(prev)
        c.execute("insert into products(id, name, source, search_text) values ('old:1', 'Old product', 'x', 'old product')")
        c.execute("insert into redirects values ('old:2', 'old:1')")
        c.commit()
        c.close()
        build_slim.build(DATA, nxt, '2026.10.18', 'full', previous=prev)
        for old in [r[0] for r in q(prev, 'select id from products union select old_id from redirects')]:
            hit = (q(nxt, 'select 1 from products where id = ?', old)
                   or q(nxt, 'select 1 from redirects where old_id = ?', old)
                   or q(nxt, 'select 1 from removed where id = ?', old))
            self.assertTrue(hit, old)


if __name__ == '__main__':
    unittest.main()
