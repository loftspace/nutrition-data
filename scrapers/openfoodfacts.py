"""Open Food Facts, Norway only, via the official Parquet bulk export (Hugging Face).
Filter: list_contains(countries_tags, 'en:norway'). Reads columns remotely (HTTP range), no images.
Writes data/raw/openfoodfacts/products.jsonl. Resume-safe: skips if output exists (use --force)."""
import duckdb, json, sys, os, time, datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, 'data', 'raw', 'openfoodfacts')
os.makedirs(OUT, exist_ok=True)
LOG = os.path.join(BASE, 'logs', 'openfoodfacts.log')
JSONL = os.path.join(OUT, 'products.jsonl')
URL = 'https://huggingface.co/datasets/openfoodfacts/product-database/resolve/main/food.parquet'


def log(m):
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(datetime.datetime.now().isoformat(timespec='seconds') + ' ' + m + '\n')
    print(m, flush=True)


if os.path.exists(JSONL) and '--force' not in sys.argv:
    log('products.jsonl exists, skipping (use --force)')
    sys.exit(0)
# Remote range-reads proved very slow (>1 h); the full 8 GB file downloads in ~2 min, so: curl it to a
# temp dir outside the library (deleted afterwards) and pass its path: openfoodfacts.py --local <path>
if '--local' in sys.argv:
    URL = sys.argv[sys.argv.index('--local') + 1].replace('\\', '/')
log('start; source=' + URL)
c = duckdb.connect()
c.execute('install httpfs; load httpfs')
FILTER = "list_contains(countries_tags,'en:norway')"
sql = ("select code, brands, quantity, product_quantity, product_quantity_unit, serving_size, serving_quantity, "
       "nutrition_data_per, no_nutrition_data, categories, categories_tags, ingredients_text, allergens_tags, traces_tags, "
       "nutriscore_grade, nutriscore_score, nova_group, additives_tags, labels_tags, stores, countries_tags, lang, "
       "product_name, generic_name, nutriments, last_modified_t, created_t, obsolete, completeness "
       "from read_parquet('" + URL + "') where " + FILTER)
t = time.time()
cur = c.execute(sql)
cols = [d[0] for d in cur.description]
n = 0
withn = 0
fetched = datetime.date.today().isoformat()
tmp = JSONL + '.tmp'


def pick(arr, pref):
    return (next((x['text'] for x in arr if x['lang'] == pref and x['text']), None)
            or next((x['text'] for x in arr if x['text']), None))


with open(tmp, 'w', encoding='utf-8') as f:
    while True:
        rows = cur.fetchmany(5000)
        if not rows:
            break
        for r in rows:
            d = dict(zip(cols, r))
            names = d.pop('product_name') or []
            nut = d.pop('nutriments') or []
            ing = d.pop('ingredients_text') or []
            gen = d.pop('generic_name') or []
            rec = {
                'source': 'openfoodfacts', 'ean': d['code'],
                'source_url': 'https://world.openfoodfacts.org/product/' + str(d['code']),
                'fetched_on': fetched,
                'name': pick(names, 'no') or pick(names, 'nb') or pick(names, 'main'),
                'names_by_lang': {x['lang']: x['text'] for x in names if x['text']},
                'generic_name': pick(gen, 'no'),
                'ingredients_text': pick(ing, 'no') or pick(ing, d['lang'] or 'main'),
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
os.replace(tmp, JSONL)
log('done: %d products, %d with nutrients, %.0fs; filter=%s; requests: DuckDB HTTP range reads, no per-product requests'
    % (n, withn, time.time() - t, FILTER))
