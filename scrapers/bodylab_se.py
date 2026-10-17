#!/usr/bin/env python
"""Bodylab.se (Shopware 6). Rules: ../README.md.
URLs: /produkter?p=N listing (48 per page, ~153 products) + root-level slugs in the sitemap.
Per page: JSON-LD Product (name, sku, brand, gtin13, price SEK), breadcrumb, nutrition tables
(.ingredient-nutrition-table), ingredient text blocks, flavour list from the shop's own htmx endpoint.
Usage: python bodylab_se.py [--limit N]
"""
import html
import json
import re
import sys

from se_common import *

SOURCE = "bodylab-se"
BASE = "https://www.bodylab.se"
CAT_SLUGS = {"recept", "muskeluppbyggnad", "mat-snacks", "viktminskning", "energi", "tillskott", "klaeder-utrustning", "erbjudande",
             "paket", "produkter", "team-bodylab", "artiklar", "kom-igaang", "you", "serier", "kundservice", "information", "kampanjer",
             "taevlingsvillkor", "fraaga-experterna", "rcp_recipe", "rcp_category"}


def discover(f, log):
    urls = {}
    p = 1
    while p < 12:
        h = f.get(f"{BASE}/produkter?p={p}")
        if not h:
            break
        links = re.findall(r'href="(https://www\.bodylab\.se/[^"?#]+)"\s+class="product-name"', h)
        new = [u for u in links if u not in urls]
        for u in new:
            urls[u] = 1
        log(f"listing p={p} links={len(links)} new={len(new)} total={len(urls)}")
        if not new:
            break
        p += 1
    x = f.get(BASE + "/sitemap.xml")
    # sitemap index -> gz files not parsed (gz); root level slugs are also reachable from the listing, so only report
    log(f"listing total {len(urls)} product urls")
    return list(urls)


def jsonld(s, typ):
    for t in s.find_all("script", type="application/ld+json"):
        try:
            d = json.loads(t.string or "")
        except ValueError:
            continue
        for x in (d if isinstance(d, list) else [d]):
            if isinstance(x, dict) and x.get("@type") == typ:
                return x
    return None


def scrape(f, url):
    h = f.get(url)
    if not h:
        return []
    s = soup(h)
    prod = jsonld(s, "Product")
    if not prod:
        return []
    bc = jsonld(s, "BreadcrumbList")
    cats = [html.unescape(x.get("name") or "") for x in (bc or {}).get("itemListElement", [])][1:-1] if bc else []
    off = prod.get("offers") or {}
    if isinstance(off, list):
        off = off[0] if off else {}
    name = norm_ws(prod.get("name"))
    if looks_nonfood(name) or (cats and cats[0] in ("Kläder & Utrustning", "Klader & Utrustning")):
        return []
    brand = (prod.get("brand") or {}).get("name") if isinstance(prod.get("brand"), dict) else prod.get("brand")
    tables = []
    for tb in s.select("table.ingredient-nutrition-table__table"):
        tables.extend(parse_table_el(tb))
    flags = []
    nut, f2 = pick_primary(tables)
    flags += f2
    if not tables and s.select_one(".js-ingredients-content img"):
        flags.append("nutrition_image_only")
    ingredients = allergens = None
    texts = {}
    for sec in s.select(".ingredient-text-section"):
        t = sec.select_one(".ingredient-text-section__title")
        c = sec.select_one(".ingredient-text-section__content")
        if t and c:
            texts[norm_ws(t.get_text(" "))] = norm_ws(c.get_text(" "))
    for k, v in texts.items():
        if k.lower().startswith("ingrediens"):
            ingredients = v[:4000]
        elif k.lower().startswith("allergi"):
            allergens = v[:1500]
    flavours = []
    m = re.search(r'hx-get="(/ingredient/variants/[^"]+)"', h)
    if m:
        x = f.get(BASE + m.group(1).replace("&amp;", "&"))
        if x:
            flavours = [norm_ws(o.get_text(" ")) for o in soup(x).find_all("option") if norm_ws(o.get_text(" "))]
    rec = base_record(SOURCE, url, name=name, brand=norm_ws(brand) if brand else None, sku=prod.get("sku"), ean=ean_ok(prod.get("gtin13") or prod.get("gtin")),
                      price_sek=off.get("price"), categories=cats, pack_size_text=pack_from_name(name),
                      description=norm_ws(prod.get("description"))[:1500] or None, ingredients=ingredients, allergens_text=allergens,
                      nutrition=nut, nutrition_flags=flags)
    rec["extra_tables"] = [t for t in tables if t is not nut]
    rec["text_sections"] = {k: v[:1500] for k, v in texts.items() if not k.lower().startswith(("ingrediens", "allergi"))}
    rec["flavour_options"] = flavours
    rec["is_bundle"] = bool(re.search(r"\b(box|paket|bundle)\b|\d+\s*x\s*\d", name, re.I))
    if flavours:
        rec["flavour_nutrition_shared_assumed"] = True
    return [rec]


if __name__ == "__main__":
    log = Logger(SOURCE)
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    f = Fetcher(SOURCE, BASE, log)
    log(f"START {SOURCE}")
    urls = discover(f, log)
    run_crawl(SOURCE, urls, scrape, f, log, limit=limit)
