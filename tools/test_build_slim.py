"""Tests for tools/build_slim.py. Run: python -m unittest discover -s tools -v

Builds the real slim databases from the committed shards once, then checks them.
"""
import json
import os
import re
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import build_slim  # noqa: E402

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, '..', 'data')
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
        self.assertEqual(meta['schema_version'], '2')
        self.assertEqual(meta['variant'], 'full')
        self.assertEqual(int(meta['product_count']), q(FULL, 'select count(*) from products')[0][0])
        self.assertEqual(q(FULL, 'pragma user_version')[0][0], 2)

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
        c.execute("insert into products(id, name, per_100_unit, source, verified, search_text) "
                  "values ('old:1', 'Old product', 'g', 'x', 0, 'old product')")
        c.execute("insert into redirects values ('old:2', 'old:1')")
        c.commit()
        c.close()
        build_slim.build(DATA, nxt, '2026.10.18', 'full', previous=prev)
        for old in [r[0] for r in q(prev, 'select id from products union select old_id from redirects')]:
            hit = (q(nxt, 'select 1 from products where id = ?', old)
                   or q(nxt, 'select 1 from redirects where old_id = ?', old)
                   or q(nxt, 'select 1 from removed where id = ?', old))
            self.assertTrue(hit, old)


NUTRIENTS = ('kcal', 'protein_g', 'fat_g', 'sat_fat_g', 'carbs_g', 'sugars_g', 'fibre_g', 'salt_g')


def flags(dq):
    return json.loads(dq) if dq else []


class Barcodes(unittest.TestCase):
    """Canonical barcodes (contract: Barcodes). Golden cases copied from Makro packages/contracts/search/barcode.json."""

    def test_golden_cases(self):
        with open(os.path.join(HERE, 'testdata', 'barcode.json'), encoding='utf-8') as f:
            cases = json.load(f)['cases']
        self.assertGreaterEqual(len(cases), 9)
        for c in cases:
            self.assertEqual(build_slim.canonical_ean(c['input']), c['expected'], c['id'])

    def test_none_is_not_a_barcode(self):
        self.assertIsNone(build_slim.canonical_ean(None))

    def test_stored_barcodes_are_canonical(self):
        for path in (FULL, OPEN):
            for (ean,) in q(path, 'select ean from product_eans'):
                self.assertEqual(build_slim.canonical_ean(ean), ean)
            for (ean,) in q(path, 'select ean from products where ean is not null'):
                self.assertEqual(build_slim.canonical_ean(ean), ean)

    def test_eight_digit_scan_finds_a_product(self):
        # v0 stored EAN-8 padded to 13 while scanners return 8 digits; both sides now canonicalise.
        ean = q(FULL, "select ean from product_eans where ean like '00000%' limit 1")[0][0]
        self.assertTrue(q(FULL, 'select 1 from product_eans where ean = ?', build_slim.canonical_ean(ean[5:])))

    def test_unique_index_and_no_products_ean_index(self):
        for path in (FULL, OPEN):
            unique = [r for r in q(path, "pragma index_list('product_eans')") if r[2]]
            self.assertTrue(unique)
            names = {r[0] for r in q(path, "select name from sqlite_master where type = 'index'")}
            self.assertNotIn('ix_products_ean', names)


class NonFood(unittest.TestCase):
    def test_no_non_food_rows(self):
        for path in (FULL, OPEN):
            self.assertEqual(q(path, "select count(*) from products where category = 'non_food'")[0][0], 0)


