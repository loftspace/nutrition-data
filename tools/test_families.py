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
    def test_within_ten_percent(self):
        # Max, 2026-11-08: YT Proteinmelk Kakao (46) is a flavour of Naturell (43).
        self.assertTrue(fam.close(p('a', 'x', kcal=43), p('b', 'x', kcal=46)))

    def test_over_ten_percent_on_any_nutrient(self):
        self.assertFalse(fam.close(p('a', 'x', kcal=74), p('b', 'x', kcal=84)))
        self.assertFalse(fam.close(p('a', 'x', protein=10), p('b', 'x', protein=12)))

    def test_salt_gets_half_a_gram(self):
        self.assertTrue(fam.close(p('a', 'x', salt_g=0.0), p('b', 'x', salt_g=0.31)))

    def test_small_values_get_a_third_of_a_gram(self):
        self.assertTrue(fam.close(p('a', 'x', salt_g=0.1), p('b', 'x', salt_g=0.35)))

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
            p('6', 'YT Proteinpudding Drikk', kcal=60, unit='ml'),  # other numbers
        ]
        fams = fam.candidates(rows)
        self.assertEqual([sorted(f) for f in fams], [['1', '2', '3']])

    def test_every_member_is_close_to_every_other(self):
        rows = [p('1', 'YT Proteinpudding A', kcal=70), p('2', 'YT Proteinpudding B', kcal=75), p('3', 'YT Proteinpudding C', kcal=80)]
        # 70 and 80 are 12.5% apart, so one of the ends stays out.
        self.assertEqual([len(f) for f in fam.candidates(rows)], [2])

    def test_brands_must_agree(self):
        rows = [p('1', 'Cottage Cheese', brand='Tine', kcal=96), p('2', 'Cottage Cheese', brand='ICA', kcal=93)]
        self.assertEqual(fam.candidates(rows), [])

    def test_missing_brand_is_compatible(self):
        rows = [p('1', 'Cottage Cheese', brand='Tine', kcal=96), p('2', 'Cottage cheese', brand=None, kcal=97)]
        self.assertEqual(len(fam.candidates(rows)), 1)

    def test_one_line_despite_spelling_unit_and_brand_position(self):
        # Max, 2026-11-08: "Protein Melk" and "YT Proteinmelk" are one product; Kakao is a flavour.
        rows = [
            p('1', 'YT® PROTEINMELK NATURELL - YT®', brand='yt', kcal=43, protein=5.9, unit='ml'),
            p('2', 'YT® PROTEINMELK KAKAO - YT®', brand='yt', kcal=46, protein=6.0, unit='ml'),
            p('3', 'Protein Melk', brand='YT', kcal=46, protein=6.0, unit='g'),
            p('4', 'Yt Proteinmelk Fettfri 1l Tine', brand='Yt', kcal=43, protein=5.9, unit='ml'),
            p('5', 'YT proteinmelk Kakao, 330 ml', brand='Tine', kcal=46, protein=6.0, unit='ml'),
            p('6', 'Proteinmelk', brand='Tine', kcal=156, protein=21.0),  # a powder: other numbers
        ]
        for r in rows:
            r.update(fat_g=0.2, carbs_g=4.7, sugars_g=4.5, salt_g=0.14)
        self.assertEqual([sorted(f) for f in fam.candidates(rows)], [['1', '2', '3', '4', '5']])

    def test_names_differ_only_by_size_or_case(self):
        self.assertFalse(fam.names_differ(['YT Protein 190g', 'yt protein, 10x190 g']))
        self.assertTrue(fam.names_differ(['YT Proteinpudding Mango', 'YT Proteinpudding Vanilje']))


