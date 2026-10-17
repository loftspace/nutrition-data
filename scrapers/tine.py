import sys, json, re, os
from urllib.parse import unquote, quote
from bs4 import BeautifulSoup
from common import *

SOURCE = "tine"
BASE = "https://www.tine.no"
EXTRA = os.path.join(ROOT, "data", "raw", SOURCE, "_extra_urls.json")
PROD_RE = re.compile(r'href="(/merkevarer/[^"/#?]+/produkter/[^"#?]+)"')
BRAND_RE = re.compile(r'href="(/merkevarer/[^"/#?]+)"')


def fix(path):
    # keep percent-encoding as the site wrote it
    return BASE + path


def add_extra(urls):
    cur = set(json.load(open(EXTRA, encoding="utf-8"))) if os.path.exists(EXTRA) else set()
    n = len(cur)
    cur |= set(urls)
    os.makedirs(os.path.dirname(EXTRA), exist_ok=True)
    json.dump(sorted(cur), open(EXTRA, "w", encoding="utf-8"))
    return len(cur) - n


def discover(cl, log):
    prods, brands, cats = set(), set(), set()
    home = cl.get(BASE + "/produkter") or ""
    cats |= set(re.findall(r'href="(/produkter/[^"/#?]+)"', home))
    brands_page = cl.get(BASE + "/merkevarer") or ""
    brands |= set(BRAND_RE.findall(brands_page)) - {"/merkevarer"}
    for c in sorted(cats):
        h = cl.get(BASE + c) or ""
        prods |= set(PROD_RE.findall(h))
        brands |= set(BRAND_RE.findall(h)) - {"/merkevarer"}
    seen = set()
    for b in sorted(brands):
        if b in seen:
            continue
        seen.add(b)
        h = cl.get(BASE + b) or ""
        prods |= set(PROD_RE.findall(h))
    log(f"discovered {len(cats)} categories, {len(brands)} brands, {len(prods)} product links")
    out = set(fix(p) for p in prods)
    if os.path.exists(EXTRA):
        out |= set(json.load(open(EXTRA, encoding="utf-8")))
    return sorted(out)


def acc(s, ident):
    el = s.find(id=ident)
    return el


def scrape(cl, url):
    html = cl.get(url)
    if not html:
        return None
    # queue sibling product links for a later pass
    sib = set(fix(p) for p in PROD_RE.findall(html))
    new = add_extra(sib)
    s = BeautifulSoup(html, "lxml")
    title = s.title.get_text(" ", strip=True).split(" | ")[0] if s.title else None
    h = s.find(["h1", "h2"], class_=re.compile("heading|title"))
    name = title or (h.get_text(" ", strip=True) if h else None)
    brand_slug = unquote(url.split("/")[4]) if "/merkevarer/" in url else None
    tables = []
    nut = s.find(id="accordion__nutrition")
    nut_title = None
    btn = s.find(id="accordion_btn_nutrition")
    if btn:
        nut_title = btn.get_text(" ", strip=True)
    if nut:
        rows = []
        for tr in nut.find_all("tr"):
            tds = [re.sub(r"\s+", " ", td.get_text(" ", strip=True)).replace("</nutrient>", "").strip() for td in tr.find_all("td")]
            if len(tds) >= 2 and tds[1]:
                rows.append((tds[0], tds[1]))
        if rows:
            tb = make_table(nut_title or "Næringsinnhold pr. 100g", rows)
            if tb["basis"] == "unknown":
                tb["basis"] = "per_100"
            tables.append(tb)
    ing = acc(s, "accordion__ingredients")
    alg = acc(s, "accordion__allergener")
    pk = acc(s, "accordion__packaging")
    packs = [li.get_text(" ", strip=True) for li in pk.find_all("li")] if pk else []
    desc = None
    sku = None
    pm = s.find(class_="productMap")
    if pm and pm.get("sku"):
        sku = pm.get("sku")
    eans = [norm_ean(x) for x in re.findall(r"\b70\d{11}\b", html)]
    eans = [e for e in dict.fromkeys(eans) if e]
    rec = {
        "name": name, "brand": brand_slug, "tine_sku": sku,
        "ean": eans[0] if eans else None,
        "pack_size_raw": ", ".join(packs) or pack_size(name),
        "packagings": packs,
        "ingredients": ing.get_text(" ", strip=True) if ing else None,
        "allergens_raw": alg.get_text(" ", strip=True) if alg else None,
        "nutrition": {"tables": tables} if tables else None,
        "nutrition_per100": per100_from_tables(tables) if tables else None,
        "nutrition_flag": None if tables else "no_nutrition_on_page",
        "ean_note": "tine.no does not publish EAN on product pages" if not eans else None,
    }
    return rec


if __name__ == "__main__":
    run_main(SOURCE, discover, scrape, limit=int(sys.argv[1]) if len(sys.argv) > 1 else None)
