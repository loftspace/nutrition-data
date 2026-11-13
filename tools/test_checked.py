"""Store-checked fixes (checked.py): python -m unittest discover -s tools"""
import unittest

import checked

NUT = ('kcal', 'protein_g', 'fat_g', 'sat_fat_g', 'carbs_g', 'sugars_g', 'fibre_g', 'salt_g')


def row(i, name, kcal=100.0, **kw):
    p = {'id': i, 'name': name, 'brand': None, 'pack_size': None, 'ean': None, 'flavour': None,
         'category': 'other_food', 'serving_g': None, 'primary_source': 'norgesgruppen', 'status': 'from_source',
         'data_quality': None, **{n: 1.0 for n in NUT}}
    p['kcal'] = kcal
    p.update(kw)
    return p


class ApplyTest(unittest.TestCase):
    def setUp(self):
        self.kept = {i: row(i, n) for i, n in (('a', 'Meny Kjøttdeig'), ('b', 'Kjøttdeig 14%'), ('c', 'Norvegia'),
                                                ('d', 'Fiskekaker'), ('m', 'Old member'))}
        del self.kept['m']
        self.moved = {'m': 'a'}  # an earlier family moved m into a
        self.extra, self.units, self.stats = {}, {i: 'g' for i in self.kept}, {}
        self.flags = {i: [] for i in self.kept}

    def run_apply(self, data):
        return checked.apply(data, self.kept, self.moved, self.extra, self.flags, self.units, self.stats)

    def test_fold_moves_the_row_and_its_members(self):
        self.run_apply({'fold': [{'id': 'a', 'into': 'b', 'why': 'store meat'}]})
        self.assertNotIn('a', self.kept)
        self.assertEqual(self.moved, {'m': 'b', 'a': 'b'})
        self.assertIn('Meny Kjøttdeig', self.extra['b'])  # the old name still finds the row

    def test_fix_sets_numbers_name_category_sizes_and_flags_it(self):
        sizes, _ = self.run_apply({'fixes': [{'id': 'c', 'name': 'Norvegia Original', 'category': 'dairy_eggs',
                                              'sizes': ['500 g', '1 kg'], 'nutrients': {'kcal': 344, 'salt_g': 1.2},
                                              'source_url': 'https://meny.no/x'}]})
        c = self.kept['c']
        self.assertEqual((c['name'], c['category'], c['kcal'], c['salt_g']), ('Norvegia Original', 'dairy_eggs', 344, 1.2))
        self.assertEqual(sizes['c'], '500 g, 1 kg')
        self.assertIn('corrected_from_store', self.flags['c'])
        self.assertIn('Norvegia', self.extra['c'])  # the old name stays searchable

    def test_drop_add_and_common(self):
        sizes, common = self.run_apply({
            'drop': [{'id': 'd', 'why': 'salt 12.8 g'}],
            'add': [{'id': 'store:7038010016745', 'name': 'Norvegia Lett', 'brand': 'Norvegia', 'category': 'dairy_eggs',
                     'unit': 'g', 'sizes': ['150 g'], 'eans': ['7038010016745'], 'source': 'norgesgruppen',
                     'nutrients': {'kcal': 268, 'protein_g': 31, 'fat_g': 16, 'carbs_g': 0}, 'source_url': 'https://meny.no/y'}],
            'common': {'c': 3, 'store:7038010016745': 2, 'gone': 1},
        })
        self.assertNotIn('d', self.kept)
        added = self.kept['store:7038010016745']
        self.assertEqual((added['kcal'], added['ean'], added['salt_g']), (268, '7038010016745', None))  # unknown stays unknown
        self.assertEqual(sizes['store:7038010016745'], '150 g')
        self.assertEqual(common, {'c': 3, 'store:7038010016745': 2})

    def test_listings_of_a_dropped_row_are_not_redirected_to_nothing(self):
        self.run_apply({'drop': [{'id': 'a', 'why': 'broken'}]})
        self.assertNotIn('m', self.moved)

    def test_open_variant_takes_no_shop_numbers_or_shop_products(self):
        checked.apply({'fixes': [{'id': 'c', 'name': 'Norvegia Original', 'nutrients': {'kcal': 344}, 'source_url': 'u'}],
                       'add': [{'id': 'store:1', 'name': 'X', 'brand': 'B', 'category': 'dairy_eggs', 'unit': 'g', 'eans': ['1'],
                                'source': 'norgesgruppen', 'source_url': 'u',
                                'nutrients': {'kcal': 1, 'protein_g': 1, 'fat_g': 0, 'carbs_g': 0}}]},
                      self.kept, self.moved, self.extra, self.flags, self.units, self.stats, open_sources=('openfoodfacts',))
        self.assertEqual((self.kept['c']['name'], self.kept['c']['kcal']), ('Norvegia Original', 100.0))
        self.assertNotIn('store:1', self.kept)

    def test_an_all_zero_label_is_refused(self):
        self.run_apply({'fixes': [{'id': 'c', 'nutrients': {k: 0 for k in NUT}, 'source_url': 'u'}]})
        self.assertEqual(self.kept['c']['kcal'], 100.0)
        self.assertEqual(self.stats['checked_all_zero_refused'], 1)

    def test_an_added_product_takes_the_brand_spelling_in_use(self):
        self.kept['b']['brand'] = 'La Molisana'
        self.run_apply({'add': [{'id': 'store:2', 'name': 'Penne', 'brand': 'La molisana', 'category': 'bread_cereal_grain',
                                 'unit': 'g', 'eans': ['2'], 'source': 'norgesgruppen', 'source_url': 'u',
                                 'nutrients': {'kcal': 350, 'protein_g': 13, 'fat_g': 1.5, 'carbs_g': 70}}]})
        self.assertEqual(self.kept['store:2']['brand'], 'La Molisana')

    def test_a_restaurant_item_has_a_portion_and_no_barcode(self):
        self.run_apply({'add': [{'id': 'mcdonalds-no:big-mac', 'name': 'Big Mac', 'brand': "McDonald's", 'category': 'ready_meals_sauces',
                                 'unit': 'g', 'eans': [], 'serving_g': 215, 'derived': True, 'source': 'norgesgruppen',
                                 'source_url': 'u', 'nutrients': {'kcal': 240, 'protein_g': 12, 'fat_g': 12, 'carbs_g': 20}}]})
        r = self.kept['mcdonalds-no:big-mac']
        self.assertEqual((r['serving_g'], r['ean']), (215, None))
        self.assertIn('per100_derived_from_serving', self.flags['mcdonalds-no:big-mac'])

    def test_add_eans_attaches_barcodes_to_the_row(self):
        self.run_apply({'fixes': [{'id': 'c', 'add_eans': ['7038010016745'], 'source_url': 'u'}]})
        self.assertEqual(self.kept['c']['extra_eans'], ['7038010016745'])

    def test_a_menu_item_name_carries_its_chain(self):
        self.run_apply({'add': [{'id': 'godt-brod:kanelbolle', 'name': 'Kanelbolle', 'brand': 'Godt Brød', 'category': 'bread_cereal_grain', 'unit': 'g',
                                 'eans': [], 'menu': True, 'source': 'norgesgruppen', 'source_url': 'u',
                                 'nutrients': {'kcal': 350, 'protein_g': 7, 'fat_g': 12, 'carbs_g': 52}}]})
        self.assertEqual(self.kept['godt-brod:kanelbolle']['name'], 'Godt Brød Kanelbolle')

    def test_a_per_portion_item_keeps_its_printed_values(self):
        self.run_apply({'add': [{'id': 'burgerking-no:double-whopper', 'name': 'Double Whopper', 'brand': 'Burger King', 'category': 'ready_meals_sauces',
                                 'unit': 'portion', 'eans': [], 'menu': True, 'source': 'norgesgruppen', 'source_url': 'u',
                                 'nutrients': {'kcal': 1376, 'protein_g': 70, 'fat_g': 104, 'carbs_g': 40}}]})
        r = self.kept['burgerking-no:double-whopper']
        self.assertEqual((r['kcal'], r['fat_g'], self.units['burgerking-no:double-whopper']), (1376, 104, 'portion'))

    def test_take_eans_marks_barcodes_to_move(self):
        self.run_apply({'fixes': [{'id': 'c', 'take_eans': ['7038010058639'], 'source_url': 'u'}]})
        self.assertEqual(self.kept['c']['take_eans'], ['7038010058639'])

    def test_a_null_nutrient_becomes_unknown(self):
        self.run_apply({'fixes': [{'id': 'c', 'nutrients': {'fibre_g': None}, 'source_url': 'u'}]})
        self.assertIsNone(self.kept['c']['fibre_g'])

    def test_a_fix_for_a_missing_row_is_skipped_not_guessed(self):
        self.run_apply({'fixes': [{'id': 'zzz', 'nutrients': {'kcal': 1}, 'source_url': 'u'}],
                        'fold': [{'id': 'zzz', 'into': 'b'}]})
        self.assertEqual(self.stats['checked_skipped'], 2)
        self.assertEqual(self.stats['checked_fixed'], 0)

    def test_validate_refuses_what_it_cannot_trust(self):
        bad = [
            {'fixes': [{'id': 'c', 'nutrients': {'kcal': 1}}]},  # no source
            {'fixes': [{'id': 'c', 'category': 'cheese', 'source_url': 'u'}]},
            {'fixes': [{'id': 'c', 'nutrients': {'kcal': -1}, 'source_url': 'u'}]},
            {'add': [{'id': 'x', 'eans': ['1'], 'source_url': 'u', 'category': 'dairy_eggs', 'unit': 'g',
                      'nutrients': {'kcal': 1, 'protein_g': 1, 'fat_g': 1}}]},  # carbs unknown
            {'common': {'c': 5}},
        ]
        for data in bad:
            with self.assertRaises(ValueError, msg=data):
                checked.validate(data)


if __name__ == '__main__':
    unittest.main()