class Per100Unit(unittest.TestCase):
    def test_from_pack_size(self):
        u = build_slim.per_100_unit
        self.assertEqual(u('330ml', 'x'), 'ml')
        self.assertEqual(u('1,5L', 'x'), 'ml')
        self.assertEqual(u('33 cl', 'x'), 'ml')
        self.assertEqual(u('450 g', 'x'), 'g')
        self.assertEqual(u('1 kg', 'x'), 'g')
        self.assertEqual(u('12 x 55g', 'x'), 'g')

    def test_from_name_when_pack_size_has_no_unit(self):
        u = build_slim.per_100_unit
        self.assertEqual(u(None, 'YT Proteinmelk Kakao Fettfri 330ml'), 'ml')
        self.assertEqual(u('4BX', 'Barebells Protein Bar 4 x 55 g'), 'g')

    def test_default_is_grams(self):
        self.assertEqual(build_slim.per_100_unit(None, 'Havregryn'), 'g')
        self.assertEqual(build_slim.per_100_unit('60 kapsler', 'Omega-3'), 'g')

    def test_column(self):
        for path in (FULL, OPEN):
            bad = q(path, "select count(*) from products where per_100_unit is null or per_100_unit not in ('g', 'ml')")[0][0]
            self.assertEqual(bad, 0)
        self.assertGreater(q(FULL, "select count(*) from products where per_100_unit = 'ml'")[0][0], 1000)


class Sources(unittest.TestCase):
    def test_every_source_is_listed_with_a_kind(self):
        for path in (FULL, OPEN):
            missing = q(path, 'select count(*) from products where source not in (select slug from sources)')[0][0]
            self.assertEqual(missing, 0)
            kinds = {r[0] for r in q(path, 'select kind from sources')}
            self.assertLessEqual(kinds, {'open_database', 'government', 'brand', 'shop', 'custom'})
            self.assertEqual(q(path, "select kind from sources where slug = 'custom'"), [('custom',)])
            self.assertEqual(q(path, "select count(*) from sources where coalesce(display_name, '') = ''")[0][0], 0)

    def test_open_sources_are_not_shops(self):
        for slug in build_slim.OPEN_SOURCES:
            self.assertIn(build_slim.SOURCES[slug][1], ('open_database', 'government'), slug)


class DataQuality(unittest.TestCase):
    def test_normalise_entries(self):
        nq = build_slim.normalise_quality
        self.assertEqual(nq(['derived_canonical_from_46_products', 'pure_compound', 'Typical serving 2 to 5 g. Pure compound.']),
                         ['derived_canonical', 'pure_compound'])
        self.assertEqual(nq(['Typical serving 1 to 3 g. Pure compound.']), ['pure_compound'])
        self.assertEqual(nq(['missing_macros:carbs', 'filled_from_openfoodfacts']),
                         ['missing_macros:carbs', 'filled_from_openfoodfacts'])
        with self.assertRaises(ValueError):
            nq(['made_up_flag'])

    def test_only_known_codes_in_the_file(self):
        known = build_slim.SUSPECT_FLAGS | build_slim.INFO_FLAGS
        for path in (FULL, OPEN):
            for (dq,) in q(path, 'select data_quality from products where data_quality is not null'):
                for f in flags(dq):
                    code = f.split(':', 1)[0]
                    self.assertTrue(code in known or code.startswith('filled_from_'), f)


class Verified(unittest.TestCase):
    def test_matches_the_rule(self):
        for path in (FULL, OPEN):
            kinds = dict(q(path, 'select slug, kind from sources'))
            rows = q(path, 'select status, kcal, protein_g, fat_g, carbs_g, data_quality, source, verified from products')
            n = 0
            for status, kcal, p, f, c, dq, src, verified in rows:
                macros = (kcal, p, f, c)
                ok = (status == 'from_source'
                      and all(v is not None for v in macros) and any(v != 0 for v in macros)
                      and not any(x.split(':', 1)[0] in build_slim.SUSPECT_FLAGS for x in flags(dq))
                      and kinds[src] != 'shop')
                self.assertEqual(verified, int(ok))
                n += ok
            self.assertGreater(n, 10000)


