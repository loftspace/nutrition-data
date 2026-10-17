#!/usr/bin/env python
"""Gymgrossisten.no scraper (macro-library). Rules: see ../README.md.
Phase 1: category listing /kosttillskott (paged, sz=100) -> product URLs.
Phase 2: each product page (server-rendered HTML) -> JSONL record.
Resume-safe: skips URLs already in products.jsonl.
Usage: python gymgrossisten_se.py [--limit N] [--urls-only]
"""
import re, sys, json, time, html, os, datetime, requests

BASE = "https://www.gymgrossisten.com"
UA = "macro-library-personal/1.0 (single-user personal research; github.com/Maxaubert)"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data", "raw", "gymgrossisten-se")
OUT = os.path.join(OUT_DIR, "products.jsonl")
URLS = os.path.join(OUT_DIR, "urls.json")
LOG = os.path.join(ROOT, "logs", "gymgrossisten-se.log")
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(os.path.dirname(LOG), exist_ok=True)
S = requests.Session()
S.headers["User-Agent"] = UA
S.headers["Accept-Language"] = "sv-SE,sv;q=0.9"
state = {"req": 0, "last": 0.0, "blocks": 0}


def log(msg):
    line = f"{datetime.datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf8") as f:
        f.write(line + "\n")


# ---- robots (wildcard aware) ----
def load_robots():
    txt = requests.get(BASE + "/robots.txt", headers={"User-Agent": UA}, timeout=30).text
    rules, active = [], False
    for ln in txt.splitlines():
        ln = ln.split("#")[0].strip()
        if not ln:
            continue
        k, _, v = ln.partition(":")
        k, v = k.strip().lower(), v.strip()
        if k == "user-agent":
            active = v == "*"
        elif k == "disallow" and active and v:
            rules.append(re.compile("^" + re.escape(v).replace(r"\*", ".*").replace(r"\$", "$")))
    return rules


RULES = load_robots()


def allowed(url):
    path = url[len(BASE):]
    return not any(r.match(path) for r in RULES)


def get(url, tries=5):
    if not allowed(url):
        log(f"ROBOTS-DISALLOWED skip {url}")
        return None
    delay = 2
    for _ in range(tries):
        wait = 1.1 - (time.time() - state["last"])
        if wait > 0:
            time.sleep(wait)
        state["last"] = time.time()
        state["req"] += 1
        try:
            r = S.get(url, timeout=60)
        except requests.RequestException as e:
            log(f"ERR {url} {e}")
            time.sleep(delay); delay *= 2
            continue
        if r.status_code == 200:
            state["blocks"] = 0
            r.encoding = "utf-8"
            return r.text
        if r.status_code == 404:
            log(f"404 {url}")
            return None
        if r.status_code in (403, 429) or r.status_code >= 500:
            state["blocks"] += 1
            log(f"HTTP {r.status_code} {url} (backoff {delay}s)")
            if state["blocks"] >= 8:
                log("STOP: repeated blocks")
                sys.exit(2)
            time.sleep(delay); delay = min(delay * 2, 120)
            continue
        log(f"HTTP {r.status_code} {url}")
        return None
    return None


# ---- phase 1 ----
def collect_urls():
    if os.path.exists(URLS):
        return json.load(open(URLS, encoding="utf8"))
    urls, start, total = {}, 0, None
    while True:
        h = get(f"{BASE}/kosttillskott?sz=100&start={start}")
        if h is None:
            break
        if total is None:
            m = re.search(r'data-product-count="(\d+)"', h)
            total = int(m.group(1)) if m else 0
            log(f"listing total={total}")
        found = list(dict.fromkeys(re.findall(r'href="(/[^"?#]+/[^"/?#]+\.html)"', h)))
        # keep only product tiles (the page also links menu/promos): tiles carry data-pid
        new = [u for u in found if u not in urls]
        for u in new:
            urls[u] = 1
        log(f"listing start={start} links={len(found)} new={len(new)} cum={len(urls)}")
        start += 100
        if start >= (total or 0):
            break
    res = list(urls)
    json.dump(res, open(URLS, "w", encoding="utf8"))
    return res


# ---- parsing ----
def clean(s):
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).replace("\xa0", " ").strip()


NUM = re.compile(r"(<|>|~|ca\.?\s*)?\s*(\d+(?:[.,]\d+)?)\s*(kj|kcal|mcg|µg|μg|ug|mg|g|ml|iu|ie|%)?", re.I)


