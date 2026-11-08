"""Tests for tools/families.py (display tidying and flavour families). Run: python -m unittest discover -s tools -v"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import families as fam  # noqa: E402

N = ('kcal', 'protein_g', 'fat_g', 'sat_fat_g', 'carbs_g', 'sugars_g', 'fibre_g', 'salt_g')


def p(pid, name, brand='YT', kcal=74.0, protein=10.0, unit='g', **kw):
    d = {'id': pid, 'name': name, 'brand': brand, 'pack_size': None, 'flavour': None, 'unit': unit,
         'kcal': kcal, 'protein_g': protein, 'fat_g': 1.5, 'sat_fat_g': None, 'carbs_g': 8.0,
         'sugars_g': 7.0, 'fibre_g': None, 'salt_g': 0.1}
    d.update(kw)
    return d


class TidyName(unittest.TestCase):
    def test_all_caps_becomes_title_case_and_brand_tail_goes(self):
        self.assertEqual(fam.tidy_name('YT® PROTEINYOGHURT VANILJE - YT®', 'yt'), 'YT Proteinyoghurt Vanilje')

    def test_mixed_case_is_left_alone(self):
        self.assertEqual(fam.tidy_name('YT Proteinpudding Mango 190g', 'YT'), 'YT Proteinpudding Mango 190g')

    def test_small_words_and_sizes_lower_case(self):
        self.assertEqual(fam.tidy_name('KYLLING OG RIS 330ML', 'FIRST PRICE'), 'Kylling og Ris 330ml')

    def test_a_short_brand_as_first_word_is_upper_case(self):
        self.assertEqual(fam.tidy_name('Yt Proteinyoghurt Naturell 430g Tine', 'Tine', {'yt'}), 'YT Proteinyoghurt Naturell 430g Tine')
        self.assertEqual(fam.tidy_name('Ytterst god', 'Tine', {'yt'}), 'Ytterst god')

    def test_trademark_signs_go(self):
        self.assertEqual(fam.tidy_name('Barebells™ Protein Bar', 'Barebells'), 'Barebells Protein Bar')


class TidyBrand(unittest.TestCase):
    def test_brands(self):
        self.assertEqual(fam.tidy_brand('yt', {'yt'}), 'YT')
        self.assertEqual(fam.tidy_brand('Yt', {'yt'}), 'YT')
        self.assertEqual(fam.tidy_brand('BOB'), 'Bob')
        self.assertEqual(fam.tidy_brand('TINE'), 'Tine')
        self.assertEqual(fam.tidy_brand('ICA', {'ica'}), 'ICA')
        self.assertEqual(fam.tidy_brand('SYNNØVE FINDEN'), 'Synnøve Finden')
        self.assertEqual(fam.tidy_brand('Hennig-Olsen'), 'Hennig-Olsen')
        self.assertIsNone(fam.tidy_brand(None))

    def test_capital_brands_follow_the_usual_spelling(self):
        self.assertEqual(fam.capital_brands(['YT', 'YT', 'yt', 'Bob', 'Bob', 'BOB', 'ICA', 'Tine', None]), {'yt', 'ica'})


class Close(unittest.TestCase):
    def test_within_five_percent(self):
        self.assertTrue(fam.close(p('a', 'x', kcal=69), p('b', 'x', kcal=67)))

    def test_over_five_percent_on_any_nutrient(self):
        self.assertFalse(fam.close(p('a', 'x', kcal=74), p('b', 'x', kcal=84)))
        self.assertFalse(fam.close(p('a', 'x', protein=10), p('b', 'x', protein=12)))

    def test_small_values_get_half_a_gram(self):
        self.assertTrue(fam.close(p('a', 'x', salt_g=0.1), p('b', 'x', salt_g=0.5)))

    def test_unknown_kcal_never_matches(self):
        self.assertFalse(fam.close(p('a', 'x', kcal=None), p('b', 'x', kcal=None)))


class Candidates(unittest.TestCase):
    def test_yt_puddings_form_one_family_and_others_stay_out(self):
        rows = [
            p('1', 'YT Proteinpudding Mango 190g'),
            p('2', 'YT Proteinpudding Vanilje 190g'),
            p('3', 'YT Proteinpudding Sjokolade 10x190g - TIPAKNING'),
            p('4', 'YT Proteinpudding Light', kcal=50),  # more than 5% off: its own product
            p('5', 'Synnøve Proteinpudding', brand='Synnøve'),  # different first word
            p('6', 'YT Proteinpudding Drikk', unit='ml'),  # other unit
        ]
        fams = fam.candidates(rows)
        self.assertEqual([sorted(f) for f in fams], [['1', '2', '3']])

    def test_every_member_is_close_to_every_other(self):
        rows = [p('1', 'YT Proteinpudding A', kcal=70), p('2', 'YT Proteinpudding B', kcal=73.5), p('3', 'YT Proteinpudding C', kcal=77)]
        # 70 and 77 are 9% apart, so one of the ends stays out.
        self.assertEqual([len(f) for f in fam.candidates(rows)], [2])

    def test_brands_must_agree(self):
        rows = [p('1', 'Cottage Cheese', brand='Tine', kcal=96), p('2', 'Cottage Cheese', brand='ICA', kcal=93)]
        self.assertEqual(fam.candidates(rows), [])

    def test_missing_brand_is_compatible(self):
        rows = [p('1', 'Cottage Cheese', brand='Tine', kcal=96), p('2', 'Cottage cheese', brand=None, kcal=97)]
        self.assertEqual(len(fam.candidates(rows)), 1)

    def test_names_differ_only_by_size_or_case(self):
        self.assertFalse(fam.names_differ(['YT Protein 190g', 'yt protein, 10x190 g']))
        self.assertTrue(fam.names_differ(['YT Proteinpudding Mango', 'YT Proteinpudding Vanilje']))


class Compatible(unittest.TestCase):
    """Rules added after the review of 200 families (2026-11-08)."""

    def test_variant_words_must_match(self):
        self.assertFalse(fam.compatible(p('1', 'Lätt Crème Fraiche', brand='ICA'), p('2', 'Lätt Crème Fraiche', brand='Ica laktosfri')))
        self.assertFalse(fam.compatible(p('1', 'Coca-Cola Original', kcal=1, unit='ml'), p('2', 'Coca-Cola u/Sukker', kcal=1, unit='ml')))
        self.assertFalse(fam.compatible(p('1', 'Spekeskinke Bit Røkt'), p('2', 'Spekeskinke Bit Urøkt')))
        self.assertFalse(fam.compatible(p('1', 'Laksefilet Naturell'), p('2', 'Laksefilet Marinert')))
        self.assertFalse(fam.compatible(p('1', 'Evergood Dark Hele Bønner', brand='Evergood'), p('2', 'Evergood Dark', brand='Evergood kapsler')))
        self.assertTrue(fam.compatible(p('1', 'YT Proteinpudding Mango'), p('2', 'YT Proteinpudding Vanilje')))

    def test_bundles_never_join(self):
        self.assertFalse(fam.compatible(p('1', 'Supreme Casein 750g'), p('2', 'Supreme Casein 750g + Creatine Monohydrate 500g')))

    def test_near_zero_kcal_needs_the_same_name(self):
        self.assertFalse(fam.compatible(p('1', 'Coca-Cola Intergalactic', kcal=1, unit='ml'), p('2', 'Coca-Cola Lime', kcal=1, unit='ml')))
        self.assertTrue(fam.compatible(p('1', 'Pepsi Max 0,5l', kcal=1, unit='ml'), p('2', 'Pepsi Max 1,5 l', kcal=1, unit='ml')))


class FamilyName(unittest.TestCase):
    def test_promo_words_are_not_the_name(self):
        names = ['BIG BUY 4 x Havremel 1 kg', 'Big Buy 4 x Havremjöl 1 kg']
        self.assertEqual(fam.family_name(fam.tidy_name(names[0], 'Star Nutrition'), names), 'Havremel')

    def test_no_dangling_small_word_at_the_end(self):
        names = ['Riskrem med Jordbærsaus', 'Riskrem med Molte']
        self.assertEqual(fam.family_name(names[0], names), 'Riskrem')

    def test_a_brand_alone_is_not_a_name(self):
        names = ['Rå Hygge Kaffe Shiitake', 'Rå Hygge Reishi Filtermalt']
        self.assertEqual(fam.family_name(names[0], names, brand='Rå Hygge'), 'Rå Hygge Kaffe Shiitake')

    def test_common_words_in_the_representative_order(self):
        names = ['YT Proteinpudding Mango 190g', 'YT Proteinpudding Vanilje 190g', 'YT proteinpudding med smak av vanilje 190 g']
        self.assertEqual(fam.family_name(names[0], names), 'YT Proteinpudding')

    def test_same_product_from_many_shops_keeps_its_name(self):
        names = ['Proteinyoghurt Vanilje 350g Synnøve', 'Proteinyoghurt vanilje 350 g', 'Proteinyoghurt Vanilje']
        self.assertEqual(fam.family_name(names[2], names), 'Proteinyoghurt Vanilje')

    def test_falls_back_to_the_representative_without_sizes(self):
        self.assertEqual(fam.family_name('Mango Pudding 190g', ['Mango Pudding 190g', 'Vanilje Drikk']), 'Mango Pudding')


if __name__ == '__main__':
    unittest.main()
