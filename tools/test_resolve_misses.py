"""Tests for resolve_misses.py: missing products reported by Makro become a review list (nutrition-data #3)."""
import unittest

import resolve_misses as rm


def miss(type_, ean=None, q=None, food=None, pid=None):
    return {'type': type_, 'ean': ean, 'query_text': q, 'custom_food': food, 'product_id': pid, 'country': 'NO'}


LABEL = {'name': 'Tine Lettmelk', 'brand': 'Tine', 'weight': 1, 'weight_unit': 'l', 'nutrition': [
    {'name': 'Kalorier', 'amount': 38, 'unit': 'kcal'}, {'name': 'Fett', 'amount': 0.5, 'unit': 'g'},
    {'name': 'Karbohydrater', 'amount': 4.5, 'unit': 'g'}, {'name': 'Protein', 'amount': 3.5, 'unit': 'g'},
    {'name': 'Salt', 'amount': 0.1, 'unit': 'g'}]}


class Resolve(unittest.TestCase):
    def run_it(self, misses, known=(), labels=None):
        labels = labels or {}
        return rm.resolve(misses, known=set(known), lookup=lambda e: labels.get(e))

    def test_scans_group_by_barcode_and_count(self):
        out = self.run_it([miss('scan_not_found', '7038010000010'), miss('scan_not_found', '07038010000010'),
                           miss('scan_not_found', '7038010000027')])
        self.assertEqual([(c['ean'], c['count']) for c in out['barcodes']], [('7038010000010', 2), ('7038010000027', 1)])

    def test_a_barcode_the_database_has_now_is_resolved(self):
        out = self.run_it([miss('scan_not_found', '7038010000010')], known={'7038010000010'})
        self.assertEqual(out['barcodes'], [])
        self.assertEqual(out['stats']['already_in_database'], 1)

    def test_a_shop_label_becomes_a_candidate_with_numbers_copied(self):
        out = self.run_it([miss('scan_not_found', '7038010000010')], labels={'7038010000010': LABEL})
        c = out['barcodes'][0]['candidate']
        self.assertEqual(c['name'], 'Tine Lettmelk')
        self.assertEqual(c['nutrients']['kcal'], 38)
        self.assertIsNone(c['nutrients']['fibre_g'])  # not on the label: unknown, never 0
        self.assertEqual(c['unit'], 'ml')
        self.assertIsNone(c['category'])  # a person picks it

    def test_a_label_without_the_four_main_numbers_is_no_candidate(self):
        bare = dict(LABEL, nutrition=[{'name': 'Kalorier', 'amount': 38, 'unit': 'kcal'}])
        out = self.run_it([miss('scan_not_found', '7038010000010')], labels={'7038010000010': bare})
        self.assertIsNone(out['barcodes'][0]['candidate'])

    def test_a_users_own_food_is_shown_but_never_a_candidate(self):
        food = {'name': 'Mammas boller', 'nutrients': {'kcal': 300}}
        out = self.run_it([miss('photo_custom', '7038010000010', food=food)])
        b = out['barcodes'][0]
        self.assertIsNone(b['candidate'])
        self.assertEqual(b['user_foods'], [food])

    def test_searches_rank_by_count_after_normalising(self):
        out = self.run_it([miss('search_no_match', q='Brunost '), miss('search_no_match', q='brunost'),
                           miss('voice_no_match', q='kvarg')])
        self.assertEqual([(s['query'], s['count']) for s in out['searches']], [('brunost', 2), ('kvarg', 1)])

    def test_wrong_value_reports_list_the_product(self):
        out = self.run_it([miss('wrong_value', pid='ean:7038010000010'), miss('wrong_value', pid='ean:7038010000010')])
        self.assertEqual(out['wrong_values'], [{'product_id': 'ean:7038010000010', 'count': 2}])


if __name__ == '__main__':
    unittest.main()
