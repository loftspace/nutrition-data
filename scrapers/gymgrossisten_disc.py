"""gymgrossisten-discontinued: products in the shop sitemap / Internet Archive that the first crawl (category listing) did not have.
Live page first (no redirect following); if gone (404/410/redirect to /404 or elsewhere) fetch the Wayback snapshot (id_ = original page).
Reuses parse_product from gymgrossisten.py. Resume-safe via checked.jsonl. Usage: python gymgrossisten_disc.py [--limit N]"""
import re, sys, json, time, os, datetime, requests, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gymgrossisten as G   # parse_product, robots rules (module-level robots fetch is one request)

ROOT = G.ROOT; BASE = G.BASE; UA = G.UA
D = os.path.join(ROOT, 'data', 'raw', 'gymgrossisten-discontinued'); os.makedirs(D, exist_ok=True)
OUT = os.path.join(D, 'products.jsonl'); CHK = os.path.join(D, 'checked.jsonl')
LOGF = os.path.join(ROOT, 'logs', 'gymgrossisten-discontinued.log')
S = requests.Session(); S.headers['User-Agent'] = UA; S.headers['Accept-Language'] = 'nb-NO,nb;q=0.9'
LAST = {}; REQ = {'live': 0, 'archive': 0}


def log(m):
    line = f"{datetime.datetime.now().isoformat(timespec='seconds')} {m}"; print(line, flush=True)
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


DENY = re.compile(r'(knee|sleeve|glove|hanske|grip|strap|t-?shirt|t-?skjorte|skjorte|shorts|hoodie|hettegenser|genser|jakke|jacket|tights|singlet|-bh-|boxer|sock|strump|yoga|treningsband|fitnessband|-rope|hopp|hantel|dumbbell|kettlebell|abilica|venum|ryggsekk|backpack|-bag-|vaske|shaker|flaske|bottle|handduk|towel|belte|belt|wallbar|bench|pullup|vekt|body-?wash|lotion|sjampo|shampoo|deodor|beanie|lue|skor|shoes|-matte|gymmat|treningsmatte|foam-roller|rulle|massasje|bike|sykkel|ellipse|tredemolle|hodetelefon|klokke|watch)', re.I)
FOODCAT = re.compile(r'(kosttilskudd|matvarer|drikke|barer|snacks|helsekost|protein|vitamin|supplement|kosthold|sjokolade|godteri|kaffe)', re.I)


def is_food(rec):
    c = ' / '.join(rec.get('categories') or [])
    if FOODCAT.search(c): return True
    return bool(rec.get('tables')) and bool(rec.get('has_per100_table') or re.search(r'kcal|kJ|energi', rec.get('other_text') or '', re.I))


def fix(rec, h):
    """older page layouts: <h1 itemprop="name"> without inner span, breadcrumbs missing"""
    import html as _h
    if not rec.get('name'):
        m = re.search(r'<h1[^>]*>(.*?)</h1>', h, re.S)
        if m: rec['name'] = G.clean(m.group(1))
    if not rec.get('title'):
        m = re.search(r'og:title" content="([^"]*)"', h)
        if m: rec['title'] = _h.unescape(m.group(1)).replace('Kj\u00f8p ', '').replace(' | Gymgrossisten.no', '')
    if not rec.get('pack_size_text'):
        m = re.search(r'(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l|stk|kapsler|tabletter|caps)\b', rec.get('title') or rec.get('name') or '', re.I)
        rec['pack_size_text'] = m.group(0) if m else None
    return rec


def finish(rec, url, status, ts, disc, redirect=None):
    rec['source'] = 'gymgrossisten-discontinued'; rec['source_url'] = url; rec['fetched_on'] = datetime.date.today().isoformat()
    rec['page_status'] = status; rec['archive_timestamp'] = ts; rec['discontinued'] = disc; rec['redirect_to'] = redirect
    vo = rec.get('variant_options') or {}
    rec['flavour_nutrition_shared_assumed'] = any(len(v) > 1 for v in vo.values())
    return rec