class Compatible(unittest.TestCase):
    """Rules added after the review of 200 families (2026-11-08)."""

    def test_variant_words_must_match(self):
        self.assertFalse(fam.compatible(p('1', 'Lätt Crème Fraiche', brand='ICA'), p('2', 'Lätt Crème Fraiche', brand='Ica laktosfri')))
        self.assertFalse(fam.compatible(p('1', 'Coca-Cola Original', kcal=1, unit='ml'), p('2', 'Coca-Cola u/Sukker', kcal=1, unit='ml')))
        self.assertFalse(fam.compatible(p('1', 'Coca-Cola Original', kcal=42, unit='ml'), p('2', 'Coca-Cola Zero', kcal=0.2, unit='ml')))
        self.assertFalse(fam.compatible(p('1', 'Spekeskinke Bit Røkt'), p('2', 'Spekeskinke Bit Urøkt')))
        self.assertFalse(fam.compatible(p('1', 'Laksefilet Naturell'), p('2', 'Laksefilet Marinert')))
        self.assertFalse(fam.compatible(p('1', 'Fläskytterfilé', brand='ICA'), p('2', 'Fläskytterfilé Mörmarinerad', brand='ICA')))
        self.assertFalse(fam.compatible(p('1', 'Kycklingben', brand='ICA'), p('2', 'Kycklingben Grillkryddade', brand='ICA')))
        self.assertFalse(fam.compatible(p('1', 'Norvegia Gulost', brand='Tine'), p('2', 'Norvegia Gulost Vellagret', brand='Tine')))
        self.assertFalse(fam.compatible(p('1', 'Lammebog', brand='Lundal'), p('2', 'Lammebog Røykt', brand='Lundal')))
        self.assertFalse(fam.compatible(p('1', 'Russin', brand='Änglamark'), p('2', 'Ekologiska Russin', brand='Änglamark')))
        self.assertFalse(fam.compatible(p('1', 'Kotlett Benfri', brand='ICA'), p('2', 'Kotlett Med Ben', brand='ICA')))
        self.assertFalse(fam.compatible(p('1', 'Kungskassler', brand='Gudruns'), p('2', 'Kungskassler Alspånsrökt', brand='Gudruns')))
        self.assertFalse(fam.compatible(p('1', 'Appelsinjuice', brand='Eldorado'), p('2', 'Appelsinjuice Premium', brand='Eldorado')))

    def test_small_amounts_need_to_be_close_too(self):
        self.assertFalse(fam.close(p('a', 'x', protein=2.1), p('b', 'x', protein=2.6)))
        self.assertFalse(fam.compatible(p('1', 'Evergood Dark Hele Bønner', brand='Evergood'), p('2', 'Evergood Dark', brand='Evergood kapsler')))
        self.assertTrue(fam.compatible(p('1', 'YT Proteinpudding Mango'), p('2', 'YT Proteinpudding Vanilje')))

    def test_bundles_never_join(self):
        self.assertFalse(fam.compatible(p('1', 'Supreme Casein 750g'), p('2', 'Supreme Casein 750g + Creatine Monohydrate 500g')))

    def test_near_zero_kcal_needs_the_same_name(self):
        self.assertFalse(fam.compatible(p('1', 'Coca-Cola Intergalactic', kcal=1, unit='ml'), p('2', 'Coca-Cola Lime', kcal=1, unit='ml')))
        self.assertTrue(fam.compatible(p('1', 'Pepsi Max 0,5l', kcal=1, unit='ml'), p('2', 'Pepsi Max 1,5 l', kcal=1, unit='ml')))


class StrictWhenNamesDiffer(unittest.TestCase):
    """Third review (2026-11-08): when names differ by more than size or spelling, the brand must match."""

    def test_no_brand_never_joins_a_different_name(self):
        rows = [p('1', 'Pils', brand=None, kcal=40), p('2', 'Ringnes Pils', brand='Ringnes', kcal=41), p('3', 'Dahls Pils', brand=None, kcal=40)]
        self.assertEqual(fam.candidates(rows), [])

    def test_other_brands_never_join_through_a_name_word(self):
        rows = [p('1', 'Whey Muscle Builder', brand='Tommi', kcal=380), p('2', 'Whey Muscle NH2', brand='Muscle NH2', kcal=385)]
        self.assertEqual(fam.candidates(rows), [])

    def test_a_brand_at_the_start_of_the_name_counts(self):
        rows = [p('1', 'YT Proteinmelk Kakao', brand='Tine', kcal=46), p('2', 'YT Proteinmelk Naturell', brand='YT', kcal=43),
                p('3', 'YT Proteinbar', brand='YT', kcal=300), p('4', 'YT Proteinbar Salt', brand='YT', kcal=301),
                p('5', 'YT Proteinbar Brownie', brand='YT', kcal=302)]
        self.assertIn(['1', '2'], [sorted(f) for f in fam.candidates(rows)])

    def test_same_name_without_brand_still_joins(self):
        rows = [p('1', 'Kyllingfilet', brand=None, kcal=105), p('2', 'Kyllingfilet', brand='Prior', kcal=106)]
        self.assertEqual(len(fam.candidates(rows)), 1)


