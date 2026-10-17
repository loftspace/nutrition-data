#!/usr/bin/env python
"""Tyngre.se (Swedish training magazine + shop: own supplements, Barebells, drinks, protein porridge). Rules: ../README.md.
URLs: sitemap.xml, sections /kosttillskott /dryck /barebells /livsmedel /ovrigt /kroppsvard. Product pages carry a JSON-LD Product
(name, brand, sku, gtin13, offers price) and an HTML nutrition table (Per 100 g | Per portion).
Usage: python tyngre.py [--limit N]
"""
import json
import re
import sys

from se_common import *

SOURCE = "tyngre"
BASE = "https://tyngre.se"
KEEP = ("kosttillskott", "dryck", "barebells", "livsmedel", "ovrigt", "kroppsvard")


def discover(f, log):
    x = f.get(BASE + "/sitemap.xml")
    urls = re.findall(r"<loc>([^<]+)</loc>", x or "")
    keep = []
    for u in dict.fromkeys(urls):
        parts = u.split("/")
        if len(parts) >= 6 and parts[3] in KEEP and not looks_nonfood(parts[-1].replace("-", " ")):
            keep.append(u)
    log(f"sitemap urls={len(urls)} product-like pages kept={len(keep)}")
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
    bc = next((x for x in lds if isinstance(x, dict) and x.get("@type") == "BreadcrumbList"), None)
    cats = [norm_ws(i.get("name")) for i in (bc or {}).get("itemListElement", [])][:-1]
    name = norm_ws(prod.get("name"))
    if looks_nonfood(name):
        return []
    brand = prod.get("brand")
    brand = brand.get("name") if isinstance(brand, dict) else brand
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