def parse_cell(c):
    """'1657 kJ / 396 kcal' / '<0,5 g' / '7,3 g' -> dict"""
    t = c.strip()
    if not t or t in ("-", "–", "—"):
        return None
    out = {"raw": t}
    kj = re.search(r"(\d+(?:[.,]\d+)?)\s*kj", t, re.I)
    kc = re.search(r"(\d+(?:[.,]\d+)?)\s*kcal", t, re.I)
    if kj or kc:
        if kj: out["kj"] = float(kj.group(1).replace(",", "."))
        if kc: out["kcal"] = float(kc.group(1).replace(",", "."))
        return out
    m = NUM.search(t)
    if m:
        out["value"] = float(m.group(2).replace(",", "."))
        u = (m.group(3) or "").lower().replace("µ", "mc").replace("μ", "mc")
        out["unit"] = {"ug": "mcg", "ie": "iu"}.get(u, u)
        if m.group(1) and m.group(1).strip().startswith("<"):
            out["less_than"] = True
    return out


def parse_tables(frag):
    tables = []
    for tm in re.finditer(r"<table.*?</table>", frag, re.S | re.I):
        rows = []
        for rm in re.finditer(r"<tr.*?</tr>", tm.group(0), re.S | re.I):
            cells = [clean(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", rm.group(0), re.S | re.I)]
            if cells:
                rows.append(cells)
        if rows:
            tables.append(rows)
    return tables


def basis_of(label):
    l = label.lower()
    if "100" in l and ("g" in l or "ml" in l):
        return "per_100"
    if re.search(r"porsjon|dagsdose|serving|dose|scoop|skje|tablett|kapsel|innhold\s*/", l):
        return "per_serving"
    if re.search(r"\bper\b|/\s*\d", l):
        return "per_other"
    return "unknown"


def structure_table(rows):
    """First row = header: [label, col1, col2...]. Columns are flavours/variants or amounts."""
    head, body = rows[0], rows[1:]
    ncol = len(head) - 1
    cols = []
    for ci in range(1, len(head)):
        nutrients = []
        for r in body:
            if len(r) > ci:
                p = parse_cell(r[ci])
                nutrients.append({"label": r[0], **(p or {"raw": r[ci], "empty": True})})
        cols.append({"column": head[ci], "nutrients": nutrients})
    # two-column tables with no usable header (e.g. 'Innhold/ 5 g' | 'Mengde'): column header is 'Mengde:' etc.
    sv = re.search(r"(\d+(?:[.,]\d+)?)\s*(g|ml)", head[0], re.I)
    return {"basis_label": head[0], "basis": basis_of(head[0]), "basis_amount": ({"value": float(sv.group(1).replace(",", ".")), "unit": sv.group(2).lower()} if sv else None), "ncols": ncol, "columns": cols}


def section(h, marker, end_markers):
    i = h.find(marker)
    if i < 0:
        return ""
    j = len(h)
    for e in end_markers:
        k = h.find(e, i + len(marker))
        if k > 0:
            j = min(j, k)
    return h[i:j]


def parse_product(url, h):
    g = lambda pat, flags=re.S: (lambda m: m.group(1) if m else None)(re.search(pat, h, flags))
    rec = {"source": "gymgrossisten-se", "source_url": BASE + url,
           "fetched_on": datetime.date.today().isoformat()}
    rec["product_group_id"] = g(r'itemprop="productGroupID" content="([^"]*)"')
    rec["sku"] = g(r'itemprop="sku" content="([^"]*)"')
    rec["ean"] = g(r'itemprop="gtin13" content="(\d+)"') or g(r'class="ean-code">(\d+)<')
    rec["name"] = clean(g(r'<h1[^>]*>.*?<span itemprop="name">(.*?)</span>') or "")
    t = g(r'og:title" content="([^"]*)"')
    rec["title"] = html.unescape(t).replace("Kjøp ", "").replace(" | Gymgrossisten.no", "") if t else None
    rec["brand"] = g(r'itemprop="brand"[^>]*>\s*<meta itemprop="name" content="([^"]*)"')
    p = g(r'itemprop="price" content="([\d.]+)"')
    rec["price_sek"] = float(p) if p else None; rec["currency"] = "SEK"; rec["country"] = "SE"
    crumbs = []
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', h, re.S):
        try:
            d = json.loads(m.group(1))
        except Exception:
            continue
        if isinstance(d, dict) and d.get("@type") == "BreadcrumbList":
            crumbs = [x.get("name") for x in d.get("itemListElement", [])]
    rec["categories"] = crumbs
    # variants (flavours / sizes) as listed in the selector
    rec["variant_options"] = {}
    for m in re.finditer(r'<button class="item variation-item"[^>]*?data-text="([^"]*)"[^>]*?data-url="[^"]*?dwvar_[^=]*?_([\w-]+)=', h, re.S):
        rec["variant_options"].setdefault(m.group(2), [])
        v = html.unescape(m.group(1))
        if v not in rec["variant_options"][m.group(2)]:
            rec["variant_options"][m.group(2)].append(v)
    rec["is_bundle"] = bool(re.match(r"(SET|BUNDLE)", rec["sku"] or "", re.I) or re.search(r"\d+\s*x|mix&match|pakke", (rec["name"] or "").lower()))
    sm = re.search(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l|stk|kapsler|tabletter|caps)\b", rec["title"] or rec["name"] or "", re.I)
    rec["pack_size_text"] = sm.group(0) if sm else None
    # description + nutrition sections
    short = g(r'<div class="product-short-description"[^>]*>(.*?)</div>\s*(?:<a class="read-more|</div>)') or ""
    t1 = section(h, 'data-tab-content="tab-1"', ['data-tab-content="tab-2"'])
    t3 = section(h, 'data-tab-content="tab-3"', ['data-tab-content="tab-4"', "<!-- =============== This snippet"]) or ""
    nutri_frag = t3
    # trim trailing page chrome from t3: cut at the first closing of tab container heuristics
    rec["description"] = clean(re.sub(r"<table.*?</table>", " ", t1, flags=re.S)).replace('data-tab-content="tab-1">', "", 1).strip()[:3000]
    rec["raw_nutrition_html"] = (short + " <!--TAB3--> " + nutri_frag)[:60000]
    tabs = []
    nutrition_tables = []
    for src, frag in (("short_description", short), ("tab_nutrition", nutri_frag), ("tab_description", t1)):
        for rows in parse_tables(frag):
            s = structure_table(rows)
            s["source_section"] = src
            nutrition_tables.append(s)
    rec["tables"] = nutrition_tables
    rec["tables_raw"] = [{"section": src, "rows": rows} for src, frag in (("short_description", short), ("tab_nutrition", nutri_frag), ("tab_description", t1)) for rows in parse_tables(frag)]
    # ingredients / other text from nutrition tab and short description
    txt = clean(re.sub(r"<table.*?</table>", " ", nutri_frag + " " + short, flags=re.S))
    ing = re.search(r"Ingredienser?\s*:?\s*(.*?)(?:Øvrig informasjon|Bruksanvisning|Anbefalt|Allergi|$)", txt, re.I)
    rec["ingredients_text"] = ing.group(1).strip()[:4000] if ing else None
    rec["other_text"] = txt[:6000]
    # extract flat per-100 g view when a table is per 100 g
    per100 = []
    for t in nutrition_tables:
        if t["basis"] == "per_100":
            per100.append(t)
    rec["has_per100_table"] = bool(per100)
    rec["nutrition"] = None
    if per100:
        # one dict per flavour column, merged across tables
        flat = {}
        for t in per100:
            for c in t["columns"]:
                flat[c["column"]] = {n["label"]: {k: v for k, v in n.items() if k != "label"} for n in c["nutrients"]}
        rec["nutrition"] = {"basis": "per_100_g_or_ml", "by_column": flat}
        rec["nutrition_flag"] = "ok"
    elif nutrition_tables:
        rec["nutrition_flag"] = "table_not_per_100g_see_tables"
    else:
        rec["nutrition_flag"] = "no_nutrition_table"
    return rec


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    log(f"start; robots rules={len(RULES)}")
    urls = collect_urls()
    log(f"urls={len(urls)}")
    if "--urls-only" in sys.argv:
        return
    done = set()
    if os.path.exists(OUT):
        for ln in open(OUT, encoding="utf8"):
            try:
                done.add(json.loads(ln)["source_url"])
            except Exception:
                pass
    todo = [u for u in urls if BASE + u not in done]
    if limit:
        todo = todo[:limit]
    log(f"todo={len(todo)} already={len(done)}")
    n = 0
    with open(OUT, "a", encoding="utf8") as f:
        for u in todo:
            h = get(BASE + u)
            if h is None:
                continue
            try:
                rec = parse_product(u, h)
            except Exception as e:
                log(f"PARSE-ERR {u} {e}")
                continue
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            n += 1
            if n % 50 == 0:
                log(f"progress saved={n} requests={state['req']}")
    log(f"end saved={n} requests={state['req']}")


if __name__ == "__main__":
    main()