class SameWordsAnyOrder(unittest.TestCase):
    """Max, 2026-11-08 ("go through and look for such errors"): the same words in another order,
    with or without the brand, are the same name ("Laks Røkt" / "Røkt Laks")."""

    def test_core_ignores_order_brand_and_size(self):
        rows = [p('1', 'Bodylab Clear Whey Blackcurrant 500g', brand='Bodylab'), p('2', 'Blackcurrant Clear Whey', brand='Bodylab'),
                p('3', 'Bodylab Whey 100', brand='Bodylab'), p('4', 'Bodylab Carbo', brand='Bodylab')]
        lines = fam.Lines(rows)
        self.assertEqual(lines.core(rows[0]['name'], 'Bodylab'), lines.core(rows[1]['name'], 'Bodylab'))
        self.assertEqual(lines.core('Laks Røkt', 'Troll'), lines.core('Røkt Laks', 'Troll'))

    def test_reversed_words_and_brand_only_names_join(self):
        rows = [p('1', 'Indrefilet Pampas', brand='REMA', kcal=135), p('2', 'Pampas Indrefilet', brand='REMA 1000', kcal=135),
                p('3', 'Lofotpils', brand='Lofotpils', kcal=41), p('4', 'Lofotpils', brand='Lofotpils', kcal=41),
                p('5', 'Lofotpils', brand='Lofotpils', kcal=41)]
        self.assertEqual(sorted(sorted(f) for f in fam.candidates(rows)), [['1', '2'], ['3', '4', '5']])

    def test_same_words_need_no_check(self):
        rows = [p('1', 'Laks Røkt', brand='Troll', kcal=225), p('2', 'Røkt Laks', brand='Troll', kcal=225)]
        fams = fam.candidates(rows)
        self.assertEqual([sorted(f) for f in fams], [['1', '2']])
        self.assertFalse(fam.names_differ_core([r['_core'] for r in rows]))


class DisplayName(unittest.TestCase):
    """Max, 2026-11-08: a name never carries its pack size, nor the maker tacked on at the end."""

    def test_sizes_and_a_trailing_maker_go(self):
        lines = fam.Lines([p(str(i), 'Tine Melk', brand='Tine') for i in range(3)])
        self.assertEqual(fam.display_name('YT Protein Yoghurt Salt Karamell 200g Tine', 'YT', lines),
                         'YT Protein Yoghurt Salt Karamell')
        self.assertEqual(fam.display_name('Kylling og Ris 330ml', 'First Price', lines), 'Kylling og Ris')
        self.assertEqual(fam.display_name('BIG BUY 4 x Havremel 1 kg', 'Star Nutrition', lines), 'Havremel')

    def test_a_trailing_brand_stays_when_it_is_the_product(self):
        lines = fam.Lines([p(str(i), 'Oreo Original', brand='Oreo') for i in range(3)] +
                          [p(str(i + 3), 'Marabou Mjölkchoklad', brand='Marabou') for i in range(3)])
        self.assertEqual(fam.display_name('Marabou Oreo', 'Marabou', lines), 'Marabou Oreo')

    def test_number_codes_go(self):
        lines = fam.Lines([p(str(i), 'Tine Melk', brand='Tine') for i in range(3)])
        self.assertEqual(fam.display_name('Rapsstekolja smörsmak, 260201', 'ICA', lines), 'Rapsstekolja smörsmak')

    def test_a_name_that_is_only_a_size_or_brand_keeps_something(self):
        lines = fam.Lines([p(str(i), 'Tine Melk', brand='Tine') for i in range(3)])
        self.assertEqual(fam.display_name('Tine', 'Tine', lines), 'Tine')
        self.assertEqual(fam.display_name('Mager Kjøttdeig 400g', None, lines), 'Mager Kjøttdeig')


