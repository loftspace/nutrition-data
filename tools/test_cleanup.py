"""Tests for tools/cleanup.py. Run: python -m unittest tools/test_cleanup.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import cleanup  # noqa: E402


def row(**kw):
    base = dict(id='a', name='Vare', brand='Merke', flavour=None, kcal=100.0, protein_g=10.0, fat_g=2.0, sat_fat_g=1.0,
                carbs_g=10.0, sugars_g=1.0, fibre_g=1.0, salt_g=1.0, category='snacks_sweets', serving_g=None)
    base.update(kw)
    return base


class Names(unittest.TestCase):
    def test_html_and_broken_characters(self):
        self.assertEqual(cleanup.clean_name('Fit &amp; Smart', 'x'), 'Fit & Smart')
        self.assertEqual(cleanup.clean_name('Clean sav:D + Creatine Â Strawberry Punch', 'x'), 'Clean sav:D + Creatine Strawberry Punch')

    def test_empty_brackets(self):
        self.assertEqual(cleanup.clean_name('Bodylab Carbo Recovery ( ) - Lemon Lime', 'x'), 'Bodylab Carbo Recovery - Lemon Lime')

    def test_a_trademark_in_brackets(self):
        self.assertEqual(cleanup.clean_name('Protein Puffs (®)', 'x'), 'Protein Puffs')

    def test_brackets_left_empty_by_removing_a_size(self):
        self.assertEqual(cleanup.no_empty_brackets('Carbo Recovery ( ) - Lemon Lime'), 'Carbo Recovery - Lemon Lime')
        self.assertEqual(cleanup.no_empty_brackets('Whey (Vanilje)'), 'Whey (Vanilje)')

    def test_cut_off_endings(self):
        self.assertEqual(cleanup.clean_name('Seifilet Skinn & beinfri, ca.', 'x'), 'Seifilet Skinn & beinfri')
        self.assertEqual(cleanup.clean_name('Dolmøy Cognacmarinert Laks ca', 'x'), 'Dolmøy Cognacmarinert Laks')
        self.assertEqual(cleanup.clean_name('Natur-Drogeriet Engelsk Lakrids M.', 'x'), 'Natur-Drogeriet Engelsk Lakrids')
        self.assertEqual(cleanup.clean_name('Lunch Box m/', 'x'), 'Lunch Box')
        self.assertEqual(cleanup.clean_name('Kinder.', 'x'), 'Kinder')

    def test_i_stays_in_norwegian_names(self):
        self.assertEqual(cleanup.clean_name('Reker i Lake', 'x'), 'Reker i Lake')
        self.assertEqual(cleanup.clean_name('Lofoten Makrell I Tomat', 'x'), 'Lofoten Makrell I Tomat')

    def test_apex_uses_i_as_a_separator(self):
        self.assertEqual(cleanup.clean_name('ABE I PUMP Shot I Stim-Free I', 'apex-no'), 'ABE PUMP Shot Stim-Free')

    def test_case(self):
        self.assertEqual(cleanup.clean_name('ovnsbakt chips', 'x'), 'Ovnsbakt chips')
        self.assertEqual(cleanup.clean_name('KALLES ORIGINAL Kaviar', 'x'), 'Kalles Original Kaviar')
        self.assertEqual(cleanup.clean_name('Kalles ABC Kaviar', 'x'), 'Kalles ABC Kaviar')
        self.assertEqual(cleanup.clean_name('DRY ROASTED NUTS', 'x'), 'DRY ROASTED NUTS')  # families.tidy_name does these


class Brands(unittest.TestCase):
    def test_legal_suffix(self):
        self.assertEqual(cleanup.clean_brand('Orkla Foods Norge AS'), 'Orkla Foods Norge')
        self.assertEqual(cleanup.clean_brand('Matgard AB'), 'Matgard')
        self.assertEqual(cleanup.clean_brand('Refresco Deutschland Gmbh'), 'Refresco Deutschland')
        self.assertEqual(cleanup.clean_brand('Private Brands A/S'), 'Private Brands')

    def test_a_doubled_legal_suffix(self):
        self.assertEqual(cleanup.clean_brand('Staur Fjellbakeri As As'), 'Staur Fjellbakeri')

    def test_a_brand_that_is_only_a_suffix_stays(self):
        self.assertEqual(cleanup.clean_brand('AS'), 'AS')

    def test_junk_and_entities(self):
        self.assertIsNone(cleanup.clean_brand('???'))
        self.assertIsNone(cleanup.clean_brand('-'))
        self.assertEqual(cleanup.clean_brand('Dave &amp; Jon’s'), "Dave & Jon's")

    def test_aliases(self):
        self.assertEqual(cleanup.clean_brand('Bama dagligvare as'), 'Bama')
        self.assertEqual(cleanup.clean_brand('Hennig-olsen is as'), 'Hennig-Olsen')

    def test_one_spelling_prefers_capitals_then_count(self):
        book = cleanup.BrandBook(['United bakeries'] * 85 + ['United Bakeries'] * 12 + ['Rema1000'] * 51 + ['Rema 1000'] * 824
                                 + ['Diplom-is'] * 49 + ['Diplom-Is'] * 22 + ['Diplom Is'] * 9 + ['Tine Sa'] * 5 + ['Tine'] * 233)
        self.assertEqual(book.canon('United bakeries'), 'United Bakeries')
        self.assertEqual(book.canon('Rema1000'), 'Rema 1000')
        self.assertEqual(book.canon('Diplom Is'), 'Diplom-Is')
        self.assertEqual(book.canon('Tine Sa'), 'Tine')
        self.assertIsNone(book.canon(None))

    def test_spelling_choices(self):
        book = cleanup.BrandBook(['SOLID Nutrition'] * 28 + ['Solid Nutrition'] * 3 + ['Nicks'] * 20 + ["Nick's"] * 2
                                 + ['Polarbröd'] * 9 + ['Polarbrød'] * 2 + ['Zeina’s'] * 2)
        self.assertEqual(book.canon('SOLID Nutrition'), 'Solid Nutrition')
        self.assertEqual(book.canon('Nicks'), "Nick's")
        self.assertEqual(book.canon('Polarbröd'), 'Polarbrød')
        self.assertEqual(book.canon('Zeina’s'), "Zeina's")

    def test_an_ampersand_or_apostrophe_is_kept(self):
        book = cleanup.BrandBook(['Paul Thom'] * 9 + ['Paul & Thom'] * 2 + ['Feldts'] * 9 + ["Feldt's"] * 2)
        self.assertEqual(book.canon('Paul Thom'), 'Paul & Thom')
        self.assertEqual(book.canon('Feldts'), "Feldt's")

    def test_known_stylised_brands(self):
        self.assertEqual(cleanup.clean_brand('Terrasana'), 'TerraSana')
        self.assertEqual(cleanup.clean_brand('Powerbar'), 'PowerBar')

    def test_a_brand_of_digits_stays(self):
        self.assertEqual(cleanup.clean_brand('1839'), '1839')
        self.assertEqual(cleanup.clean_brand('7-11'), '7-Eleven')

    def test_umlauts_win(self):
        book = cleanup.BrandBook(['Master'] * 9 + ['Mäster'] * 2)
        self.assertEqual(book.canon('Master'), 'Mäster')

    def test_shouting_is_not_the_spelling(self):
        self.assertEqual(cleanup.BrandBook(['DIET FOOD'] * 3).canon('DIET FOOD'), 'Diet Food')
        self.assertEqual(cleanup.BrandBook(['ICA'] * 3).canon('ICA'), 'ICA')

    def test_brand_already_in_name(self):
        self.assertTrue(cleanup.brand_in_name('BioTechUSA', 'L-glutamine Biotech Usa'))
        self.assertTrue(cleanup.brand_in_name('Aronmat', 'Tørrsaltet Bacon Aron Mat'))
        self.assertFalse(cleanup.brand_in_name('Tine', 'Melk'))

    def test_swapped_brand_and_size(self):
        self.assertEqual(cleanup.swapped_fields('600 G', 'Coop'), ('Coop', '600 G'))
        self.assertEqual(cleanup.swapped_fields('Coop', '600 G'), ('Coop', '600 G'))
        self.assertEqual(cleanup.swapped_fields('600 G', None), ('600 G', None))

    def test_most_common_decides_between_good_spellings(self):
        book = cleanup.BrandBook(['Eldorado'] * 756 + ['El Dorado'] * 4 + ['Dahls'] * 41 + ["Dahl's"] * 3)
        self.assertEqual(book.canon('El Dorado'), 'Eldorado')
        self.assertEqual(book.canon("Dahl's"), 'Dahls')

    def test_name_follows_the_brand(self):
        self.assertEqual(cleanup.rename_brand('Bama dagligvare as Spirer', 'Bama dagligvare as', 'Bama'), 'Bama Spirer')
        self.assertEqual(cleanup.rename_brand('Ica basic Pasta', 'Ica basic', 'ICA Basic'), 'ICA Basic Pasta')
        self.assertEqual(cleanup.rename_brand('Spirer', 'Bama dagligvare as', 'Bama'), 'Spirer')


class CounterPack(unittest.TestCase):
    def test_text_goes_back_into_the_name(self):
        self.assertEqual(cleanup.counter_pack('Kylling', 'Indisk Punjabi Varm pr Kg'), ('Kylling Indisk Punjabi Varm', None))
        self.assertEqual(cleanup.counter_pack('Berlinerbolle', 'm/Bringebær'), ('Berlinerbolle m/Bringebær', None))
        self.assertEqual(cleanup.counter_pack('Gruyere Grotte', 'Lagret 12+ Mnd'), ('Gruyere Grotte Lagret 12+ Mnd', None))

    def test_a_sales_unit_is_cut_from_the_name_too(self):
        self.assertEqual(cleanup.counter_pack('Kyllingspyd Gyros Varm pr stykk', '1 piece'), ('Kyllingspyd Gyros Varm', '1 piece'))
        self.assertEqual(cleanup.counter_pack('Skinke', 'Dolce Riserva Ferrarinipr Kg'), ('Skinke Dolce Riserva Ferrarini', None))

    def test_only_a_sales_unit_is_removed(self):
        self.assertEqual(cleanup.counter_pack('Skagenrøre', 'pr Kg'), ('Skagenrøre', None))
        self.assertEqual(cleanup.counter_pack('Ostehorn', 'Husets pr stykk'), ('Ostehorn', None))

    def test_an_order_note_is_not_a_name(self):
        self.assertEqual(cleanup.counter_pack('Nykokt sjøkreps', 'Bestilles'), ('Nykokt sjøkreps', None))

    def test_a_bare_unit_word_is_not_a_name(self):
        self.assertEqual(cleanup.counter_pack('Fiken Frisk', 'STK'), ('Fiken Frisk', None))

    def test_real_sizes_stay(self):
        self.assertEqual(cleanup.counter_pack('Melk', '1 liter'), ('Melk', '1 liter'))
        self.assertEqual(cleanup.counter_pack('Egg', '12STK'), ('Egg', '12STK'))
        self.assertEqual(cleanup.counter_pack('Melk', None), ('Melk', None))


class SizeText(unittest.TestCase):
    def test_not_a_size(self):
        for junk in ('.', 'g', '250', '1 c', '1pcs', '1 piece', '1STK', 'stykk', 'bestilles pr stykk á ca.100g'):
            self.assertIsNone(cleanup.size_text(junk), junk)

    def test_a_size(self):
        for good in ('12STK', '20POS', '8 oz', '48 portioner'):
            self.assertEqual(cleanup.size_text(good), good)


class Unusable(unittest.TestCase):
    def test_foreign_script(self):
        self.assertTrue(cleanup.unusable(row(name='Тунец')))
        self.assertTrue(cleanup.unusable(row(name='Plain Noodles', brand='麦老大')))
        self.assertFalse(cleanup.unusable(row(name='Blåbær Crème Müsli')))

    def test_a_name_without_letters(self):
        self.assertTrue(cleanup.unusable(row(name='7333192138752')))
        self.assertTrue(cleanup.unusable(row(name='5%')))
        self.assertFalse(cleanup.unusable(row(name='M&m')))

    def test_a_percentage_takes_its_brand(self):
        self.assertEqual(cleanup.percent_name('70%', 'Marabou'), 'Marabou 70%')
        self.assertEqual(cleanup.percent_name('70%', None), '70%')
        self.assertEqual(cleanup.percent_name('Mørk 70%', 'Marabou'), 'Mørk 70%')


class Impossible(unittest.TestCase):
    def test_energy_above_pure_fat(self):
        self.assertTrue(cleanup.impossible(row(kcal=2374.0)))
        self.assertFalse(cleanup.impossible(row(kcal=915.0, fat_g=100.0, protein_g=0.0, carbs_g=0.0)))

    def test_a_macro_above_100(self):
        self.assertTrue(cleanup.impossible(row(protein_g=143.0)))

    def test_macros_summing_above_100(self):
        self.assertTrue(cleanup.impossible(row(protein_g=9.0, fat_g=50.0, carbs_g=68.0)))
        self.assertFalse(cleanup.impossible(row(protein_g=30.0, fat_g=30.0, carbs_g=44.0)))

    def test_unknown_is_not_impossible(self):
        self.assertFalse(cleanup.impossible(row(protein_g=None, fat_g=None, carbs_g=None)))

    def test_zero_kcal_with_real_macros(self):
        self.assertTrue(cleanup.impossible(row(name='Potetmel', kcal=0.0, protein_g=0.0, fat_g=0.0, carbs_g=14.0, category='bread_cereal_grain')))

    def test_zero_kcal_sweeteners_and_supplements_stay(self):
        self.assertFalse(cleanup.impossible(row(name='Sukrin +', kcal=0.0, protein_g=0.0, fat_g=0.0, carbs_g=100.0)))
        self.assertFalse(cleanup.impossible(row(name='Erythrit Stevia Mix', kcal=0.0, protein_g=0.0, fat_g=0.0, carbs_g=100.0)))
        self.assertFalse(cleanup.impossible(row(name='Svelli Sukkererstatning', kcal=0.0, protein_g=0.0, fat_g=0.0, carbs_g=100.0)))
        self.assertFalse(cleanup.impossible(row(name='SUKKR 1:1', kcal=0.0, protein_g=0.0, fat_g=0.0, carbs_g=100.0)))
        self.assertFalse(cleanup.impossible(row(name='L-Glutamine', kcal=0.0, protein_g=25.0, fat_g=0.0, carbs_g=0.0, category='amino_acids')))


class SubNutrients(unittest.TestCase):
    def test_sugar_above_carbs_becomes_unknown(self):
        p, flags = row(carbs_g=8.0, sugars_g=10.0), []
        cleanup.tidy_nutrients(p, flags)
        self.assertIsNone(p['sugars_g'])
        self.assertEqual(p['carbs_g'], 8.0)
        self.assertEqual(flags, ['sugars_exceed_carbs'])

    def test_sat_above_fat_becomes_unknown(self):
        p, flags = row(fat_g=1.3, sat_fat_g=5.0), []
        cleanup.tidy_nutrients(p, flags)
        self.assertIsNone(p['sat_fat_g'])
        self.assertEqual(flags, ['sat_fat_exceeds_fat'])

    def test_rounding_is_left_alone(self):
        p, flags = row(carbs_g=8.0, sugars_g=8.4), []
        cleanup.tidy_nutrients(p, flags)
        self.assertEqual(p['sugars_g'], 8.4)
        self.assertEqual(flags, [])

    def test_a_side_value_above_100_becomes_unknown(self):
        p, flags = row(salt_g=846.0), []
        cleanup.tidy_nutrients(p, flags)
        self.assertIsNone(p['salt_g'])

    def test_a_silly_serving_is_unknown(self):
        p, flags = row(serving_g=5000.0), []
        cleanup.tidy_nutrients(p, flags)
        self.assertIsNone(p['serving_g'])


class SameProducts(unittest.TestCase):
    def test_same_name_brand_and_numbers_fold_to_the_first(self):
        rows = [row(id='best'), row(id='copy', name='VARE', kcal=105.0)]
        self.assertEqual(cleanup.same_products(rows), {'copy': 'best'})

    def test_numbers_more_than_10_percent_apart_stay(self):
        self.assertEqual(cleanup.same_products([row(id='a'), row(id='b', kcal=150.0)]), {})

    def test_other_brand_flavour_or_unknown_numbers_stay(self):
        self.assertEqual(cleanup.same_products([row(id='a'), row(id='b', brand='Annet')]), {})
        self.assertEqual(cleanup.same_products([row(id='a', flavour='Sitron'), row(id='b', flavour='Lime')]), {})
        self.assertEqual(cleanup.same_products([row(id='a'), row(id='b', protein_g=None)]), {})

    def test_no_brand_never_folds(self):
        self.assertEqual(cleanup.same_products([row(id='a', brand=None), row(id='b', brand=None)]), {})

    def test_two_clusters_under_one_name(self):
        rows = [row(id='a'), row(id='b', kcal=300.0), row(id='c', kcal=102.0), row(id='d', kcal=301.0)]
        self.assertEqual(cleanup.same_products(rows), {'c': 'a', 'd': 'b'})


if __name__ == '__main__':
    unittest.main()
