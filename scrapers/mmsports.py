#!/usr/bin/env python
"""MMSports.se (Swedish supplement and health-food chain, server-rendered). Rules: ../README.md.
URLs: sitemap.xml product pages (.html) under /kosttillskott, /livsmedel-halsa, /rea (clothing and gear skipped).
Per page: name, price SEK, art no, brand (Tillverkare), EAN (info table), nutrition tables (one per flavour, flavour names are not
printed next to them -> first table used, flavour_nutrition_shared_assumed), ingredients.
Quirks handled: '<br>' separated label/value pairs in one cell (fat + saturated fat), digits split by spaces ('16 04 kJ'),
header cell holding both bases ('per 100 g och per portion 30 g').
Usage: python mmsports.py [--limit N]
"""
import re
import sys

from se_common import *

SOURCE = "mmsports"
BASE = "https://www.mmsports.se"
KEEP = ("kosttillskott", "livsmedel-halsa", "livsmedelhalsa", "rea")


def discover(f, log):
    x = f.get(BASE + "/sitemap.xml")
    urls = re.findall(r"<loc>([^<]+)</loc>", x or "")
    prods = []
    for u in urls:
        if not u.endswith(".html"):
            continue
        seg = u.split("/")[3].lower() if len(u.split("/")) > 3 else ""
        if seg in KEEP and not looks_nonfood(u.rsplit("/", 1)[1].replace("-", " ").replace(".html", "")):
            prods.append(u)
    log(f"sitemap urls={len(urls)} candidate product pages={len(prods)}")
    return list(dict.fromkeys(prods))


def fix_rows(rows):
    """Turn a title row 'per 100 g och per portion 30 g' + unlabeled value columns into explicit column headers."""
    if not rows:
        return rows
    head = rows[0]
    ncols = len(head)
    title = norm_ws(head[0]) if head else ""
    uniq = {norm_ws(c) for c in head if norm_ws(c)}
    if len(uniq) == 1 and ncols >= 2:
        t = title
        has100 = re.search(r"100\s*(g|ml)", t, re.I)
        m = re.search(r"portion\s*(?:om|[\(:])?\s*(\d+(?:[.,]\d+)?\s*(?:g|ml))", t, re.I) or re.search(r"per\s+(?:portion|port\.?|dos|bar|st[aä]ng|kapsel|tablett)\s*(\d+(?:[.,]\d+)?\s*(?:g|ml))?", t, re.I)
        if ncols == 3 and has100:
            serv = "Per portion" + (f" ({m.group(1)})" if m and m.groups() and m.group(1) else "")
            new_head = ["Näringsinnehåll", "Per 100 g" if re.search(r"100\s*g", t, re.I) else "Per 100 ml", serv]
            return [new_head] + rows[1:]
        if ncols == 2 and has100:
            return [["Näringsinnehåll", "Per 100 g" if re.search(r"100\s*g", t, re.I) else "Per 100 ml"]] + rows[1:]
    return rows


def scrape(f, url):
    h = f.get(url)
    if not h:
        return []
    s = soup(h)
    name_el = s.find("h1")
    name = norm_ws(name_el.get_text(" ")) if name_el else None
    if not name or looks_nonfood(name):
        return []
    m = re.search(r'itemprop="price" content="([\d.,]+)"', h)
    price = float(m.group(1).replace(",", ".")) if m else None
    props = {}
    for tr in s.select("tr"):
        k = tr.select_one("td.property-name")
        v = tr.select_one("td.property-value, td#product_code")
        if k and v:
            props[norm_ws(k.get_text(" ")).rstrip(":")] = norm_ws(v.get_text(" "))
    ean = ean_ok(props.get("EAN"))
    brand = props.get("Tillverkare")
    sku = props.get("Artnr") or (re.search(r'itemprop="sku" content="([^"]+)"', h) or [None, None])[1]
    path = url.split("/")[3:-1]
    cats = [p.replace("-", " ") for p in path]
    tables = []
    for tb in s.find_all("table"):
        if not re.search(r"Energi|kcal|Inneh.ll per|N.ringsinneh.ll|N.ringsv.rde", tb.get_text(" ")):
            continue
        rows = fix_rows(table_to_rows_br(tb, collapse_digit_spaces=True))
        tables.extend(parse_nutrition_table(rows))
    flags = []
    # drop exact duplicate tables (the page repeats flavour tables for mobile/desktop)
    uniq, seen = [], set()
    for t in tables:
        key = repr(t["per_100"]) + repr(t["per_serving"])
        if key not in seen:
            seen.add(key)
            uniq.append(t)
    tables = uniq
    nut, f2 = pick_primary(tables)
    flags += f2
    # ingredients: first 'Ingredienser:' paragraph(s)
    ingredients = None
    full = norm_ws(s.get_text(" "))
    mi = re.search(r"Ingredienser\s*:\s*(.{20,1500}?)(?=Allergi|N.ringsinneh|Bruksanvisning|Rekommenderat|Anv.ndning|$)", full)
    if mi:
        ingredients = mi.group(1).strip()
    ma = re.search(r"Allergi\w*\s*(?:information|r[aå]d)?\s*:\s*(.{5,300}?\.)", full)
    allergens = ma.group(1).strip() if ma else None
    og = s.select_one('meta[property="og:description"]')
    desc = norm_ws(og["content"])[:1500] if og and og.get("content") else None
    if not tables and s.find("img", src=re.compile(r"n[aä]ring|nutri", re.I)):
        flags.append("nutrition_image_only")
    rec = base_record(SOURCE, url, name=name, brand=brand, sku=sku, ean=ean, price_sek=price, categories=cats,
                      pack_size_text=pack_from_name(name), description=desc, ingredients=ingredients, allergens_text=allergens,
                      nutrition=nut, nutrition_flags=flags)
    rec["extra_tables"] = [t for t in tables if t is not nut][:20]
    if len(tables) > 1:
        rec["flavour_nutrition_shared_assumed"] = True
    return [rec]


if __name__ == "__main__":
    log = Logger(SOURCE)
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    f = Fetcher(SOURCE, BASE, log)
    log(f"START {SOURCE}")
    urls = discover(f, log)
    run_crawl(SOURCE, urls, scrape, f, log, limit=limit)