class ZeroKcal(unittest.TestCase):
    def test_allowlist(self):
        z = build_slim.zero_allowed
        self.assertTrue(z('Isklar Sparkling', []))
        self.assertTrue(z('Naturlig mineralvann med kullsyre', []))
        self.assertTrue(z('Bordsalt', []))
        self.assertTrue(z('Iodised Salt', []))
        self.assertTrue(z('Sukrin Stevia Drops Lemon 30 ml', []))
        self.assertTrue(z('Creatine monohydrate', ['pure_compound']))
        self.assertFalse(z('Tine Cottage Cheese 400g', []))
        self.assertFalse(z('Kalkun Lårfilet', []))
        self.assertFalse(z('Saltstenger', []))
        for name in ('Sukrin Stevia Drops Caramel 30 ml', 'Gymqueen Tasty Drops Caramel 30ml', 'Steviosa pulver',
                     'Monster Lavkarbo Zero Drops - Cookie', 'Evian 75cl PET', 'Ramlösa Fläder Lime', 'Jodsalz',
                     "Aqua d'Or still", 'Sprudle Sitron'):
            self.assertTrue(z(name, []), name)
        # Diet soft drinks are not on the contract's allowlist (water, sweeteners, salt).
        self.assertFalse(z('Coca-Cola Zero', []))
        # Salty snacks and spice mixes are not salt.
        for name in ('X-tra Potetchips Salt 300g', 'Sørlandschips Havsalt 100g', 'Salt Sild 100g',
                     'YT Proteinbar Salt Karamell 50 g', 'Kyllingkrydder No Added Salt 445g',
                     'Gaveeske Nøtter Og Salt Chips'):
            self.assertFalse(z(name, []), name)

    def test_missing_written_as_zero_becomes_null(self):
        for pid in ('ean:7038010054471', 'kassalapp:40188'):
            rows = q(FULL, 'select kcal, protein_g, fat_g, carbs_g, data_quality, verified from products where id = ?', pid)
            self.assertEqual(len(rows), 1, pid)
            kcal, p, f, c, dq, verified = rows[0]
            self.assertEqual((kcal, p, f, c), (None, None, None, None), pid)
            self.assertIn('no_nutrition', flags(dq))
            self.assertEqual(verified, 0)

    def test_all_zero_count_stays_low(self):
        """CI guard: all-zero products left after the rule. Raise the limit only on purpose."""
        rows = q(FULL, 'select name, data_quality from products where kcal = 0 and protein_g = 0 and fat_g = 0 and carbs_g = 0')
        self.assertLessEqual(len(rows), build_slim.MAX_ALL_ZERO)
        for name, dq in rows:
            self.assertTrue(build_slim.zero_allowed(name, flags(dq)), name)


class OpenValues(unittest.TestCase):
    def test_no_values_from_non_open_sources(self):
        with open(os.path.join(DATA, 'manifest.json'), encoding='utf-8') as f:
            man = json.load(f)
        ids = {r[0] for r in q(OPEN, 'select id from products')}
        closed = set()
        for n in build_slim.read_shard(DATA, man, 'nutrients'):
            if (n['basis'] == 'per_100g' and n['code'] in NUTRIENTS and n['product_id'] in ids
                    and n['source'] not in build_slim.OPEN_SOURCES):
                closed.add((n['product_id'], n['code']))
        self.assertGreater(len(closed), 0)
        c = sqlite3.connect(OPEN)
        try:
            for pid, code in closed:
                value = c.execute('select %s from products where id = ?' % code, (pid,)).fetchone()[0]
                self.assertIsNone(value, (pid, code))
            for (dq,) in c.execute("select data_quality from products where data_quality like '%filled_from_%'"):
                for f in flags(dq):
                    if f.startswith('filled_from_'):
                        self.assertIn(f[len('filled_from_'):], build_slim.OPEN_SOURCES, f)
        finally:
            c.close()


class ReleaseWorkflow(unittest.TestCase):
    def test_previous_for_both_variants(self):
        with open(os.path.join(HERE, '..', '.github', 'workflows', 'release-db.yml'), encoding='utf-8') as f:
            text = f.read()
        fetch, build = text.split('Build both variants', 1)
        self.assertIn('products-open.sqlite.gz', fetch)
        full, open_ = build.split('--variant open', 1)
        self.assertIn('$PREVIOUS_FULL', full)
        self.assertIn('$PREVIOUS_OPEN', open_.split('sha256sum', 1)[0])


if __name__ == '__main__':
    unittest.main()