class ReviewedGuard(unittest.TestCase):
    """Groups a model read as duplicates (data/families_reviewed.json) still pass a number check."""

    def test_sugar_free_and_light_stay_apart_in_reviewed_groups(self):
        a = p('1', 'Monster Belgisk Mørk Sjokolade', brand='Monster', kcal=500); a['_bkey'] = 'monster'
        b = p('2', 'Monster Belgisk Mørk Sjokolade Sukkerfri', brand='Monster', kcal=480); b['_bkey'] = 'monster'
        self.assertFalse(fam.reviewed_ok(b, a))

    def test_guard(self):
        a = p('1', 'Aioli', brand='Rema 1000', kcal=745); a['_bkey'] = 'rema'
        b = p('2', 'Aioli', brand='Rema 1000', kcal=564); b['_bkey'] = 'rema'
        c = p('3', 'Aioli Hvitløk', brand='Rema 1000', kcal=700); c['_bkey'] = 'rema'
        d = p('4', 'Aioli', brand='Coop', kcal=740); d['_bkey'] = 'coop'
        e = p('5', 'Aioli', brand='Rema 1000', kcal=None); e['_bkey'] = 'rema'
        self.assertFalse(fam.reviewed_ok(b, a))   # 24% apart
        self.assertTrue(fam.reviewed_ok(c, a))    # 6% apart
        self.assertFalse(fam.reviewed_ok(d, a))   # other brand
        self.assertTrue(fam.reviewed_ok(e, a))    # no numbers: nothing to contradict


class FamilyName(unittest.TestCase):
    def test_a_describing_word_is_not_the_product_line(self):
        lines = fam.Lines([p('1', 'Grilstad Lett Gullsalami', brand='Grilstad'), p('2', 'Grilstad Lett Jubelsalami', brand='Grilstad'),
                           p('3', 'Grilstad Kokt Skinke', brand='Grilstad')])
        self.assertEqual(lines.line('Grilstad Lett Gullsalami', 'Grilstad'), 'gullsalami')

    def test_no_shared_product_word_means_no_name(self):
        names = ['Lemon Lime Bitters', 'Root Beer', 'Ginger Beer']
        self.assertIsNone(fam.family_name(names[0], names, 'Bundaberg', strict=True))
        self.assertEqual(fam.family_name(names[0], names, 'Bundaberg'), 'Lemon Lime Bitters')

    def test_split_words_count_as_one(self):
        names = ['YT Proteinmelk Naturell', 'YT Proteinmelk Kakao', 'Protein Melk']
        self.assertEqual(fam.family_name(names[0], names, 'YT'), 'YT Proteinmelk')

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


class CompoundTails(unittest.TestCase):
    """Norwegian compounds are one token: `melk` must find `lettmelk` (products-db.md, Search)."""

    def tails(self, text):
        import build_slim
        return build_slim.with_compound_tails(text).split()

    def test_food_word_at_the_end_is_added(self):
        self.assertEqual(self.tails('tine lettmelk'), ['tine', 'lettmelk', 'melk'])
        self.assertIn('ost', self.tails('synnove gulost'))
        self.assertIn('saus', self.tails('toro tomatsaus'))

    def test_every_known_tail_of_a_long_compound(self):
        words = self.tails('prior kyllingkjottdeig')
        self.assertIn('kjottdeig', words)
        self.assertIn('deig', words)

    def test_words_that_only_look_like_compounds_are_left_alone(self):
        for w in ('frokost', 'eplemost', 'lakris', 'bunnpris', 'caramel', 'gammel', 'jordgubbar', 'langtidsholdbar', 'post'):
            self.assertEqual(self.tails(w), [w], w)

    def test_the_word_itself_is_not_repeated(self):
        self.assertEqual(self.tails('melk'), ['melk'])
        self.assertEqual(self.tails('lettmelk melk'), ['lettmelk', 'melk'])


if __name__ == '__main__':
    unittest.main()
