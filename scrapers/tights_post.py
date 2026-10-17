"""Stage 3: re-parse nutrition from the REST content HTML kept in list.jsonl (offline, no requests), add text-form parsing,
per-table variants, and derived per-100 g where only a per-unit value with known gram weight exists.
Input: data/raw/tights/fetched.jsonl (page fetch output of tights.py). Output: data/raw/tights/products.jsonl"""
import json, os, re, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tights_parse as P
from bs4 import BeautifulSoup

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
D = os.path.join(BASE, 'data/raw/tights')
LOG = os.path.join(BASE, 'logs/tights.log')

TXT_LABELS = [('energy', r'Energi(?:innhold)?'), ('fat', r'Fett'), ('saturated_fat', r'(?:hvorav\s+)?mettet(?:e)?(?:\s+fett(?:syrer)?)?'),
              ('carbs', r'Karbohydrat(?:er)?'), ('sugars', r'(?:hvorav\s+)?sukker(?:arter)?'), ('polyols', r'polyol(?:er)?'),
              ('fibre', r'Kostfiber|Fiber'), ('protein', r'Protein(?:er)?'), ('salt', r'Salt')]


def text_parse(content):
    soup = BeautifulSoup(content, 'html.parser')
    t = re.sub(r'\s+', ' ', soup.get_text(' ').replace('\xa0', ' '))
    m = re.search(r'(N.ringsinnhold|N.ringsverdi|Nutrition|Energi\s*:)', t, re.I)
    if not m: return None
    seg = t[m.start(): m.start() + 900]
    basis = 'per100' if re.search(r'per\s*100\s*(g|ml)', seg[:200], re.I) else ('serving' if re.search(r'per\s*(porsjon|dose|serving|stk|bar)', seg[:200], re.I) else None)
    out = {}
    for key, rx in TXT_LABELS:
        mm = re.search(r'(?<![A-Za-zæøå])(?:' + rx + r')\s*:?\s*(<?\s*\d+(?:[.,]\d+)?\s*(?:kcal|kJ|g|mg)\b(?:\s*(?:/|,|\()\s*<?\s*\d+(?:[.,]\d+)?\s*(?:kcal|kJ|g)\b\)?)?)', seg, re.I)
        if mm:
            out[key] = {'raw': mm.group(1), 'parsed': P.parse_value(mm.group(1))}
    if len(out) < 3: return None
    rows = [{'label': k, 'key': k, 'raw': [v['raw']], 'cols': {basis or 'unknown': v['parsed']}} for k, v in out.items()]
    return {'header': ['', {'per100': 'per 100 g (from text)', 'serving': 'serving (from text)', None: 'basis unknown (from text)'}[basis]], 'col_kinds': [basis or 'unknown'],
            'headerless_assumed_per100': basis is None, 'rows': rows, 'serving': None, 'nutritional': True, 'from_text': True}


def unit_weight_g(name, serving, weight_kg):
    """Grams of one 'unit' (bar/pose/dose) for a derived per-100 g, only when stated."""
    if serving and serving.get('size') and serving.get('unit') == 'g':
        return serving['size'], 'serving_header'
    return None, None


