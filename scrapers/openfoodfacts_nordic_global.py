"""Open Food Facts, second pass: (a) ALL products with country Sweden or Denmark, (b) protein/supplement-like
products from every other country (incl. UK, US). Source: official Parquet bulk export, passed as a LOCAL copy
(--local <path>, downloaded once to a temp dir outside the library, deleted afterwards). No per-product requests.
Same record fields as scrapers/openfoodfacts.py, plus 'selection'. Products whose EAN is already in
data/raw/openfoodfacts/products.jsonl (Norway) are dropped. Output: data/raw/openfoodfacts-nordic-global/products.jsonl.
Usage: openfoodfacts_nordic_global.py --local <food.parquet> [--test 5] [--force]"""
import duckdb, json, sys, os, time, datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, 'data', 'raw', 'openfoodfacts-nordic-global')
os.makedirs(OUT, exist_ok=True)
LOG = os.path.join(BASE, 'logs', 'openfoodfacts-nordic-global.log')
JSONL = os.path.join(OUT, 'products.jsonl')
NO_JSONL = os.path.join(BASE, 'data', 'raw', 'openfoodfacts', 'products.jsonl')


def log(m):
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(datetime.datetime.now().isoformat(timespec='seconds') + ' ' + m + '\n')
    print(m, flush=True)


if os.path.exists(JSONL) and '--force' not in sys.argv and '--test' not in sys.argv:
    log('products.jsonl exists, skipping (use --force)')
    sys.exit(0)
URL = sys.argv[sys.argv.index('--local') + 1].replace('\\', '/')
TEST = int(sys.argv[sys.argv.index('--test') + 1]) if '--test' in sys.argv else 0

# category tags that mark protein / supplement / sports-nutrition products (lower-cased tag, regex)
CAT_RE = (r"^en:(.*(supplement|protein-powder|protein-bar|protein-shake|protein-drink|protein-energy|protein-ball|"
          r"bodybuilding|bcaa|creatine|amino-acid|pre-workout|preworkout|energy-drink|energy-gel|energy-bar|"
          r"sports?-drink|sports?-nutrition|dietary-drink-for-sport|meal-replacement|electrolyte|isotonic|"
          r"whey-protein|casein|collagen|nutritional-shake|weight-gain|mass-gainer|recovery-drink|proteinpulver|"
          r"proteinriegel|barras-de-proteina|proteinas-en-polvo|bebidas-isotonicas).*"
          r"|protein|proteinas|proteina|whey|shake|nutrition-bar|protein-supplement)$"
          r"|^(nl:(sportvoeding|proteine-eiwit-poeders|voedingssupplement|sportdrank)|fr:produits-pour-sportifs|"
          r"es:(proteinas|proteina)|de:(proteinriegel|proteinpulver|nahrungserganzungsmittel))$")
CAT_COND = "len(list_filter(categories_tags, t -> regexp_matches(lower(t), '%s'))) > 0" % CAT_RE.replace("'", "''")
NORDIC = "(list_contains(countries_tags,'en:sweden') or list_contains(countries_tags,'en:denmark'))"
FILTER = "(%s or %s)" % (NORDIC, CAT_COND)

log('start; source=' + URL + '; test=%d' % TEST)
no_eans = set()
with open(NO_JSONL, encoding='utf-8') as f:
    for line in f:
        no_eans.add(json.loads(line)['ean'])
log('existing Norway OFF eans: %d' % len(no_eans))

c = duckdb.connect()
sql = ("select code, brands, quantity, product_quantity, product_quantity_unit, serving_size, serving_quantity, "
       "nutrition_data_per, no_nutrition_data, categories, categories_tags, ingredients_text, allergens_tags, traces_tags, "
       "nutriscore_grade, nutriscore_score, nova_group, additives_tags, labels_tags, stores, countries_tags, lang, "
       "product_name, generic_name, nutriments, last_modified_t, created_t, obsolete, completeness, "
       "%s as is_nordic, %s as is_cat "
       "from read_parquet('%s') where %s and code is not null" % (NORDIC, CAT_COND, URL, FILTER))
