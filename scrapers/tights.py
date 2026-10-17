"""Stage 2: fetch each tights.no product page (1 req/s), merge with REST content, parse nutrition tables.
Output: data/raw/tights/products.jsonl (resume-safe by product id). Run tights_list.py first."""
import requests, json, re, os, sys, time, html
from bs4 import BeautifulSoup
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tights_parse as P

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
D = os.path.join(BASE, 'data/raw/tights')
OUT = os.path.join(D, 'products.jsonl'); LOG = os.path.join(BASE, 'logs/tights.log')
UA = "macro-library-personal/1.0 (single-user personal research; github.com/Maxaubert)"
S = requests.Session(); S.headers['User-Agent'] = UA
LAST = [0.0]; REQ = [0]


def log(m):
    open(LOG, 'a', encoding='utf8').write(time.strftime('%F %T ') + m + '\n'); print(m, flush=True)


def get(url):
    for a in range(6):
        w = 1.05 - (time.time() - LAST[0])
        if w > 0: time.sleep(w)
        LAST[0] = time.time(); REQ[0] += 1
        try:
            r = S.get(url, timeout=60)
        except requests.RequestException as e:
            log(f'ERR {e} {url}'); time.sleep(2 ** a * 2); continue
        if r.status_code in (200, 404, 410): return r
        log(f'HTTP {r.status_code} {url}')
        if r.status_code in (401, 403) and a >= 2:
            raise SystemExit('blocked ' + url)
        time.sleep(2 ** a * 3)
    raise SystemExit('too many failures ' + url)


def sitemap_urls():
    urls = set()
    for i in (1, 2):
        r = get(f'https://www.tights.no/wp-sitemap-posts-product-{i}.xml')
        urls |= set(re.findall(r'<loc>([^<]+)</loc>', r.text))
    return urls


def clean(t):
    return re.sub(r'\s+', ' ', t.replace('\xa0', ' ')).strip()


def page_data(h):
    soup = BeautifulSoup(h, 'html.parser')
    d = {}
    for s in soup.find_all('script', type='application/ld+json'):
        try:
            j = json.loads(s.string)
        except Exception:
            continue
        for g in j.get('@graph', []):
            if g.get('@type') == 'Product':
                d['gtin'] = g.get('gtin13') or g.get('gtin') or g.get('gtin12') or g.get('gtin8')
                d['mpn'] = g.get('mpn')
                d['sku'] = g.get('sku')
                d['brand'] = (g.get('brand') or {}).get('name')
                d['name'] = html.unescape(g.get('name', ''))
                d['weight_kg'] = (g.get('weight') or {}).get('value')
                d['category_ld'] = g.get('category')
            if g.get('@type') == 'BreadcrumbList':
                d['breadcrumb'] = [html.unescape(html.unescape(i['item']['name'])) for i in g['itemListElement'][1:-1]]
    f = soup.find('form', class_='variations_form')
    if f and f.get('data-product_variations'):
        try:
            vs = json.loads(html.unescape(f['data-product_variations']))
            d['variants'] = [{'variation_id': v['variation_id'], 'sku': v.get('sku'), 'attributes': v['attributes'],
                              'weight_kg': v.get('weight'), 'in_stock': v.get('is_in_stock')} for v in vs]
        except Exception:
            pass
    # variation attribute labels (slug -> display)
    labs = {}
    if f:
        for sel in f.find_all('select'):
            for o in sel.find_all('option'):
                if o.get('value'): labs[(sel.get('name'), o['value'])] = clean(o.get_text())
    for v in d.get('variants', []):
        v['labels'] = {k.replace('attribute_', ''): labs.get((k, val), val) for k, val in v['attributes'].items()}
    # attributes table (additional information)
    attrs = {}
    for tr in soup.select('table.woocommerce-product-attributes tr'):
        th, td = tr.find('th'), tr.find('td')
        if th and td: attrs[clean(th.get_text())] = clean(td.get_text())
    d['attributes'] = attrs
    m = soup.find(class_='meta-expired-date')
    if m: d['best_before_note'] = clean(m.get_text())
    return d


def text_after(content_html, word):
    soup = BeautifulSoup(content_html, 'html.parser')
    txt = clean(soup.get_text(' '))
    m = re.search('(?:' + word + r')' + r'\s*:?\s*(.{5,1500}?)(?=\s(?:Allergener|Advarsel|Produsent|Oppbevaring|Bruksanvisning|Anbefalt|Tilberedning|N.ringsinnhold|Importert|Opprinnelsesland)\b|$)', txt, re.I)
    return m.group(1).strip() if m else None


