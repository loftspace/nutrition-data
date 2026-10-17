#!/usr/bin/env python3
"""Build candidate lists (archive-only or hidden products) from the CDX dumps. No network."""
import json, re, collections, os, sys
from urllib.parse import urlsplit, parse_qs
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
NONFOOD = re.compile(r"(hoodie|hettegenser|t-?skjorte|t-shirt|tshirt|shorts|singlet|sock|sokk|tights|leggings|\bbra\b|jogger|bukse|jakke|jacket|gloves?|hansker|strap|belt|belte|bag\b|duffle|sleeve|wrap|yoga|mat\b|matte|bench|barbell|skivestang|hantel|dumbbell|kettlebell|vekt|weight|rack|sko\b|shoe|\bcap\b|lue\b|caps\b|sweat|genser|undertoy|boxer|bikini|trunks|rashguard|gi\b|shaker|flaske\b|bottle|drikkeflaske|mobil|pod\b|blazepod|rullen|foam|roller|resistance|bands?\b|rope|hopp|skipping|deodorant|sjampo|shampoo|krem\b|cream|lotion|sapa|såpe|soap|tannkrem|parfy|mascara|sminke|makeup|makeup|neglelakk|hudpleie|ansikts|face|spray|duft|candle|lys\b|bok\b|book|t-skjorte|tank|vest|top\b|crop|polo|skjorte|bukser|trøye|trøya|vindjakke|hat\b|handle|box\b|gaveko|gift ?card|gavekort)", re.I)

def norm(u):
    p = urlsplit(u); return "https://" + p.netloc.replace(":80", "").replace(":443", "") + p.path.rstrip("/")

def load_cdx(f):
    d = {}
    for l in open(f, encoding="utf8"):
        ts, u, *_ = l.split()
        n = norm(u)
        if n not in d or ts > d[n][0]:
            d[n] = (ts, u)
    return d

def existing(shop):
    ex = set()
    for l in open(f"{ROOT}/data/raw/{shop}/products.jsonl", encoding="utf8"):
        r = json.loads(l)
        for k in ("source_url", "page_url"):
            if r.get(k): ex.add(norm(r[k]))
    return ex

def bodystore():
    cd = load_cdx(f"{ROOT}/data/raw/bodystore-discontinued/cdx.txt"); ex = existing("bodystore"); out = []
    for n, (ts, u) in cd.items():
        if n in ex: continue
        m = re.match(r"https://www\.bodystore\.no/([^/]+)/([^/]+)\.html$", n)
        if not m or "MASTER" in m.group(2): continue
        slug, sku = m.groups()
        if re.match(r"^(1000|S0|F09|TS|SH|KS|SO|SNA|STA|NDR|B\d|\d{5}(-|$)|\d{5}R)", sku) and not re.match(r"^A", sku): continue
        if NONFOOD.search(slug): continue
        out.append({"url": n, "fetch_url": u, "ts": ts, "slug": slug, "sku": sku})
    return out

def proteinfabrikken():
    cd = load_cdx(f"{ROOT}/data/raw/proteinfabrikken-discontinued/cdx.txt"); ex = existing("proteinfabrikken"); out = []
    for n, (ts, u) in cd.items():
        if n in ex: continue
        m = re.match(r"https://www\.proteinfabrikken\.no/([^/]+)/([^/]+)\.html$", n)
        if not m or "MASTER" in m.group(2): continue
        slug, sku = m.groups()
        if re.match(r"^(VENUM|VNM|TS\d|SI\d|KS\d|SNA|STA|NDR|10001|\d{9,})", sku): continue
        if NONFOOD.search(slug): continue
        out.append({"url": n, "fetch_url": u, "ts": ts, "slug": slug, "sku": sku})
    return out

