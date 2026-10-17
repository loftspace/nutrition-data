#!/usr/bin/env python
"""Goldenathlete.se (Abicart-style shop, same family as Tillskottsbolaget). Rules: ../README.md.
URLs: sitemap.xml, product pages are /sv/<slug> (single segment). Per page: JSON-LD Product with one Offer per variant
(sku, gtin, price), nutrition tables in #Produktinfo each preceded by an h3 '<Flavour> - Innehall'.
One record per offer (EAN); nutrition = first table (flavour_nutrition_shared_assumed) since offers do not name flavours.
Usage: python goldenathlete.py [--limit N]
"""
import html
import json
import re
import sys

from se_common import *

SOURCE = "goldenathlete"
BASE = "https://goldenathlete.se"


def discover(f, log):
    x = f.get(BASE + "/sitemap.xml")
    urls = re.findall(r"<loc>([^<]+)</loc>", x or "")
    prods = [u for u in urls if re.fullmatch(r"https://goldenathlete\.se/sv/[^/]+", u) and not looks_nonfood(u.rsplit("/", 1)[1].replace("-", " "))]
    log(f"sitemap urls={len(urls)} candidate single-segment pages={len(prods)}")
    return list(dict.fromkeys(prods))


def scrape(f, url):
    h = f.get(url)
    if not h:
        return []
    s = soup(h)
    prod = None
    for t in s.find_all("script", type="application/ld+json"):
        try:
            d = json.loads(t.string or "", strict=False)
        except ValueError:
            continue
        if isinstance(d, dict) and d.get("@type") == "Product":
            prod = d
            break
    if not prod:
        return []
    name = norm_ws(s.find("h1").get_text(" ")) if s.find("h1") else norm_ws(html.unescape(prod.get("name", "")))
    if not name or looks_nonfood(name):
        return []
    pi = s.find(id="Produktinfo")
    scope = pi if pi is not None else s
    tables = []
    for tb in scope.find_all("table"):
        rows = table_to_rows(tb)
        if not any(re.search(r"(?i)energi|kcal|protein|fett|kolhydrat", r[0]) for r in rows if r):
            continue
        prev = tb.find_previous(["h2", "h3", "h4"])
        title = None
        if prev is not None:
            title = norm_ws(re.sub(r"\s*[–-]\s*Inneh[åa]ll.*$", "", prev.get_text(" ")))
        for nd in parse_nutrition_table(rows, title=title):
            if title and not nd.get("flavour_label"):
                nd["flavour_label"] = title
            tables.append(nd)
    # ingredients / allergens
    ing_by, all_by = {}, {}
    ing_generic = all_generic = None
    full = norm_ws(scope.get_text(" ")) if pi is not None else ""
    for m in re.finditer(r"Ingredienser?\s*(?:[–\-]\s*([^:]{1,60}?))?\s*:\s*(.*?)(?=Allergi|Ingredienser?\s*[–\-:]|$)", full):
        v = m.group(2).strip()[:4000]
        if m.group(1):
            ing_by[fold(m.group(1))] = v
        elif ing_generic is None:
            ing_generic = v
    m = re.search(r"Allergi\w*\s*(?:information)?\s*:\s*(.{0,300}?\.)", full)
    if m:
        all_generic = m.group(1).strip()[:1500]
    nut, flags = pick_primary(tables)
    if not tables and scope.find("img", src=re.compile(r"n[aä]ring|nutri", re.I)):
        flags.append("nutrition_image_only")
    offers = prod.get("offers") or []
    if isinstance(offers, dict):
        offers = [offers]
    desc = norm_ws(soup(html.unescape(prod.get("description") or "")).get_text(" "))[:1500] or None
    recs = []
    seen = set()
    for o in offers or [{}]:
        it = o.get("itemOffered") or {}
        ean = ean_ok(it.get("gtin13") or it.get("gtin8") or it.get("gtin") or it.get("gtin12"))
        sku = it.get("sku")
        key = (sku, ean)
        if key in seen:
            continue
        seen.add(key)
        try:
            price = float(o.get("price")) if o.get("price") else None
        except ValueError:
            price = None
        rec = base_record(SOURCE, f"{url}#{sku}" if sku else url, page_url=url, name=name, brand=None, sku=sku, ean=ean, price_sek=price,
                          categories=[], pack_size_text=pack_from_name(name), description=desc,
                          ingredients=(next(iter(ing_by.values())) if ing_by else ing_generic), allergens_text=all_generic, nutrition=nut,
                          nutrition_flags=list(flags) + (["flavour_unknown_for_offer"] if len(offers) > 1 else []))
        rec["extra_tables"] = [t for t in tables if t is not nut]
        rec["ingredients_by_flavour"] = ing_by or None
        rec["flavours_listed"] = [t.get("flavour_label") for t in tables if t.get("flavour_label")]
        if len(tables) > 1 or len(offers) > 1:
            rec["flavour_nutrition_shared_assumed"] = True
        recs.append(rec)
    return recs


if __name__ == "__main__":
    log = Logger(SOURCE)
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    f = Fetcher(SOURCE, BASE, log)
    log(f"START {SOURCE}")
    urls = discover(f, log)
    run_crawl(SOURCE, urls, scrape, f, log, limit=limit)