def build(row, pd, in_sitemap, status):
    content = row['content']['rendered']
    tables = P.parse_tables(content)
    interps = []
    for t in tables:
        it = P.interpret_table(t)
        it['nutritional'] = P.looks_nutritional(it)
        interps.append(it)
    nut = [i for i in interps if i['nutritional']]
    flags = []
    rec = {
        'source': 'tights', 'source_id': row['id'], 'source_url': row['link'], 'fetched_on': time.strftime('%F'),
        'in_sitemap': in_sitemap, 'page_status': status,
        'name': pd.get('name') or html.unescape(row['title']['rendered']),
        'brand': pd.get('brand') or next((c[len('product_brand-'):] for c in row['class_list'] if c.startswith('product_brand-')), None),
        'ean': pd.get('gtin'), 'sku': pd.get('sku'), 'weight_kg': pd.get('weight_kg'),
        'categories': pd.get('breadcrumb'), 'category_ids': row['product_cat'],
        'category_slugs': [c[len('product_cat-'):] for c in row['class_list'] if c.startswith('product_cat-')],
        'variants': pd.get('variants'), 'attributes': pd.get('attributes'),
        'ingredients': text_after(content, r'Ingredienser|Ingredients|Innholdsfortegnelse'),
        'allergens': text_after(content, r'Allergener|Allergi'),
        'description_text': clean(BeautifulSoup(content, 'html.parser').get_text(' '))[:4000],
    }
    rec['nutrition_tables'] = nut if nut else None
    # primary table: first nutritional table with a per100 column, else first nutritional
    prim = next((i for i in nut if 'per100' in i['col_kinds'] or i['headerless_assumed_per100']), nut[0] if nut else None)
    if prim:
        rec['nutrition_per_100g'] = P.flatten(prim, 'per100') or None
        rec['nutrition_per_serving'] = P.flatten(prim, 'serving') or None
        rec['serving'] = prim['serving']
        if prim['headerless_assumed_per100']: flags.append('table_without_header_assumed_per100g')
        if not rec['nutrition_per_100g']:
            flags.append('no_per100_column' if not P.flatten(prim, 'prepared') else 'only_prepared_product_values')
        if len(nut) > 1: flags.append('multiple_nutrition_tables')
    else:
        rec['nutrition_per_100g'] = rec['nutrition_per_serving'] = rec['serving'] = None
        if re.search(r'kcal|kJ', content, re.I): flags.append('nutrition_text_not_table')
        else: flags.append('no_nutrition_on_page')
    rec['nutrition'] = prim and {'per_100g': rec['nutrition_per_100g'], 'per_serving': rec['nutrition_per_serving']} or None
    # does a variable product warn that flavours differ?
    if rec['variants'] and len(rec['variants']) > 1:
        flags.append('variants_share_one_nutrition_table')
        if re.search(r'varier|forskjell|ulik|avvik', rec['description_text'], re.I):
            flags.append('flavour_macros_may_differ_see_description')
    rec['flags'] = flags
    return rec


def main():
    rows = [json.loads(l) for l in open(os.path.join(D, 'list.jsonl'), encoding='utf8')]
    rows = [r for r in rows if r.get('status') == 'publish']
    sm = sitemap_urls()
    log(f'stage2 start rows={len(rows)} sitemap_urls={len(sm)}')
    done = set()
    if os.path.exists(OUT):
        done = {json.loads(l)['source_id'] for l in open(OUT, encoding='utf8')}
    rows.sort(key=lambda r: (r['link'] not in sm, r['id']))
    f = open(OUT, 'a', encoding='utf8'); n = 0; t0 = time.time()
    for r in rows:
        if r['id'] in done: continue
        r_ = get(r['link'])
        pd = page_data(r_.text) if r_.status_code == 200 else {}
        rec = build(r, pd, r['link'] in sm, r_.status_code)
        f.write(json.dumps(rec, ensure_ascii=False) + '\n'); f.flush(); n += 1
        if n % 100 == 0: log(f'progress {n} written, {REQ[0]} requests, {time.time()-t0:.0f}s')
        if limit and n >= limit: break
    log(f'stage2 done written={n} requests={REQ[0]}')


limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
if __name__ == '__main__':
    main()
