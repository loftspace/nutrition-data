#!/usr/bin/env python
"""Tillskottsbolaget.se (Swedish supplement shop, Abicart-style HTML). Rules: ../README.md.
URLs: sitemap.xml (product pages are /sv/<slug>, single path segment; category pages are skipped after fetch).
Per page: name, price (SEK), brand, sku, EAN of the default variant, categories, nutrition table(s) in tab_4.
Usage: python tillskottsbolaget.py [--limit N]
"""
import json
import re
import sys

from se_common import *

SOURCE = "tillskottsbolaget"
BASE = "https://www.tillskottsbolaget.se"
NON_FOOD_PATHS = ("/sv/tillbehor", "/sv/tema", "/sv/rea", "/sv/nyheter")


def discover(f, log):
    x = f.get(BASE + "/sitemap.xml")
    urls = re.findall(r"<loc>([^<]+)</loc>", x or "")
    prods = []
    for u in urls:
        m = re.fullmatch(r"https://www\.tillskottsbolaget\.se/sv/([^/]+)", u)
        if m and not looks_nonfood(m.group(1).replace("-", " ")):
            prods.append(u)
    log(f"sitemap urls={len(urls)} candidate single-segment pages={len(prods)}")
    return list(dict.fromkeys(prods))


def scrape(f, url):
    h = f.get(url)
    if not h:
        return []
    if 'itemprop="price"' not in h:
        return []  # category / info page
    s = soup(h)
    name = norm_ws(s.find("h1").get_text(" ")) if s.find("h1") else None
    m = re.search(r'itemprop="price" content="([\d.,]+)"', h)
    price = float(m.group(1).replace(",", ".")) if m else None
    kl = {}
    m = re.search(r"var item = (\{.*?\});\s*klaviyo", h, re.S)
    if m:
        try:
            kl = json.loads(m.group(1))
        except ValueError:
            kl = {}
    brand = kl.get("Brand")
    if not brand:
        b = s.select_one("#VarumarkeFalt a")
        brand = norm_ws(b.get_text()) if b else None
    m = re.search(r'"EANFalt":"(\d*)"', h)
    ean = ean_ok(m.group(1)) if m else None
    cats = kl.get("Categories") or []
    if looks_nonfood(name or "") or (cats and cats[0] in ("Tillbehör", "Kläder", "Träningskläder")):
        return []
    nutri = s.select_one(".JS-CleaningFunc__nutrition")
    flags = []
    tables = []
    ingredients = allergens = None
    if nutri is not None:
        for tb in nutri.find_all("table"):
            tables.extend(parse_table_el(tb))
        txt = norm_ws(nutri.get_text(" "))
        mi = re.search(r"Ingrediens\w*\s*:?\s*(.*?)(?:Allergi\w*\s*(?:information)?\s*:|Näringsdeklaration|Bruksanvisning|Rekommenderat|$)", txt, re.I)
        if mi:
            ingredients = mi.group(1).strip()[:4000] or None
        ma = re.search(r"Allergi\w*\s*(?:information)?\s*:?\s*(.*)$", txt, re.I)
        if ma:
            allergens = ma.group(1).strip()[:1500] or None
        if not tables and nutri.find("img"):
            flags.append("nutrition_image_only")
    else:
        # fallback: any table in the page body that looks like a nutrition table
        for tb in s.find_all("table"):
            rows = table_to_rows(tb)
            if rows and re.search(r"(?i)energi|kcal|protein|fett", " ".join(r[0] for r in rows if r)):
                tables.extend(parse_table_el(tb, rows=rows))
        if tables:
            flags.append("nutrition_table_outside_nutrition_tab")
    nut, f2 = pick_primary(tables)
    flags += f2
    desc = None
    d = s.select_one("#tab_1")
    if d:
        desc = norm_ws(d.get_text(" "))[:1500] or None
    rec = base_record(SOURCE, url, name=name, brand=brand, sku=kl.get("SKU") or kl.get("ProductID"), ean=ean,
                      price_sek=price, categories=cats, pack_size_text=pack_from_name(name), description=desc,
                      ingredients=ingredients, allergens_text=allergens, nutrition=nut, nutrition_flags=flags)
    rec["extra_tables"] = [t for t in tables if t is not nut]
    rec["is_bundle"] = bool(re.match(r"\s*\d+\s*[x×]\s", name or "") or re.search(r"(paket|bundle|mix\s*&\s*match)", name or "", re.I))
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
