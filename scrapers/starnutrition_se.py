#!/usr/bin/env python
"""Starnutrition.se (Star Nutrition brand site, Salesforce Commerce Cloud like Gymgrossisten). Rules: ../README.md.
No prices and no EAN on the brand site (links out to retailers); value is the full Star Nutrition range with per-flavour
nutrition columns, ingredients per flavour and pack sizes.
URLs: category listings (?sz=100&start=N). Per page: h1, tab 'Naringsvarde' tables (columns are flavours, per 100 g),
ingredient paragraph(s).
Usage: python starnutrition_se.py [--limit N]
"""
import re
import sys

from se_common import *

SOURCE = "starnutrition-se"
BASE = "https://www.starnutrition.se"
CATS = ("kosttillskott-for-traning", "kosttillskott-for-halsa", "livsmedel-bars-och-dryck")


def discover(f, log):
    urls = {}
    for cat in CATS:
        start, total = 0, None
        while True:
            h = f.get(f"{BASE}/{cat}?sz=100&start={start}")
            if h is None:
                break
            if total is None:
                m = re.search(r'data-product-count="(\d+)"', h)
                total = int(m.group(1)) if m else 0
                log(f"listing {cat} total={total}")
            found = list(dict.fromkeys(re.findall(r'href="(/[^"?#]+/[^"/?#]+\.html)"', h)))
            new = [u for u in found if BASE + u not in urls]
            for u in new:
                urls[BASE + u] = cat
            log(f"listing {cat} start={start} links={len(found)} new={len(new)} cum={len(urls)}")
            start += 100
            if start >= (total or 0):
                break
    return [u for u in urls if not looks_nonfood(u.rsplit("/", 2)[-2].replace("-", " "))]


def scrape(f, url):
    h = f.get(url)
    if not h:
        return []
    s = soup(h)
    name = norm_ws(s.find("h1").get_text(" ")) if s.find("h1") else None
    if not name:
        return []
    pd = s.find(id="product-detail")
    sku = pd.get("data-pid") if pd is not None else None
    cats = [norm_ws(a.get_text(" ")) for a in s.select(".breadcrumb a")]
    flavours = []
    for b in s.select("button.variation-item"):
        v = norm_ws(b.get("aria-label", ""))
        v = re.sub(r"^V.lj\s+\w+\s+", "", v)
        if v and v not in flavours:
            flavours.append(v)
    tables = []
    for pane in s.select("[data-tab-content]"):
        for tb in pane.find_all("table"):
            rows = table_to_rows(tb)
            if rows and any(re.search(r"(?i)energi|kcal|protein", r[0]) for r in rows if r):
                tables.extend(parse_nutrition_table(rows))
    text = ""
    for pane in s.select("[data-tab-content]"):
        text += " " + norm_ws(pane.get_text(" "))
    ing_by, ing_generic = {}, None
    for m in re.finditer(r"Ingredienser?\s*(?:[–\-]\s*([^:]{1,60}?))?\s*:\s*(.*?)(?=Ingredienser?\s*[–\-:]|Allergi|N.ringsv|Anv.ndning|Information|$)", text):
        v = m.group(2).strip()[:4000]
        if m.group(1):
            ing_by[fold(m.group(1))] = v
        elif ing_generic is None:
            ing_generic = v
    m = re.search(r"Allergi\w*\s*(?:information)?\s*:\s*(.{0,300}?\.)", text)
    allergens = m.group(1).strip() if m else None
    og = s.select_one('meta[property="og:description"]')
    desc = norm_ws(og["content"])[:1500] if og and og.get("content") else None
    flags = []
    recs = []
    if not tables and s.find("img", src=re.compile(r"n[aä]ring|nutri", re.I)):
        flags.append("nutrition_image_only")
    # one record per page (flavours share the product); every flavour column kept in extra_tables
    fl_name = name.split(",")[-1].strip() if name.count(",") >= 2 else None
    nut, f2 = pick_primary(tables, fl_name)
    flags += [x for x in f2 if not (x == "no_nutrition_table" and "nutrition_image_only" in flags)]
    rec = base_record(SOURCE, url, name=name, brand="Star Nutrition", sku=sku, ean=None, price_sek=None, categories=cats,
                      pack_size_text=pack_from_name(name), description=desc, ingredients=(next(iter(ing_by.values())) if ing_by else ing_generic),
                      allergens_text=allergens, nutrition=nut, nutrition_flags=flags)
    rec["currency"] = None
    rec["extra_tables"] = [t for t in tables if t is not nut]
    rec["ingredients_by_flavour"] = ing_by or None
    rec["flavour_options"] = flavours
    rec["flavour_from_name"] = fl_name
    if len(tables) > 1 or len(flavours) > 1:
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