def main():
    L = {}
    for l in open(os.path.join(D, 'list.jsonl'), encoding='utf8'):
        d = json.loads(l); L[d['id']] = d
    out = open(os.path.join(D, 'products.jsonl'), 'w', encoding='utf8')
    stats = collections.Counter()
    for l in open(os.path.join(D, 'fetched.jsonl'), encoding='utf8'):
        r = json.loads(l)
        row = L.get(r['source_id'])
        flags = [f for f in r['flags'] if f in ('variants_share_one_nutrition_table', 'flavour_macros_may_differ_see_description')]
        content = row['content']['rendered']
        its = []
        for t in P.parse_tables(content):
            it = P.interpret_table(t); it['nutritional'] = P.looks_nutritional(it); its.append(it)
        nut = [i for i in its if i['nutritional']]
        if not nut:
            tp = text_parse(content)
            if tp: nut = [tp]; flags.append('nutrition_parsed_from_free_text')
        page_txt = re.sub(r'\s+', ' ', BeautifulSoup(content, 'html.parser').get_text(' '))
        ix = [m.start() for m in re.finditer(r'Energi|Protein|Karbohydrat|Fett', page_txt)]
        win = page_txt[max(0, ix[0] - 160): ix[0] + 60] if ix else ''
        has100 = re.search(r'(per|pr\.?)\s*100\s*(g|ml)', win, re.I)
        hasserv = re.search(r'(per|pr\.?)\s*(?!100\b)(\d+\s*(g|ml)|porsjon|dose|serving|stk|bar\b|pose|kapsel|tablett|skje|scoop|flaske|boks|can\b|glass|pakke|enhet|bit\b|kake|ts\b|tsk)', win, re.I)
        for i in nut:
            if i.get('headerless_assumed_per100') or 'unknown' in i['col_kinds']:
                if has100 and not hasserv:
                    i['col_kinds'] = ['per100' if k in ('unknown', 'per100') else k for k in i['col_kinds']]
                    for rw in i['rows']:
                        if 'unknown' in rw['cols']: rw['cols']['per100'] = rw['cols'].pop('unknown')
                    i['basis_from_page_text'] = True
                else:
                    i['basis_unverified'] = True
                    i['col_kinds'] = ['unknown' if k == 'per100' else k for k in i['col_kinds']]
                    for rw in i['rows']:
                        if 'per100' in rw['cols']: rw['cols']['unknown'] = rw['cols'].pop('per100')
        prim = next((i for i in nut if 'per100' in i['col_kinds']), nut[0] if nut else None)
        r['nutrition_tables'] = nut or None
        r['nutrition_per_100g'] = r['nutrition_per_serving'] = r['serving'] = r['nutrition'] = None
        r['nutrition_per_100g_derived'] = None
        if prim:
            if prim.get('basis_from_page_text'): flags.append('basis_per100g_taken_from_page_text')
            if prim.get('basis_unverified'):
                flags.append('basis_unverified_per_100g_or_per_serving')
                r['nutrition_unverified_basis'] = P.flatten(prim, 'unknown') or None
            p100 = P.flatten(prim, 'per100') or None
            psv = P.flatten(prim, 'serving') or None
            r['nutrition_per_100g'], r['nutrition_per_serving'], r['serving'] = p100, psv, prim['serving']
            if not p100:
                pp = P.flatten(prim, 'prepared')
                if pp: flags.append('only_prepared_product_values'); r['nutrition_prepared'] = pp
                g, basis = unit_weight_g(r['name'], prim['serving'], r['weight_kg'])
                if psv and g:
                    r['nutrition_per_100g_derived'] = {k: round(v * 100.0 / g, 4) if isinstance(v, float) and not k.endswith('_lt') else v for k, v in psv.items()}
                    r['derived_basis'] = {'serving_g': g, 'from': basis}
                    flags.append('per100g_derived_from_serving_size')
                elif psv:
                    flags.append('per_serving_only_no_gram_size')
                elif not pp:
                    flags.append('no_per100_column')
            if len(nut) > 1:
                flags.append('multiple_nutrition_tables')
                r['nutrition_by_table'] = [{'title': i['header'][0] if i['header'] else '', 'header': i['header'],
                                            'per_100g': P.flatten(i, 'per100') or None, 'per_serving': P.flatten(i, 'serving') or None} for i in nut]
            r['nutrition'] = {'per_100g': p100, 'per_serving': psv}
        else:
            kc = re.search(r'kcal|kJ', content, re.I)
            flags.append('nutrition_unparsed_text_or_image' if kc else 'no_nutrition_on_page')
        r['flags'] = flags
        stats['rows'] += 1
        for f in flags: stats['flag:' + f] += 1
        if r['nutrition_per_100g']: stats['with_per100'] += 1
        if r['nutrition_per_100g_derived']: stats['derived'] += 1
        if r['ean']: stats['ean'] += 1
        out.write(json.dumps(r, ensure_ascii=False) + '\n')
    out.close()
    open(LOG, 'a', encoding='utf8').write('stage3 parse stats ' + json.dumps(stats, ensure_ascii=False) + '\n')
    print(json.dumps(stats, indent=1))


if __name__ == '__main__':
    main()
