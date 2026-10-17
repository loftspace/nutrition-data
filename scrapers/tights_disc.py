"""tights-discontinued: tights.no product pages that the first crawl (REST list filtered to 4 food categories) did not have.
Input: data/raw/tights-discontinued/{candidates.json, rest_lookup.jsonl, rest_missing.json} (see discontinued_discover.py, tights_disc_rest.py).
Live page first (no redirect following); if gone fetch the Wayback snapshot (id_). Parsing reuses tights.py / tights_parse.py / tights_post.py.
Resume-safe via checked.jsonl. Usage: python tights_disc.py [--limit N]"""
import re, sys, json, time, os, datetime, html as H, requests, urllib.parse, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
_argv = sys.argv; sys.argv = sys.argv[:1]
import tights as T, tights_post as TP, tights_parse as P     # noqa
sys.argv = _argv
from bs4 import BeautifulSoup

ROOT = os.path.abspath(os.path.join(HERE, '..'))
D = os.path.join(ROOT, 'data', 'raw', 'tights-discontinued')
OUT = os.path.join(D, 'products.jsonl'); CHK = os.path.join(D, 'checked.jsonl')
LOGF = os.path.join(ROOT, 'logs', 'tights-discontinued.log')
UA = "macro-library-personal/1.0 (single-user personal research; github.com/Maxaubert)"
S = requests.Session(); S.headers['User-Agent'] = UA; S.headers['Accept-Language'] = 'nb-NO,nb;q=0.9'
LAST = {}; REQ = {'live': 0, 'archive': 0}
FOODTOP = {'matvarer', 'treningstilskudd', 'helsekost', 'drikkevarer', 'kosttilskudd'}


def log(m):
    line = f"{time.strftime('%F %T')} {m}"; print(line, flush=True)
    open(LOGF, 'a', encoding='utf8').write(line + '\n')


def fetch(url, host, follow, tries=5):
    d = 4
    for a in range(tries):
        w = (2.3 if 'archive' in host else 1.1) - (time.time() - LAST.get(host, 0))  # two scrapers share archive.org: 2.3 s each keeps the total under 1 req/s
        if w > 0: time.sleep(w)
        LAST[host] = time.time(); REQ['archive' if 'archive' in host else 'live'] += 1
        try: r = S.get(url, timeout=90, allow_redirects=follow)
        except requests.RequestException as e:
            log(f'ERR {url} {type(e).__name__}'); time.sleep(d); d *= 2; continue
        if r.status_code in (200, 301, 302, 303, 307, 308, 404, 410): return r
        log(f'HTTP {r.status_code} {url}')
        if r.status_code in (403, 429) and a >= 3: raise SystemExit('blocked ' + url)
        time.sleep(d); d = min(d * 2, 120)
    return None


def txt(r): return r.content.decode('utf-8', 'replace')


def row_from_html(h, url):
    """Build a REST-like row from a page (live or archived)."""
    soup = BeautifulSoup(h, 'html.parser')
    parts = []
    for cls in ('long-description', 'short-description'):
        el = soup.find('div', class_=cls)
        if el: parts.append(str(el))
    if not parts:
        el = soup.find(id='tab-description') or soup.find(class_='woocommerce-Tabs-panel--description') or soup.find(attrs={'itemprop': 'description'})
        if el: parts.append(str(el))
    content = ''.join(parts)
    pid = None
    m = re.search(r"rel=['\"]shortlink['\"] href=['\"][^'\"]*[?&]p=(\d+)", h) or re.search(r'id="product-(\d+)"', h) or re.search(r'postid-(\d+)', h)
    if m: pid = int(m.group(1))
    cl = []
    m = re.search(r'class="([^"]*type-product[^"]*)"', h)
    if m: cl = m.group(1).split()
    t = soup.find('title'); title = H.unescape(t.get_text()).replace(' - Tights.no', '').strip() if t else ''
    h1 = soup.find('h1')
    if h1: title = h1.get_text(strip=True)
    return {'id': pid, 'link': url, 'title': {'rendered': title}, 'content': {'rendered': content}, 'class_list': cl,
            'product_cat': [int(x[len('product_cat-'):]) for x in cl if re.fullmatch(r'product_cat-\d+', x)]}


