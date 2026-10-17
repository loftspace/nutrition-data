"""Discovery for discontinued/hidden products: sitemaps + Internet Archive CDX for tights.no and gymgrossisten.no.
Writes data/raw/<shop>-discontinued/candidates.json (not products). Max 1 req/s per host, honest UA."""
import requests, json, re, os, time, sys, urllib.parse
BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
UA = "macro-library-personal/1.0 (single-user personal research; github.com/Maxaubert)"
S = requests.Session(); S.headers['User-Agent'] = UA
LAST = {}
def log(shop, m):
    os.makedirs(os.path.join(BASE, 'logs'), exist_ok=True)
    open(os.path.join(BASE, 'logs', f'{shop}-discontinued.log'), 'a', encoding='utf8').write(time.strftime('%F %T ') + m + '\n'); print(m, flush=True)
def get(url, params=None, tries=6):
    host = urllib.parse.urlparse(url).netloc
    d = 5
    for a in range(tries):
        w = 1.1 - (time.time() - LAST.get(host, 0))
        if w > 0: time.sleep(w)
        LAST[host] = time.time()
        try: r = S.get(url, params=params, timeout=120)
        except requests.RequestException as e:
            time.sleep(d); d *= 2; continue
        if r.status_code in (200, 404, 410): return r
        time.sleep(d); d = min(d * 2, 120)
    return None

def cdx(shop, pattern, extra=None):
    out = []
    r = get('https://web.archive.org/cdx/search/cdx', {'url': pattern, 'output': 'json', 'fl': 'timestamp,original,statuscode', 'collapse': 'urlkey', 'filter': ['statuscode:200'] + (extra or []), 'limit': 200000})
    if r is None or r.status_code != 200:
        log(shop, f'CDX failed {pattern} {r and r.status_code}'); return []
    try: rows = r.json()
    except Exception: log(shop, 'CDX bad json'); return []
    log(shop, f'CDX {pattern}: {len(rows)-1} rows'); return rows[1:]

def tights():
    shop = 'tights'; d = os.path.join(BASE, 'data/raw/tights-discontinued'); os.makedirs(d, exist_ok=True)
    existing = {json.loads(l)['source_url'] for l in open(os.path.join(BASE, 'data/raw/tights/products.jsonl'), encoding='utf8')}
    sm = set()
    for i in (1, 2, 3):
        r = get(f'https://www.tights.no/wp-sitemap-posts-product-{i}.xml')
        if r is not None and r.status_code == 200: sm |= set(re.findall(r'<loc>([^<]+)</loc>', r.text))
    log('tights', f'sitemap urls {len(sm)}, existing {len(existing)}, sitemap-not-existing {len(sm-existing)}')
    arch = {}
    for pat in ('tights.no/butikk/*', 'tights.no/produkt/*', 'www.tights.no/butikk/*'):
        for ts, orig, sc in cdx('tights', pat):
            u = re.sub(r'^http://', 'https://', orig).split('?')[0].split('#')[0]
            u = re.sub(r'^https://tights\.no', 'https://www.tights.no', u)
            if not u.endswith('/'): u += '/'
            if u.count('/') != 5: continue  # https://www.tights.no/butikk/slug/
            arch[u] = max(arch.get(u, ''), ts)
    log('tights', f'archive product urls {len(arch)}; not in existing {len(set(arch)-existing)}; not in sitemap {len(set(arch)-sm)}')
    json.dump({'sitemap': sorted(sm), 'archive': arch, 'existing_n': len(existing)}, open(os.path.join(d, 'candidates.json'), 'w'))

def gym():
    shop = 'gymgrossisten'; d = os.path.join(BASE, 'data/raw/gymgrossisten-discontinued'); os.makedirs(d, exist_ok=True)
    existing = {json.loads(l)['source_url'] for l in open(os.path.join(BASE, 'data/raw/gymgrossisten/products.jsonl'), encoding='utf8')}
    existing |= {'https://www.gymgrossisten.no' + u for u in json.load(open(os.path.join(BASE, 'data/raw/gymgrossisten/urls.json')))}
    sm = set()
    for i in range(0, 8):
        r = get(f'https://www.gymgrossisten.no/sitemap_{i}.xml')
        if r is None or r.status_code != 200: break
        sm |= set(re.findall(r'<loc>([^<]+)</loc>', r.text))
    prod = {u for u in sm if u.endswith('.html')}
    log('gymgrossisten', f'sitemap urls {len(sm)} product-like {len(prod)} existing {len(existing)} product-not-existing {len(prod-existing)}')
    arch = {}
    for ts, orig, sc in cdx('gymgrossisten', 'gymgrossisten.no/*', [r'original:[^?]*\.html']):
        u = re.sub(r'^http://', 'https://', orig).split('?')[0]
        u = re.sub(r'^https://gymgrossisten\.no', 'https://www.gymgrossisten.no', u)
        arch[u] = max(arch.get(u, ''), ts)
    log('gymgrossisten', f'archive html urls {len(arch)}; not in existing {len(set(arch)-existing)}')
    json.dump({'sitemap': sorted(sm), 'archive': arch}, open(os.path.join(d, 'candidates.json'), 'w'))

if __name__ == '__main__':
    {'tights': tights, 'gym': gym}[sys.argv[1]]()
