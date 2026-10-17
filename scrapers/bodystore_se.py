#!/usr/bin/env python3
"""Bodystore.no scraper (Salesforce Commerce Cloud, server-rendered HTML).
Phase 1: collect product URLs from category listings (?sz=100&start=N) + sitemap supplement SKUs.
Phase 2: fetch each product page, parse fields + nutrition tables.
Rules: robots.txt honoured (wildcards), 1 req/s, honest UA, resume-safe, no images.
Usage: bodystore.py [--limit N] [--test]
"""
import re, sys, json, time, os, html as H, datetime, urllib.request, urllib.error
from html.parser import HTMLParser

BASE = "https://www.bodystore.com"
UA = "macro-library-personal/1.0 (single-user personal research; github.com/Maxaubert)"
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUTD = os.path.join(ROOT, "data", "raw", "bodystore-se")
LOG = os.path.join(ROOT, "logs", "bodystore-se.log")
OUT = os.path.join(OUTD, "products.jsonl")
URLS = os.path.join(OUTD, "urls.json")
os.makedirs(OUTD, exist_ok=True); os.makedirs(os.path.dirname(LOG), exist_ok=True)
TODAY = datetime.date.today().isoformat()
REQS = 0; LAST = 0.0; BLOCKS = 0


def log(m):
    line = f"{datetime.datetime.now().isoformat(timespec='seconds')} {m}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf8") as f:
        f.write(line + "\n")


DIS = []


def load_robots():
    txt = fetch(BASE + "/robots.txt", check=False) or ""
    grp = False
    for ln in txt.splitlines():
        ln = ln.split("#")[0].strip()
        if not ln:
            continue
        k, _, v = ln.partition(":")
        k = k.strip().lower(); v = v.strip()
        if k == "user-agent":
            grp = (v == "*")
        elif k == "disallow" and grp and v:
            DIS.append(re.compile("^" + re.escape(v).replace(r"\*", ".*").replace(r"\$", "$")))
    log(f"robots: {len(DIS)} disallow rules for *")


def allowed(url):
    p = url[len(BASE):] if url.startswith(BASE) else url
    return not any(r.search(p) for r in DIS)


def fetch(url, check=True, tries=5):
    global REQS, LAST, BLOCKS
    if check and not allowed(url):
        log(f"SKIP robots-disallowed {url}")
        return None
    delay = 2
    for i in range(tries):
        w = 1.05 - (time.time() - LAST)
        if w > 0:
            time.sleep(w)
        LAST = time.time(); REQS += 1
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "sv-SE,sv;q=0.9"})
            with urllib.request.urlopen(req, timeout=40) as r:
                BLOCKS = 0
                return r.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                log(f"404 {url}"); return None
            if e.code in (403, 429) or e.code >= 500:
                BLOCKS += 1; log(f"HTTP {e.code} {url} try {i+1}")
                if BLOCKS >= 8:
                    log("STOP: repeated blocks"); sys.exit(2)
                time.sleep(delay); delay *= 2; continue
            log(f"HTTP {e.code} {url}"); return None
        except Exception as e:
            log(f"ERR {e} {url}"); time.sleep(delay); delay *= 2
    return None


CATS = ["/halsa", "/livsmedel", "/traning", "/behov"]


def collect():
    if os.path.exists(URLS):
        return json.load(open(URLS))
    found = {}
    for c in CATS:
        start = 0; prev = None
        while True:
            u = f"{BASE}{c}?sz=100&start={start}"
            h = fetch(u)
            if not h:
                break
            links = []
            for m in re.finditer(r'href="((?:https://www\.bodystore\.com)?/[^"#?]+\.html)"', h):
                l = m.group(1)
                l = l if l.startswith("http") else BASE + l
                if l.count("/") == 4 and l not in links:
                    links.append(l)
            new = [l for l in links if l not in found]
            for l in links:
                found.setdefault(l, c)
            log(f"cat {c} start={start}: {len(links)} links, {len(new)} new, total {len(found)}")
            if not links or links == prev or (not new and start > 0):
                break
            prev = links; start += 100
            if start > 3000:
                break
    for i in range(3):
        x = fetch(f"{BASE}/sitemap_{i}.xml")
        for u in re.findall(r"<loc>([^<]+)</loc>", x or ""):
            if u.endswith(".html") and u.count("/") == 4:
                sku = u.rsplit("/", 1)[1][:-5]
                if (re.match(r"^[A-C]\d", sku) or re.match(r"^90\d{4}$", sku)) and u not in found:
                    found[u] = "sitemap"
    json.dump(found, open(URLS, "w"))
    log(f"collected {len(found)} product urls")
    return found