def post(r, content):
    """Body of tights_post.main loop for one record (adds nutrition basis resolution, text fallback, derived per-100)."""
    flags = [f for f in r['flags'] if f in ('variants_share_one_nutrition_table', 'flavour_macros_may_differ_see_description')]
    its = []
    for t in P.parse_tables(content):
        it = P.interpret_table(t); it['nutritional'] = P.looks_nutritional(it); its.append(it)
    nut = [i for i in its if i['nutritional']]
    if not nut:
        tp = TP.text_parse(content)
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
            g, basis = TP.unit_weight_g(r['name'], prim['serving'], r['weight_kg'])
            if psv and g:
                r['nutrition_per_100g_derived'] = {k: round(v * 100.0 / g, 4) if isinstance(v, float) and not k.endswith('_lt') else v for k, v in psv.items()}
                r['derived_basis'] = {'serving_g': g, 'from': basis}
                flags.append('per100g_derived_from_serving_size')
            elif psv: flags.append('per_serving_only_no_gram_size')
            elif not pp: flags.append('no_per100_column')
        if len(nut) > 1:
            flags.append('multiple_nutrition_tables')
            r['nutrition_by_table'] = [{'title': i['header'][0] if i['header'] else '', 'header': i['header'],
                                        'per_100g': P.flatten(i, 'per100') or None, 'per_serving': P.flatten(i, 'serving') or None} for i in nut]
        r['nutrition'] = {'per_100g': p100, 'per_serving': psv}
    else:
        flags.append('nutrition_unparsed_text_or_image' if re.search(r'kcal|kJ', content, re.I) else 'no_nutrition_on_page')
    r['flags'] = flags
    return r


def page_data_lenient(h):
    """T.page_data for old archived pages where JSON-LD brand/weight can be plain strings or lists."""
    soup = BeautifulSoup(h, 'html.parser')
    d = {}
    def nm(x):
        if isinstance(x, dict): return x.get('name')
        if isinstance(x, list) and x: return nm(x[0])
        return x if isinstance(x, str) else None
    for s in soup.find_all('script', type='application/ld+json'):
        try: j = json.loads(s.string)
        except Exception: continue
        graph = j.get('@graph', [j]) if isinstance(j, dict) else j
        for g in graph if isinstance(graph, list) else []:
            if not isinstance(g, dict): continue
            if g.get('@type') == 'Product':
                d['gtin'] = g.get('gtin13') or g.get('gtin') or g.get('gtin12') or g.get('gtin8')
                d['mpn'] = g.get('mpn'); d['sku'] = g.get('sku'); d['brand'] = nm(g.get('brand'))
                d['name'] = H.unescape(g.get('name', '') or '')
                w = g.get('weight'); d['weight_kg'] = w.get('value') if isinstance(w, dict) else None
                d['category_ld'] = g.get('category')
            if g.get('@type') == 'BreadcrumbList':
                try: d['breadcrumb'] = [H.unescape(H.unescape(i['item']['name'] if isinstance(i['item'], dict) else i['name'])) for i in g['itemListElement'][1:-1]]
                except Exception: pass
    try:
        d2 = T.page_data(h)
        for k, v in d2.items(): d.setdefault(k, v)
    except Exception:
        d.setdefault('attributes', {})
    d.setdefault('attributes', {})
    return d


def make(url, h, status, ts, disc, redirect, row=None):
    pd = page_data_lenient(h)
    row = row or row_from_html(h, url)
    if not row.get('content', {}).get('rendered'):
        alt = row_from_html(h, url); row['content'] = alt['content']
    rec = T.build(row, pd, False, 200 if status == 'live' else status)
    rec = post(rec, row['content']['rendered'])
    top = ((pd.get('breadcrumb') or [None])[0] or '').lower()
    rec['source'] = 'tights-discontinued'; rec['source_url'] = url; rec['fetched_on'] = datetime.date.today().isoformat()
    rec['in_sitemap'] = False; rec['page_status'] = status; rec['archive_timestamp'] = ts; rec['discontinued'] = disc; rec['redirect_to'] = redirect
    rec['flavour_nutrition_shared_assumed'] = bool(rec.get('variants') and len(rec['variants']) > 1)
    rec['_top'] = top
    return rec


GEAR = re.compile(r'(shaker|flaske|tilbeh|gadget|utstyr|kl.r|bag|sekk|mat?te|trening.?utstyr|smartshake)', re.I)


def is_food(rec):
    if GEAR.search(' / '.join(rec.get('categories') or [])) and not rec.get('nutrition_tables'): return False
    if GEAR.search(' / '.join(rec.get('categories') or [])) and re.search(r'shaker|flaske|bottle', rec.get('name') or '', re.I): return False
    return rec['_top'] in FOODTOP or bool(rec.get('nutrition_tables'))


