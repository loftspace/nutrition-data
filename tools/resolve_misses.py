"""Turn the products Makro users could not find into a review list (nutrition-data #3, Makro #13).

Makro's submit-miss function stores anonymous misses in the Supabase table public.misses: a scanned
barcode with no match, a search or voice phrase with no match, a food the user made for a missing
barcode, or a "wrong value" report. This tool reads them and writes data/review/<date>-misses.json:

  barcodes      one entry per barcode, most reported first. If kassal.app has the product, a candidate
                in the data/checked.json "add" shape, numbers copied from the shop label. category is
                left empty: a person picks it, then moves the candidate into checked.json.
  searches      phrases with no match, most frequent first (a missing food, or a search fix).
  wrong_values  products users said have wrong numbers, for a label check.

Nothing is added to the database automatically. A user's own food is shown for context and never
becomes a candidate (accuracy rule 1: numbers come only from a label or the product database).

No API key can read the miss table (by design: submit-miss may only write). Export it as a person
with SQL (Supabase SQL editor, or the CLI against the database), save the rows as a JSON array:
  select type, ean, query_text, custom_food, product_id, country, created_at from public.misses order by created_at;
Then:
  python tools/resolve_misses.py --misses misses.json --db path/to/products.sqlite [--no-lookup]
The export holds no user ids, but keep it out of the repo all the same.
"""
import argparse
import collections
import datetime
import json
import os
import sqlite3
import sys

NUTRIENTS = ('kcal', 'protein_g', 'fat_g', 'sat_fat_g', 'carbs_g', 'sugars_g', 'fibre_g', 'salt_g')
# kassal.app label names (per 100 g or ml) to our nutrient keys.
LABEL_KEYS = {'kalorier': 'kcal', 'protein': 'protein_g', 'fett': 'fat_g', 'mettet fett': 'sat_fat_g',
              'karbohydrater': 'carbs_g', 'sukkerarter': 'sugars_g', 'kostfiber': 'fibre_g', 'salt': 'salt_g'}


def canonical_ean(e):
    e = ''.join(c for c in (e or '') if c.isdigit())
    if len(e) == 14 and e[0] == '0':
        e = e[1:]
    return e.zfill(13) if 0 < len(e) < 13 else e


def norm_query(q):
    return ' '.join((q or '').lower().split())


def candidate(ean, label):
    """The checked.json add entry for a kassal.app product, or None when the label lacks the main numbers."""
    if not isinstance(label, dict):
        return None
    n = {k: None for k in NUTRIENTS}
    for it in label.get('nutrition') or ():
        k = LABEL_KEYS.get((it.get('name') or '').strip().lower())
        if k and isinstance(it.get('amount'), (int, float)):
            n[k] = it['amount']
    if any(n[k] is None for k in ('kcal', 'protein_g', 'fat_g', 'carbs_g')):
        return None
    wu = (label.get('weight_unit') or '').lower()
    size = '%s %s' % (label['weight'], wu) if label.get('weight') and wu else None
    return {'id': 'store:' + ean, 'name': label.get('name'), 'brand': label.get('brand') or label.get('vendor'),
            'category': None, 'unit': 'ml' if wu in ('l', 'ml', 'cl', 'dl') else 'g', 'sizes': [size] if size else [],
            'eans': [ean], 'source': 'kassalapp', 'source_url': 'https://kassal.app (barcode %s)' % ean, 'nutrients': n}


def resolve(misses, known, lookup):
    """Group misses into the review list. known: barcodes the current database has; lookup(ean) -> kassal product or None."""
    stats = collections.Counter(misses=len(misses))
    by_ean = collections.OrderedDict()
    searches, wrong = collections.Counter(), collections.Counter()
    for m in misses:
        e = canonical_ean(m.get('ean'))
        if m['type'] == 'wrong_value':
            if m.get('product_id'):
                wrong[m['product_id']] += 1
            continue
        if e:
            b = by_ean.setdefault(e, {'ean': e, 'count': 0, 'types': collections.Counter(), 'user_foods': []})
            b['count'] += 1
            b['types'][m['type']] += 1
            if m.get('custom_food'):
                b['user_foods'].append(m['custom_food'])
        elif m.get('query_text'):
            searches[norm_query(m['query_text'])] += 1
    barcodes = []
    for e, b in sorted(by_ean.items(), key=lambda kv: (-kv[1]['count'], kv[0])):
        if e in known:
            stats['already_in_database'] += 1
            continue
        c = candidate(e, lookup(e))
        stats['with_candidate' if c else 'no_candidate'] += 1
        barcodes.append(dict(b, types=dict(b['types']), candidate=c))
    return {'stats': dict(stats), 'barcodes': barcodes,
            'searches': [{'query': q, 'count': n} for q, n in sorted(searches.items(), key=lambda kv: (-kv[1], kv[0]))],
            'wrong_values': [{'product_id': p, 'count': n} for p, n in sorted(wrong.items(), key=lambda kv: (-kv[1], kv[0]))]}


def kassal_lookup():
    """get_product by barcode on kassal.app's keyless MCP endpoint (rate-limited client in scrapers/)."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scrapers'))
    from kassalapp import Mcp  # noqa: E402
    m = Mcp()

    def look(ean):
        d, _err = m.call('get_product', {'ean': ean})
        return d if isinstance(d, dict) else None
    return look


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--db', required=True, help='the current products.sqlite (barcodes it has count as resolved)')
    ap.add_argument('--misses', required=True, help='JSON array of public.misses rows (see above)')
    ap.add_argument('--no-lookup', action='store_true', help='do not ask kassal.app')
    ap.add_argument('--out', help='default data/review/<today>-misses.json')
    a = ap.parse_args(argv)
    db = sqlite3.connect('file:%s?mode=ro' % os.path.abspath(a.db), uri=True)
    known = {e for (e,) in db.execute('select ean from product_eans')}
    lookup = (lambda e: None) if a.no_lookup else kassal_lookup()
    with open(a.misses, encoding='utf-8') as f:
        misses = json.load(f)
    out = resolve(misses, known, lookup)
    path = a.out or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'review',
                                 '%s-misses.json' % datetime.date.today().isoformat())
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(out['stats'], '->', path)


if __name__ == '__main__':
    main()