t = time.time()
cur = c.execute(sql)
cols = [d[0] for d in cur.description]
fetched = datetime.date.today().isoformat()
tmp = JSONL + '.tmp' if not TEST else os.path.join(OUT, 'test.jsonl.tmp')
PREF = ['en', 'sv', 'da', 'no', 'main']


def pick(arr, prefs):
    for p in prefs:
        v = next((x['text'] for x in arr if x['lang'] == p and x['text']), None)
        if v:
            return v
    return next((x['text'] for x in arr if x['text']), None)


n = withn = skipped_no = 0
seen = set()
stats = {'nordic': 0, 'cat_only': 0}
with open(tmp, 'w', encoding='utf-8') as f:
    while True:
        rows = cur.fetchmany(5000)
        if not rows:
            break
        for r in rows:
            d = dict(zip(cols, r))
            if d['code'] in no_eans:
                skipped_no += 1
                continue
            if d['code'] in seen:
                continue
            seen.add(d['code'])
            names = d.pop('product_name') or []
            nut = d.pop('nutriments') or []
            ing = d.pop('ingredients_text') or []
            gen = d.pop('generic_name') or []
            sel = []
            if d.pop('is_nordic'):
                sel.append('sweden_or_denmark')
            if d.pop('is_cat'):
                sel.append('protein_supplement_category')
            stats['nordic' if 'sweden_or_denmark' in sel else 'cat_only'] += 1
            rec = {
                'source': 'openfoodfacts-nordic-global', 'ean': d['code'],
                'source_url': 'https://world.openfoodfacts.org/product/' + str(d['code']),
                'fetched_on': fetched, 'selection': sel,
                'name': pick(names, PREF),
                'names_by_lang': {x['lang']: x['text'] for x in names if x['text']},
                'generic_name': pick(gen, PREF),
                'ingredients_text': pick(ing, [d['lang'] or 'main'] + PREF),
                'ingredients_by_lang': {x['lang']: x['text'] for x in ing if x['text']},
                'brand': d['brands'], 'pack_size': d['quantity'], 'product_quantity': d['product_quantity'],
                'product_quantity_unit': d['product_quantity_unit'], 'serving_size': d['serving_size'],
                'serving_quantity': d['serving_quantity'], 'nutrition_data_per': d['nutrition_data_per'],
                'categories': d['categories'], 'categories_tags': d['categories_tags'],
                'allergens_tags': d['allergens_tags'], 'traces_tags': d['traces_tags'],
                'nutriscore_grade': d['nutriscore_grade'], 'nutriscore_score': d['nutriscore_score'],
                'nova_group': d['nova_group'], 'additives_tags': d['additives_tags'], 'labels_tags': d['labels_tags'],
                'stores': d['stores'], 'countries_tags': d['countries_tags'], 'lang': d['lang'],
                'obsolete': d['obsolete'], 'completeness': d['completeness'],
                'last_modified_t': d['last_modified_t'], 'created_t': d['created_t'],
            }
            nd = {}
            for x in nut:
                if x['name'] is None:
                    continue
                e = {'per_100g': x['100g'], 'per_serving': x['serving'], 'unit': x['unit'],
                     'as_entered_value': x['value'], 'prepared_per_100g': x['prepared_100g'],
                     'prepared_per_serving': x['prepared_serving'], 'prepared_unit': x['prepared_unit']}
                nd[x['name']] = {k: v for k, v in e.items() if v is not None}
            if nd:
                rec['nutrition'] = nd
                rec['nutrition_basis'] = 'per_100g as normalised by OFF; unit in each entry (energy-kcal=kcal, energy=kJ, salt/sodium=g)'
                withn += 1
            else:
                rec['nutrition'] = None
                rec['flag'] = 'no_nutrition_in_off'
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
            n += 1
            if TEST and n >= TEST:
                break
        if TEST and n >= TEST:
            break
if not TEST:
    os.replace(tmp, JSONL)
log('done: %d products (%d sweden/denmark, %d category-only), %d with nutrients, %d dropped as already in Norway set, %.0fs; filter=%s'
    % (n, stats['nordic'], stats['cat_only'], withn, skipped_no, time.time() - t, FILTER))
