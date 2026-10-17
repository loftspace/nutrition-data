"""Step 2 for tights-discontinued: batch-lookup candidate slugs through the public WP REST API (robots allows /wp-json/), 100 slugs per request.
Output data/raw/tights-discontinued/rest_lookup.jsonl (published products found) and rest_missing.json (slugs not published)."""
import requests, json, os, time, re, urllib.parse
BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'); D = os.path.join(BASE, 'data/raw/tights-discontinued')
UA = "macro-library-personal/1.0 (single-user personal research; github.com/Maxaubert)"
S = requests.Session(); S.headers['User-Agent'] = UA
def log(m): open(os.path.join(BASE, 'logs/tights-discontinued.log'), 'a', encoding='utf8').write(time.strftime('%F %T ') + m + '\n'); print(m, flush=True)
ex = {json.loads(l)['source_url'] for l in open(os.path.join(BASE, 'data/raw/tights/products.jsonl'), encoding='utf8')}
c = json.load(open(os.path.join(D, 'candidates.json')))
urls = set(c['sitemap']) | set(c['archive']); urls = [u for u in urls if u.startswith('https://www.tights.no/butikk/') and u not in ex]
slugs = sorted({urllib.parse.unquote(u.rstrip('/').rsplit('/', 1)[1]) for u in urls})
log(f'rest lookup: {len(slugs)} candidate slugs')
found = {}
out = open(os.path.join(D, 'rest_lookup.jsonl'), 'w', encoding='utf8')
def q(b):
    """returns list or None if the batch breaks the endpoint (bisect then)."""
    for a in range(4):
        time.sleep(1.1)
        try: r = S.get('https://www.tights.no/wp-json/wp/v2/product', params={'slug': ','.join(b), 'per_page': 100, 'status': 'publish',
              '_fields': 'id,slug,link,title,content,class_list,product_cat,status,date,modified'}, timeout=90)
        except requests.RequestException as e: time.sleep(5); continue
        if r.status_code == 200:
            try: return r.json()
            except Exception: return None
        if r.status_code in (400, 404): return []
        time.sleep(5 * 2 ** a)
    return None
def run(b):
    r = q(b)
    if r is None:
        if len(b) == 1: log(f'unfetchable slug {b[0]}'); return []
        h = len(b) // 2; return run(b[:h]) + run(b[h:])
    return r
for i in range(0, len(slugs), 40):
    for x in run(slugs[i:i+40]):
        found[x['slug']] = 1; out.write(json.dumps(x, ensure_ascii=False) + chr(10))
    out.flush()
    if (i // 40) % 10 == 0: log(f'rest batch {i//40} found so far {len(found)}')
missing = [s for s in slugs if s not in found]
json.dump(missing, open(os.path.join(D, 'rest_missing.json'), 'w'))
log(f'rest done: published-found {len(found)}, not published/gone {len(missing)}')