def main():
    limit = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else 0
    c = json.load(open(os.path.join(D, 'candidates.json'), encoding='utf8'))
    ex = {json.loads(l)['source_url'] for l in open(os.path.join(ROOT, 'data/raw/gymgrossisten/products.jsonl'), encoding='utf8')}
    ex |= {BASE + u for u in json.load(open(os.path.join(ROOT, 'data/raw/gymgrossisten/urls.json')))}
    arch = c['archive']; sm = set(c['sitemap'])
    cand = [u for u in (sm | set(arch)) if u.endswith('.html') and u.count('/') == 4 and u not in ex]
    SKU = re.compile(r'^(A\d+(-\d+)?|FP\d+\w*|\d{2,6}(-\d{1,2})?R?|SET\w*|BUNDLE\w*)\.html$')
    pre = [u for u in cand if SKU.match(u.rsplit('/', 1)[1]) and not DENY.search(urllib.parse.unquote(u.rsplit('/', 2)[1]))]
    log(f'candidates {len(cand)}; after slug non-food filter {len(pre)} (dropped {len(cand)-len(pre)})')
    pre.sort(key=lambda u: (u not in sm, u))
    done = {}
    if os.path.exists(CHK):
        for l in open(CHK, encoding='utf8'):
            j = json.loads(l); done[j['url']] = j['outcome']
    saved = {json.loads(l)['source_url'] for l in open(OUT, encoding='utf8')} if os.path.exists(OUT) else set()
    todo = [u for u in pre if u not in done and u not in saved]
    if limit: todo = todo[:limit]
    log(f'todo {len(todo)} (already checked {len(done)})')
    fo = open(OUT, 'a', encoding='utf8'); fc = open(CHK, 'a', encoding='utf8')
    cnt = {}

    def mark(u, o):
        fc.write(json.dumps({'url': u, 'outcome': o}) + '\n'); fc.flush(); cnt[o] = cnt.get(o, 0) + 1
        n = sum(cnt.values())
        if n % 100 == 0: log(f'progress {n}/{len(queue)} {cnt} req={REQ}')

    queue = list(todo); qi = 0; seen_q = set(todo)
    while qi < len(queue):
        u = queue[qi]; qi += 1
        path = u[len(BASE):]
        if not G.allowed(u): mark(u, 'robots'); continue
        r = fetch(u, 'www.gymgrossisten.no', False)
        if r is None: mark(u, 'fetch_failed'); continue
        status, redirect = r.status_code, None
        if status == 200:
            r.encoding = 'utf-8'
            if 'itemprop="sku"' not in r.text and 'productGroupID' not in r.text:
                mark(u, 'nonproduct'); continue
            rec = fix(G.parse_product(path, r.text), r.text)
            if not is_food(rec): mark(u, 'live_nonfood'); continue
            fo.write(json.dumps(finish(rec, u, 'live', None, False), ensure_ascii=False) + '\n'); fo.flush(); mark(u, 'live_saved'); continue
        if status in (301, 302, 303, 307, 308):
            redirect = urllib.parse.urljoin(u, r.headers.get('Location', ''))
            rp = redirect.split('?')[0]
            if rp.endswith('.html') and rp.rsplit('/', 1)[-1] == u.rsplit('/', 1)[-1]:   # same sku, new slug: product lives on elsewhere
                if rp not in ex and rp not in seen_q and rp not in done:
                    queue.append(rp); seen_q.add(rp)
                mark(u, 'renamed_same_sku'); continue
        # gone: 404/410, redirect to /404, a category, or another product
        ts = arch.get(u)
        if not ts: mark(u, 'gone_no_archive'); continue
        a = fetch(f'https://web.archive.org/web/{ts}id_/{u}', 'web.archive.org', True)
        if a is None or a.status_code != 200: mark(u, 'archive_fetch_failed'); continue
        a.encoding = 'utf-8'
        try: rec = fix(G.parse_product(path, a.text), a.text)
        except Exception as e: log(f'PARSE-ERR {u} {e}'); mark(u, 'parse_err'); continue
        if not rec.get('sku') and not rec.get('name'): mark(u, 'archive_nonproduct'); continue
        if not is_food(rec): mark(u, 'archive_nonfood'); continue
        fo.write(json.dumps(finish(rec, u, 'gone', ts, True, redirect or f'HTTP {status}'), ensure_ascii=False) + '\n'); fo.flush(); mark(u, 'gone_archived_saved')
    log(f'END {cnt} req={REQ}')


main()
