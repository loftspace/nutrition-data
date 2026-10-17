#!/usr/bin/env python
"""Nemlig.com (Danish online grocer). robots.txt allows /, product urls are in the site's own googleproductsitemap.
The site's SPA loads each product page as JSON from the page URL itself with ?GetAsJson=1 (no login, no token);
we request exactly that. DeclarationLabel html holds the 'Naeringsindhold pr. 100 g' table.
Usage: python nemlig_dk.py [max_pages] [max_hours]"""
import re, sys, os, json, html
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nordic import *
import common

BASE = "https://www.nemlig.com"


def discover(cl, log):
    t = cl.get(BASE + "/googleproductsitemap")
    urls = [u for u in sitemap_locs(t or "") if re.search(r"-\d+$", u)]
    log(f"sitemap product urls {len(urls)}")
    return list(dict.fromkeys(urls))


_FAIL = {"n": 0}


def scrape(cl, url):
    t = get_soft(cl, url + "?GetAsJson=1")
    if not t:
        # timeouts / non-200 on single pages: remember for a later retry, do not treat as a block unless it persists
        _FAIL["n"] += 1
        open(os.path.join(os.path.dirname(common.out_paths("nemlig-dk")), "failed.txt"), "a", encoding="utf8").write(url + "\n")
        if _FAIL["n"] >= 30:
            raise common.Blocked("30 failed pages in one run")
        return False
    _FAIL["n"] = 0
    try:
        d = json.loads(t)
    except Exception:
        return None
    spot = next((s for s in d.get("content", []) if s.get("TemplateName") == "productdetailspot"), None)
    if not spot:
        return None
    label = spot.get("DeclarationLabel") or ""
    tables = []
    for tm in re.finditer(r"<table.*?</table>", label, re.S):
        tb = tm.group(0)
        head = re.search(r"<thead>.*?<td[^>]*>(.*?)</td>", tb, re.S)
        header = one(head.group(1)) if head else ""
        rows = []
        for tr in re.findall(r"<tr>(.*?)</tr>", re.sub(r"<thead>.*?</thead>", "", tb, flags=re.S), re.S):
            tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
            if len(tds) >= 2:
                rows.append((one(tds[0]), one(tds[1])))
        if rows:
            tables.append((header, rows))
    if not tables:
        dec = spot.get("Declarations") or {}
        if dec.get("ShowDeclarations"):
            rows = [("Energi", f'{dec.get("EnergyKj")} kJ / {dec.get("EnergyKcal")} kcal'), ("Fedt", f'{dec.get("NutritionalContentFat")} g'),
                    ("heraf mættede fedtsyrer", f'{dec.get("SaturatedFattyAcid")} g'), ("Kulhydrat", f'{dec.get("NutritionalContentCarbohydrate")} g'),
                    ("heraf sukkerarter", f'{dec.get("Sugar")} g'), ("Kostfibre", f'{dec.get("DietaryFiber")} g'),
                    ("Protein", f'{dec.get("NutritionalContentProtein")} g'), ("Salt", f'{dec.get("Salt")} g')]
            tables.append(("Declarations (structured fields; basis not stated)", rows))
    if not tables:
        return None
    ing = one(label.split("<table")[0]) or None
    attrs = {a["Key"]: a["Value"] for a in spot.get("Attributes") or []}
    meta = d.get("MetaData") or {}
    rec = {"name": spot.get("Name"), "brand": spot.get("Brand") or (attrs.get("Brand") or [None])[0], "ean": None,
           "ean_note": "nemlig.com does not publish EAN", "nemlig_id": spot.get("Id"), "pack_size_raw": spot.get("Description"),
           "category": spot.get("Category"), "subcategory": spot.get("SubCategory"),
           "category_path": meta.get("CategoryPath"), "main_group": spot.get("ProductMainGroupName"),
           "group": spot.get("ProductCategoryGroupName"), "subgroup": spot.get("ProductSubGroupName"),
           "price_dkk": spot.get("Price"), "unit_price": spot.get("UnitPrice"), "ingredients": ing,
           "attributes": attrs, "description": one(spot.get("Text") or "")[:500]}
    rec.update(tables_to_record(tables, numfix=ident))
    p = rec.get("nutrition_per100") or {}
    if p and all(v.get("value") == 0 for v in p.values()):
        rec["nutrition_flag"] = (rec.get("nutrition_flag") or "") + "|all_zero_values_probably_placeholder_or_non_food"
    return rec


if __name__ == "__main__":
    mp = int(sys.argv[1]) if len(sys.argv) > 1 else None
    hrs = float(sys.argv[2]) if len(sys.argv) > 2 else None
    log = common.Logger("nemlig-dk")
    cl = common.Client("nemlig-dk", log)
    urls = discover(cl, log)
    if mp:
        urls = urls[:mp]
    run_big("nemlig-dk", urls, scrape, max_seconds=hrs * 3600 if hrs else None)