def myprotein():
    ex = existing("myprotein"); byid = {}
    FOOD = ("sports-nutrition", "vitamins", "food", "protein", "health-wellbeing", "healthy-food-drink", "nutrition-and-supplements", "sports-nutrition-nc", "protein-nutrition", "snacks", "bars", "drinks")
    for l in open(f"{ROOT}/data/raw/myprotein-discontinued/cdx.txt", encoding="utf8"):
        ts, u, *_ = l.split()
        path = urlsplit(u).path
        m = re.match(r"^/p/([^/]+)/([^/]+)/(\d+)/?$", path) or re.match(r"^/([^/]+)/([^/]+)/(\d+)\.html$", path)
        if not m: continue
        cat, slug, pid = m.groups()
        if cat not in FOOD or NONFOOD.search(slug) or slug == "0": 
            if not (cat in FOOD and slug == "0"): continue
        if norm("https://www.myprotein.no/p/%s/%s/%s" % (cat, slug, pid)) in ex: continue
        cur = byid.get(pid)
        newer = "/p/" in path
        if cur is None or (newer and "/p/" not in cur["u"]) or (newer == ("/p/" in cur["u"]) and ts > cur["ts"]):
            byid[pid] = {"url": norm(u), "fetch_url": u, "u": u, "ts": ts, "slug": slug, "sku": pid}
    return list(byid.values())

def bulk():
    cd = load_cdx(f"{ROOT}/data/raw/bulk-discontinued/cdx_eu.txt"); ex = existing("bulk"); out = []
    for n, (ts, u) in cd.items():
        if n in ex: continue
        m = re.match(r"https://www\.bulk\.com/eu/products/([^/]+)/([^/]+)$", n)
        if not m: continue
        out.append({"url": n, "fetch_url": u, "ts": ts, "slug": m.group(1), "sku": m.group(2)})
    return out

def bodylab_no():
    cd = load_cdx(f"{ROOT}/data/raw/bodylab-no-discontinued/cdx.txt"); ex = existing("bodylab-no"); out = []
    skip = {"oppskrifter", "muskeloppbygging", "mat-snacks", "vekttap", "energi", "tilskudd", "klaer-utstyr", "tilbud", "pakker", "produkter", "team-bodylab", "artikler", "kom-i-gang", "you", "serier", "konkurransebetingelser", "guider", "spoer-ekspertene", "kampanjer", "sitemap", "search", "account", "checkout", "widgets", "navigation", "wishlist"}
    for n, (ts, u) in cd.items():
        if n in ex: continue
        m = re.match(r"https://www\.bodylab\.no/([a-z0-9][a-z0-9-]*)$", n)
        if not m or m.group(1) in skip: continue
        out.append({"url": n, "fetch_url": u, "ts": ts, "slug": m.group(1), "sku": m.group(1)})
    return out

def life_no():
    cd = load_cdx(f"{ROOT}/data/raw/life-no-discontinued/cdx.txt"); ex = existing("life-no"); out = []
    keep = ("mat-drikke", "kosttilskudd", "trening", "behov", "varemerker")
    for n, (ts, u) in cd.items():
        if n in ex: continue
        m = re.match(r"https://www\.life\.no/([a-z0-9-]+)/(.+)$", n)
        if not m or m.group(1) not in keep: continue
        parts = m.group(2).split("/")
        if len(parts) < 2 or "?" in n or NONFOOD.search(parts[-1]): continue
        out.append({"url": n, "fetch_url": u, "ts": ts, "slug": parts[-1], "sku": parts[-1]})
    return out

if __name__ == "__main__":
    for name, fn in [("bodystore", bodystore), ("proteinfabrikken", proteinfabrikken), ("myprotein", myprotein), ("bulk", bulk), ("bodylab-no", bodylab_no), ("life-no", life_no)]:
        if len(sys.argv) > 1 and name not in sys.argv[1:]:
            continue
        c = fn()
        json.dump(c, open(f"{ROOT}/data/raw/{name}-discontinued/candidates.json", "w"), ensure_ascii=False)
        print(name, len(c), [x["url"] for x in c[:3]])
