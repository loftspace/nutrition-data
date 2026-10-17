#!/usr/bin/env python
"""Kung Markatta (Swedish organic food brand, kungmarkatta.se). Rules: ../README.md.
URLs: sitemap.xml /produkter/ pages (category pages are skipped after fetch: no nutrient table).
Per page: h1, article no + pack size table, 'Innehall per 100 gram' table, ingredients, allergens.
No price and no EAN on the site. Usage: python kungmarkatta.py [--limit N]
"""
import re
import sys

from se_common import *

SOURCE = "kungmarkatta"
BASE = "https://www.kungmarkatta.se"


def discover(f, log):
    x = f.get(BASE + "/sitemap.xml")
    urls = [u for u in re.findall(r"<loc>([^<]+)</loc>", x or "") if "/produkter/" in u]
    log(f"sitemap /produkter/ urls={len(urls)}")
    return list(dict.fromkeys(urls))


def scrape(f, url):
    h = f.get(url)
    if not h:
        return []
    s = soup(h)
    name = norm_ws(s.find("h1").get_text(" ")) if s.find("h1") else None
    props = {}
    nut_tables = []
    for tb in s.find_all("table"):
        rows = table_to_rows(tb)
        if not rows:
            continue
        if any(re.match(r"(?i)energi", r[0]) for r in rows):
            nut_tables.extend(parse_nutrition_table(rows, default_basis="per_100"))
        else:
            for r in rows:
                if len(r) >= 2:
                    props[r[0]] = r[1]
    if not nut_tables:
        return []  # category page / product without a nutrient table
    head = None
    for hd in s.select(".nutrients .title, .product-nutrients-section h2"):
        head = norm_ws(hd.get_text(" "))
        break
    ing = None
    st = s.select_one(".statement")
    if st:
        t = norm_ws(st.get_text(" "))
        ing = re.sub(r"^Ingredienser\s*:\s*", "", t)[:4000]
    path = [p.replace("-", " ") for p in url.split("/")[4:-1]]
    flags = []
    nd = nut_tables[0]
    if head and not re.search(r"100", head):
        flags.append("basis_heading_not_100g:" + head)
    if "per_100" not in [k for k in ("per_100",) if nd.get(k)]:
        flags.append("per100_missing")
    allergens = None
    if props.get("Allergener") or props.get("Spår av"):
        allergens = f"Allergener: {props.get('Allergener', '')}; Spår av: {props.get('Spår av', '')}"
    og = s.select_one('meta[property="og:description"]')
    desc = norm_ws(og["content"])[:1500] if og and og.get("content") else None
    size = props.get("Storlek")
    rec = base_record(SOURCE, url, name=f"Kung Markatta {name}" if name else None, brand="Kung Markatta", sku=props.get("Artikelnr"),
                      ean=None, price_sek=None, categories=path, pack_size_text=size, description=desc, ingredients=ing,
                      allergens_text=allergens, nutrition=nd, nutrition_flags=flags)
    rec["currency"] = None
    rec["storage"] = props.get("Förvaring")
    return [rec]


if __name__ == "__main__":
    log = Logger(SOURCE)
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    f = Fetcher(SOURCE, BASE, log)
    log(f"START {SOURCE}")
    urls = discover(f, log)
    run_crawl(SOURCE, urls, scrape, f, log, limit=limit)