class TableP(HTMLParser):
    def __init__(s):
        super().__init__()
        s.tables = []; s.cur = None; s.row = None; s.cell = None; s.h3 = ""; s.inh3 = False; s.lasth = ""

    def handle_starttag(s, t, a):
        if t == "h3":
            s.inh3 = True; s.h3 = ""
        elif t == "table":
            s.cur = {"heading": s.lasth, "rows": []}
        elif t == "tr" and s.cur is not None:
            s.row = []
        elif t in ("td", "th") and s.row is not None:
            s.cell = ""
        elif t == "br" and s.cell is not None:
            s.cell += " "

    def handle_endtag(s, t):
        if t == "h3":
            s.inh3 = False; s.lasth = s.h3.strip()
        elif t in ("td", "th") and s.cell is not None:
            s.row.append(re.sub(r"\s+", " ", H.unescape(s.cell)).strip()); s.cell = None
        elif t == "tr" and s.row is not None:
            if s.row:
                s.cur["rows"].append(s.row)
            s.row = None
        elif t == "table" and s.cur is not None:
            s.tables.append(s.cur); s.cur = None

    def handle_data(s, d):
        if s.inh3:
            s.h3 += d
        if s.cell is not None:
            s.cell += d


UNITS = {"ug": "µg", "mcg": "µg", "mikrogram": "µg", "ie": "IU", "iu": "IU"}
NUM = re.compile(r"^\s*(<|>|ca\.?|~)?\s*(\d+(?:[.,]\d+)?)\s*(kj|kcal|mg|µg|ug|mcg|g|ml|iu|ie|%|cfu|mikrogram)?\s*$", re.I)


def parse_val(s):
    raw = s.strip()
    s = re.sub(r"(?<=\d)[\s ](?=\d{3}(?!\d))", "", raw)
    if not s or s in ("-", "–"):
        return None
    out = {"raw": raw}
    ek = re.search(r"(\d+(?:[.,]\d+)?)\s*kj", s, re.I)
    kc = re.search(r"(\d+(?:[.,]\d+)?)\s*kcal", s, re.I)
    if ek or kc:
        if ek: out["kj"] = float(ek.group(1).replace(",", "."))
        if kc: out["kcal"] = float(kc.group(1).replace(",", "."))
        return out
    m = NUM.match(s)
    if m:
        out["value"] = float(m.group(2).replace(",", "."))
        u = (m.group(3) or "").lower()
        out["unit"] = UNITS.get(u, u) or None
        if m.group(1): out["qualifier"] = m.group(1)
        return out
    if re.search(r"sporm|spor av|trace", s, re.I):
        out["value"] = 0.0; out["qualifier"] = "trace"; return out
    m = re.match(r"^\s*(<|>)?\s*(\d+(?:[.,]\d+)?)\s*([a-zA-Zµ]+)", s)
    if m:
        out["value"] = float(m.group(2).replace(",", ".")); out["unit"] = UNITS.get(m.group(3).lower(), m.group(3))
        if m.group(1): out["qualifier"] = m.group(1)
    return out


def classify(h):
    t = h.lower()
    if re.search(r"100\s*(g|ml)", t): return "per100"
    if re.search(r"\brk\b|nrv|referanse|% av|%", t): return "pct_ri"
    if t.strip(): return "perserving"
    return None


def parse_tables(sec):
    p = TableP(); p.feed(sec); res = []
    for tb in p.tables:
        rows = tb["rows"]
        if not rows:
            continue
        hdr = rows[0]; body = rows[1:]
        has_hdr = (len(hdr) <= 4 and any(re.search(r"\bper\b|pr\.|100\s*(g|ml)|dose|porsjon|serving|\brk\b|innhold|%", c, re.I) for c in hdr)
                   and not any(re.search(r"\d+\s*(kcal|kj|mg|µg)", c, re.I) for c in hdr))
        if not has_hdr:
            body = rows
        cols = [(h, classify(h)) for h in hdr] if has_hdr else []
        items = []
        for r in body:
            if len(r) < 2:
                if r: items.append({"label": r[0], "values": {}, "raw": r})
                continue
            label, vals = r[0], r[1:]
            if cols and len(cols) >= len(vals):
                hs = cols[-len(vals):]
            else:
                hs = [(None, None)] * (len(vals) - len(cols)) + cols
            d = {}
            for (hh, kind), v in zip(hs, vals):
                pv = parse_val(v)
                if pv is None: continue
                key = kind or "unlabelled"
                if key in d: key += "_2"
                if hh: pv["col"] = hh
                d[key] = pv
            items.append({"label": label, "values": d, "raw": r})
        res.append({"heading": tb["heading"], "header": hdr if has_hdr else None, "items": items})
    return res


def meta(h, prop):
    m = re.search(r'itemprop="%s"\s+content="([^"]*)"' % prop, h)
    return H.unescape(m.group(1)) if m else None


def text(s):
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"</(p|li|div|h\d)>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\n\s*\n+", "\n", H.unescape(s)).strip()