def main():
    limit = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else 0
    c = json.load(open(os.path.join(D, 'candidates.json'), encoding='utf8')); arch = c['archive']
    ex_recs = [json.loads(l) for l in open(os.path.join(ROOT, 'data/raw/tights/products.jsonl'), encoding='utf8')]
    ex = {r['source_url'] for r in ex_recs}
    cats = {x['id']: x for x in json.load(open(os.path.join(ROOT, 'data/raw/tights/categories.json'), encoding='utf8'))}

    def top(cid):
        while cid in cats and cats[cid].get('parent'): cid = cats[cid]['parent']
        return (cats.get(cid) or {}).get('name', '').lower()

    # Stage A: REST-published products not in first crawl
    rest = [json.loads(l) for l in open(os.path.join(D, 'rest_lookup.jsonl'), encoding='utf8')]
    foodA, nonA = [], 0
    for x in rest:
        if x['link'] in ex: continue
        tops = {top(i) for i in x['product_cat']}
        if tops & FOODTOP: foodA.append(x)
        else: nonA += 1
    log(f'REST-published not in first crawl: {len(rest)}; food top-category {len(foodA)}; non-food {nonA}')
    # Stage B: gone slugs, food heuristic from slug
    brandtok = collections.Counter()
    for r in ex_recs:
        s = r['source_url'].rstrip('/').rsplit('/', 1)[1]; s = re.sub(r'^\d+x-', '', s)
        brandtok[s.split('-')[0]] += 1
    brands = {b for b, n in brandtok.items() if n >= 3 and len(b) > 2}
    kw = re.compile(r'(protein|whey|kreatin|creatine|bcaa|aminosyre|vitamin|omega|kapsl|tablett|bar-|-bar\b|proteinbar|sjokolade|pulver|shake|energidrikk|drikke|kaffe|te-|nudl|pasta|mel-|saus|sirup|dressing|snack|chips|godteri|vingummi|gele|gel-|elektrolytt|koffein|pwo|pre-workout|probiotika|kollagen|magnesium|zink|jern|d3|b12|\d+\s?x?\d*\s?(g|ml|kg|l)\b|\d+g\b|\d+ml\b|nutri|iso|gainer|casein|kasein|isolat|hampe|chia|havre|mandel|nott|peanut|smor)')
    deny = re.compile(r'(tights|tee\b|t-shirt|shorts|jakke|jacket|hoodie|sweat|bra\b|bh-|singlet|legging|sock|strump|boxer|beanie|lue-|caps?-|hat-|sko-|shoe|bag|sekk|backpack|vaske|handduk|belt|glove|hansker|headband|pannebånd|armband|sleeve|polo|dress|skjort|pants|bukse|vest|baselayer|trosse|panties|briefs|flaske|bottle|tumbler|shaker|matte|yoga|foam)')
    missing = json.load(open(os.path.join(D, 'rest_missing.json'), encoding='utf8'))
    cand = []
    for s in missing:
        u = f'https://www.tights.no/butikk/{urllib.parse.quote(s)}/'
        u = next((k for k in arch if urllib.parse.unquote(k).rstrip('/').rsplit('/', 1)[1] == s), u)
        s0 = re.sub(r'^\d+x-', '', s)
        if deny.search(s0) and not s0.split('-')[0] in brands: continue
        if s0.split('-')[0] in brands or kw.search(s0): cand.append((s, u))
    log(f'gone/unpublished slugs {len(missing)}; food-looking after slug filter {len(cand)}')
    done = {}
    if os.path.exists(CHK):
        for l in open(CHK, encoding='utf8'):
            j = json.loads(l); done[j['url']] = j['outcome']
    fo = open(OUT, 'a', encoding='utf8'); fc = open(CHK, 'a', encoding='utf8'); cnt = {}

    def mark(u, o):
        fc.write(json.dumps({'url': u, 'outcome': o}) + '\n'); fc.flush(); cnt[o] = cnt.get(o, 0) + 1
        n = sum(cnt.values())
        if n % 100 == 0: log(f'progress {n} {cnt} req={REQ}')

    def save(rec):
        rec.pop('_top', None); fo.write(json.dumps(rec, ensure_ascii=False) + '\n'); fo.flush()

    jobs = [('A', x['link'], x) for x in foodA] + [('B', u, None) for s, u in cand]
    jobs = [j for j in jobs if j[1] not in done]
    if limit: jobs = jobs[:limit]
    log(f'jobs {len(jobs)}')
    for kind, u, row in jobs:
        r = fetch(u, 'www.tights.no', False)
        if r is None: mark(u, 'fetch_failed'); continue
        if r.status_code == 200:
            h = txt(r)
            try: rec = make(u, h, 'live', None, False, None, row)
            except Exception as e: log(f'PARSE-ERR {u} {type(e).__name__} {e}'); mark(u, 'parse_err'); continue
            if not is_food(rec): mark(u, 'live_nonfood'); continue
            save(rec); mark(u, 'live_saved'); continue
        redirect = urllib.parse.urljoin(u, r.headers.get('Location', '')) if r.status_code in (301, 302, 303, 307, 308) else f'HTTP {r.status_code}'
        ts = arch.get(u)
        if not ts: mark(u, 'gone_no_archive'); continue
        a = fetch(f'https://web.archive.org/web/{ts}id_/{u}', 'web.archive.org', True)
        if a is None or a.status_code != 200: mark(u, 'archive_fetch_failed'); continue
        try: rec = make(u, txt(a), 'gone', ts, True, redirect)
        except Exception as e: log(f'PARSE-ERR {u} {type(e).__name__} {e}'); mark(u, 'parse_err'); continue
        if not rec.get('name'): mark(u, 'archive_nonproduct'); continue
        if not is_food(rec): mark(u, 'archive_nonfood'); continue
        save(rec); mark(u, 'gone_archived_saved')
    log(f'END {cnt} req={REQ}')


main()
