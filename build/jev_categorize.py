"""Categorize products with Jev (TypeSafe System One). Approved by Max for: a 300-product test, then the full run.
Usage:  python -I build/jev_categorize.py test            # 300 random Norway-relevant products
        python -I build/jev_categorize.py full            # all Norway-relevant products (resumes)
        python -I build/jev_categorize.py stage2          # supplements only: single-ingredient / merge group
Output: data/jev/stage1.jsonl, data/jev/stage2.jsonl (append-only, resume-safe), data/jev/usage.json.
Sends per product: name, brand, shop category labels, pack size, per-100 g macros (+ ingredients snippet in stage 2). Key from env TYPESAFE_API_KEY, never printed."""
import json, os, random, sqlite3, sys, threading, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = ROOT + '/data/unified/products.sqlite'
OUT = ROOT + '/data/jev'
os.makedirs(OUT, exist_ok=True)
URL = 'https://api.typesafe.ai/v1/systemone'
KEY = os.environ.get('TYPESAFE_API_KEY')
WORKERS = 8
lock = threading.Lock()
usage = {'requests': 0, 'input_tokens': 0, 'errors': 0}

CATEGORIES = {
    'protein_powder': 'Whey, casein, plant or blended protein powder (not a bar, not a ready drink)',
    'protein_bar': 'Protein bar, protein snack bar, protein cookie or wafer, protein chips',
    'protein_drink_or_dessert': 'Ready-to-drink protein shake, protein yoghurt/pudding/milk',
    'mass_gainer_meal_replacement': 'Weight gainer, meal replacement shake or powder',
    'creatine': 'Creatine in any form (monohydrate, HCl, blends sold as creatine)',
    'pre_workout': 'Pre-workout or stimulant energy powder/capsules with caffeine and similar',
    'amino_acids': 'BCAA, EAA, glutamine, citrulline, beta-alanine, single or mixed amino acids',
    'vitamin_mineral': 'Vitamins, minerals, multivitamin, magnesium, zinc, D3, iron and similar supplements',
    'omega3_oils': 'Fish oil, omega-3, krill oil, cod liver oil',
    'collagen_joint': 'Collagen, joint support, glucosamine, MSM',
    'fat_burner_weight_loss': 'Fat burners, thermogenics, weight-loss aids, appetite control supplements',
    'herbal_other_supplement': 'Probiotics, adaptogens, herbal extracts, other supplements that fit nothing above',
    'energy_gel_sports_drink': 'Energy gels, electrolyte or sports drink powders/ready drinks, energy drinks',
    'dairy_eggs': 'Milk, cheese, yoghurt, cream, butter, eggs (not protein-branded supplements)',
    'meat_fish': 'Meat, poultry, fish, seafood, deli meats, vegetarian meat substitutes',
    'bread_cereal_grain': 'Bread, cereal, oats, muesli, pasta, rice, flour, grains',
    'fruit_vegetables': 'Fresh/frozen/canned fruit and vegetables, nuts, legumes',
    'snacks_sweets': 'Chocolate, candy, chips, biscuits, ice cream, cakes, desserts',
    'drinks': 'Soft drinks, juice, water, coffee, tea, beer/wine (not sports/energy supplements)',
    'ready_meals_sauces': 'Ready meals, soups, pizza, sauces, spreads, spices, oils, cooking ingredients',
    'other_food': 'Edible but fits none of the food groups above',
    'non_food': 'Clothing, equipment, shaker, cosmetics, pet food, household or gift cards',
}


def load_products(limit=None, seed=1):
    c = sqlite3.connect('file:%s?mode=ro' % DB, uri=True)
    c.row_factory = sqlite3.Row
    rows = c.execute("select id,name,brand,pack_size,categories,ingredients,kcal,protein_g,fat_g,carbs_g,primary_source from products where norway_relevant=1 order by id").fetchall()
    rows = [dict(r) for r in rows]
    if limit:
        random.Random(seed).shuffle(rows)
        rows = rows[:limit]
    return rows


def state_for(r, with_ingredients=False):
    try:
        cats = json.loads(r['categories'] or '[]')[:6]
    except Exception:
        cats = []
    s = {'name': (r['name'] or '')[:200], 'brand': r['brand'], 'shop_category_labels': cats, 'pack_size': r['pack_size'],
         'per_100g': {'kcal': r['kcal'], 'protein_g': r['protein_g'], 'fat_g': r['fat_g'], 'carbs_g': r['carbs_g']}}
    if with_ingredients and r.get('ingredients'):
        s['ingredients'] = r['ingredients'][:600]
    return {k: v for k, v in s.items() if v not in (None, [], '')}