def first(pat, t, flags=re.I):
    m = re.search(pat, t, flags)
    return m.group(1).strip() if m else None


def parse_product(h, url, src):
    rec = {"source": "bodystore-se", "source_url": url, "fetched_on": TODAY, "listing_category": src}
    m = re.search(r"<h1[^>]*>(.*?)</h1>", h, re.S)
    rec["name"] = text(m.group(1)) if m else None
    rec["sku"] = meta(h, "sku")
    rec["ean"] = meta(h, "gtin13") or meta(h, "gtin") or first(r'class="ean-code">(\d+)', h)
    rec["price"] = meta(h, "price"); rec["currency"] = meta(h, "priceCurrency")
    rec["availability"] = (meta(h, "availability") or "").split("/")[-1] or None
    m = re.search(r'itemprop="brand"[^>]*>(.*?)</', h, re.S) or re.search(r'"brand"\s*:\s*"([^"]+)"', h)
    rec["brand"] = text(m.group(1)) if m else None
    m = re.search(r'"@type":"BreadcrumbList".*?</script>', h, re.S)
    if m:
        rec["breadcrumb"] = re.findall(r'"name":"([^"]+)"', m.group(0))
    m = re.search(r'class="product-short-description"[^>]*>(.*?)</div>', h, re.S)
    rec["short_description"] = text(m.group(1)) if m else None
    m = re.search(r'<div class="nutrition-and-ingredients[^"]*">(.*)', h, re.S)
    sec = None
    if m:
        sec = m.group(1)
        end = re.search(r'</div>\s*</div>\s*</div>', sec)
        sec = sec[:end.start()] if end else sec[:60000]
    tables = parse_tables(sec) if sec else []
    rec["ingredients"] = rec["storage"] = rec["usage"] = None
    if sec:
        t = text(re.sub(r"<table.*?</table>", "", sec, flags=re.S))
        rec["ingredients"] = first(r"Ingredienser[^:\n]*:\s*(.+?)(?:\n|$)", t)
        rec["storage"] = first(r"Oppbevaring:\s*(.+?)(?:\n|$)", t)
        rec["nutrition_text"] = t[:3000]
    m = re.search(r'data-tab-content="tab-1">(.*?)<div class="item reviews', h, re.S)
    if m:
        d = text(m.group(1))
        rec["description"] = d[:4000]
        rec["usage"] = first(r"(?:Anbefalt daglig dose|Anbefalt dosering|Bruksanvisning|Dosering)[^:\n]*:\s*(.+?)(?:\n|$)", d)
        rec["servings_per_pack"] = first(r"(?:Antall|Doser)[^:\n]*pakning[^:\n]*:\s*(\d+)", d)
        if not rec["ingredients"]:
            rec["ingredients"] = first(r"Ingredienser[^:\n]*:\s*(.+?)(?:\n|$)", d)
    nm = rec.get("name") or ""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(kg|gram|g|ml|l|kapsler|kap|tabletter|tab|stk|st|kaps)\b", nm, re.I)
    if m:
        rec["pack_size"] = {"value": float(m.group(1).replace(",", ".")), "unit": m.group(2).lower(), "raw": m.group(0)}
    fl = [H.unescape(x) for x in re.findall(r'data-attr-value="([^"]+)"', h)]
    rec["variant_values"] = sorted(set(fl))[:60]
    has_n = any(("per100" in it["values"] or "perserving" in it["values"]) for tb in tables for it in tb["items"])
    rec["nutrition"] = None
    if has_n:
        rec["nutrition"] = {"tables": tables}
        flat = {}
        for tb in tables:
            for it in tb["items"]:
                flat.setdefault(it["label"], it["values"])
        rec["nutrients_flat"] = flat
        rec["nutrition_flag"] = "table"
    else:
        rec["nutrition_flag"] = "no_table" if not sec else "text_only_no_table"
    return rec


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    log(f"start bodystore scraper args={sys.argv[1:]}")
    load_robots()
    urls = collect()
    done = set()
    if os.path.exists(OUT):
        for ln in open(OUT, encoding="utf8"):
            try: done.add(json.loads(ln)["source_url"])
            except Exception: pass
    todo = [u for u in urls if u not in done]
    if limit:
        todo = todo[:limit]
    log(f"{len(urls)} urls, {len(done)} done, {len(todo)} to fetch")
    n = 0
    with open(OUT, "a", encoding="utf8") as f:
        for u in todo:
            h = fetch(u)
            if not h:
                continue
            try:
                rec = parse_product(h, u, urls[u])
            except Exception as e:
                log(f"PARSE ERR {u}: {e}"); continue
            f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush(); n += 1
            if n % 50 == 0:
                log(f"progress {n}/{len(todo)} reqs={REQS}")
    log(f"end: saved {n}, requests {REQS}")


if __name__ == "__main__":
    main()
