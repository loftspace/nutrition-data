#!/usr/bin/env python
"""Halsokostbolaget.com (Swedish health-food web shop, StarWebServer). Rules: ../README.md.
URLs: sitemap-products-sv-N.xml (/product/<slug>). Product pages carry a JSON-LD Product (name, sku, gtin, offers price SEK)
and HTML nutrition tables (Naringsinnehall per 30 g | per 100 g).
Usage: python halsokostbolaget.py [--limit N]
"""
import json
import re
import sys

from se_common import *

SOURCE = "halsokostbolaget"
BASE = "https://www.halsokostbolaget.com"


def discover(f, log):
    keep = []
    for i in range(1, 12):
        x = f.get(f"{BASE}/sitemap-products-sv-{i}.xml")
        urls = re.findall(r"<loc>([^<]+)</loc>", x or "")
        if not urls:
            break
        keep += [u for u in urls if "/product/" in u and not looks_nonfood(u.rsplit("/", 1)[1].replace("-", " "))]
        log(f"sitemap products {i}: {len(urls)} urls")
    keep = list(dict.fromkeys(keep))
    log(f"product pages kept={len(keep)}")
    return keep


def ld_all(s):
    out = []
    for t in s.find_all("script", type="application/ld+json"):
        try:
            d = json.loads(t.string or "", strict=False)
        except ValueError:
            continue
        out += d if isinstance(d, list) else [d]
    return out


def scrape(f, url):
    h = f.get(url)
    if not h:
        return []
    s = soup(h)
    lds = ld_all(s)
    prod = next((x for x in lds if isinstance(x, dict) and x.get("@type") == "Product"), None)
    if not prod:
        return []
    cats, brand_bc = [], None
    for x in lds:
        if isinstance(x, dict) and x.get("@type") == "BreadcrumbList":
            names = [norm_ws(i.get("name")) for i in x.get("itemListElement", [])]
            if names and names[0].lower().startswith("varum") and len(names) > 1:
                brand_bc = names[1]
            elif len(names) > len(cats):
                cats = names
    name = norm_ws(prod.get("name"))
    if looks_nonfood(name):
        return []
    brand = prod.get("brand")
    brand = brand.get("name") if isinstance(brand, dict) else brand
    brand = brand or brand_bc
    off = prod.get("offers") or {}
    if isinstance(off, list):
        off = off[0] if off else {}
    try:
        price = float(off.get("price")) if off.get("price") not in (None, "") else None
    except (TypeError, ValueError):
        price = None
    tables = []
    for tb in s.find_all("table"):
        tables.extend(parse_table_el(tb))
    nut, flags = pick_primary(tables)
    full = norm_ws(s.get_text(" "))
    ing = None
    m = re.search(r"Ingredienser?\s*:?\s*(.{15,1500}?)(?=Allergi|N.ringsv.rde|Bruksanvisning|F.rvaring|Tillverkare|$)", full)
    if m:
        ing = m.group(1).strip()
    ma = re.search(r"Allergi\w*\s*(?:information)?\s*:?\s*(.{5,300}?\.)", full)
    rec = base_record(SOURCE, url, name=name, brand=norm_ws(brand) if brand else None, sku=prod.get("sku"),
                      ean=ean_ok(prod.get("gtin13") or prod.get("gtin")), price_sek=price, categories=cats,
                      pack_size_text=pack_from_name(name), description=norm_ws(prod.get("description"))[:1500] or None, ingredients=ing,
                      allergens_text=ma.group(1).strip() if ma else None, nutrition=nut, nutrition_flags=flags)
    rec["extra_tables"] = [t for t in tables if t is not nut]
    return [rec]


if __name__ == "__main__":
    log = Logger(SOURCE)
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    f = Fetcher(SOURCE, BASE, log)
    log(f"START {SOURCE}")
    urls = discover(f, log)
    run_crawl(SOURCE, urls, scrape, f, log, limit=limit)