Q1 = {
    'category': {'type': 'choice', 'instructions': 'Which category best describes this product? Use name, brand, shop category labels and macros.',
                 'criteria': CATEGORIES},
    'is_supplement': {'type': 'noul', 'instructions': 'Is this a dietary or sports supplement (protein powder, creatine, pre-workout, vitamins, amino acids, etc.) rather than ordinary food?'},
}
Q2 = {
    'is_single_active_ingredient': {'type': 'noul', 'instructions': 'Is this supplement essentially ONE plain active ingredient (for example only creatine monohydrate powder, only caffeine, only one amino acid), without flavours, sweeteners, blends or other actives?'},
    'ingredient_group': {'type': 'choice', 'instructions': 'If the product is a single plain active ingredient, which one? Otherwise choose not_single.',
                         'criteria': {'creatine_monohydrate': 'Plain creatine monohydrate (including Creapure)', 'creatine_other': 'Creatine HCl, ethyl ester, blends or capsules with other things',
                                      'caffeine': None, 'beta_alanine': None, 'citrulline': None, 'glutamine': None, 'bcaa': None, 'eaa': None, 'taurine': None,
                                      'vitamin_d': None, 'vitamin_c': None, 'magnesium': None, 'zinc': None, 'omega3': None, 'collagen': None, 'whey_protein_plain': 'Plain unflavoured whey protein',
                                      'other_single': 'A single plain ingredient not listed', 'not_single': 'Blend, flavoured product or not a supplement'}},
}


def call(state, questions, tries=6):
    body = json.dumps({'state': state, 'model': 'jev-latest', 'questions': questions}).encode()
    for i in range(tries):
        req = urllib.request.Request(URL, body, {'Authorization': 'Bearer ' + KEY, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                d = json.loads(resp.read())
            with lock:
                usage['requests'] += 1
                usage['input_tokens'] += d.get('usage', {}).get('input_tokens', 0)
            return d
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(min(60, 2 ** i + random.random()))
                continue
            with lock:
                usage['errors'] += 1
            return {'error': 'http %d' % e.code}
        except Exception as e:
            time.sleep(min(30, 2 ** i))
    with lock:
        usage['errors'] += 1
    return {'error': 'failed after retries'}


def run(rows, path, questions, with_ingredients):
    done = set()
    if os.path.exists(path):
        for l in open(path, encoding='utf-8'):
            try:
                done.add(json.loads(l)['id'])
            except Exception:
                pass
    todo = [r for r in rows if r['id'] not in done]
    print('to do', len(todo), 'already', len(done), flush=True)
    f = open(path, 'a', encoding='utf-8')
    n = [0]

    def work(r):
        d = call(state_for(r, with_ingredients), questions)
        if 'answers' not in d:
            return
        a = d['answers']
        rec = {'id': r['id']}
        for k, v in a.items():
            if v.get('type') == 'choice':
                rec[k] = v['choice']; rec[k + '_conf'] = round(v.get('confidence', 0), 3)
                rec[k + '_top2'] = sorted(v['probabilities'].items(), key=lambda x: -x[1])[:2]
            else:
                rec[k] = round(v.get('noul', 0), 3)
        with lock:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n'); f.flush()
            n[0] += 1
            if n[0] % 1000 == 0:
                print(n[0], dict(usage), flush=True)
                json.dump(usage, open(OUT + '/usage.json', 'w'))

    with ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(work, todo))
    f.close()
    json.dump(usage, open(OUT + '/usage.json', 'w'))
    print('finished', dict(usage), flush=True)


if __name__ == '__main__':
    if not KEY:
        sys.exit('TYPESAFE_API_KEY not set')
    mode = sys.argv[1]
    if mode == 'test':
        run(load_products(300), OUT + '/stage1_test.jsonl', Q1, False)
    elif mode == 'full':
        run(load_products(), OUT + '/stage1.jsonl', Q1, False)
    elif mode == 'stage2':
        sup = {json.loads(l)['id'] for l in open(OUT + '/stage1.jsonl', encoding='utf-8')
               if (lambda x: x['is_supplement'] > 0.5 or x['category'] in ('creatine', 'amino_acids', 'vitamin_mineral', 'pre_workout', 'omega3_oils', 'collagen_joint',
                                                                      'fat_burner_weight_loss', 'herbal_other_supplement'))(json.loads(l))}
        run([r for r in load_products() if r['id'] in sup], OUT + '/stage2.jsonl', Q2, True)
