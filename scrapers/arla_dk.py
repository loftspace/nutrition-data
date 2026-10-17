#!/usr/bin/env python
"""Arla.dk product pages (producer page, ~315 products, EAN published). Sitemap -> page; nutrition and EAN are in
the page's embedded component props (HTML-escaped JSON): facts.values[] (per 100 g) and additionalInformation.ean.
Usage: python arla_dk.py"""
import re, sys, os, json, html
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nordic import *
import common

BASE = "https://www.arla.dk"
SM = BASE + "/sitemap.xml?type=Modules.Products.Business.SitemapUrlRewriter.ProductSitemapUrlWriter"


def discover(cl, log):
    t = cl.get(SM)
    u = [x.replace("&amp;", "&") for x in sitemap_locs(t or "") if "/produkter/" in x]
    log(f"sitemap product urls {len(u)}")
    return list(dict.fromkeys(u))


def raw_json_after(txt, key):
    i = txt.find(f'"{key}":')
    if i < 0:
        return None
    try:
        return json.JSONDecoder().raw_decode(txt[i + len(key) + 3:])[0]
    except Exception:
        return None


def scrape(cl, url):
    t = cl.get(url)
    if not t:
        return None
    u = html.unescape(t)
    facts = raw_json_after(u, "facts")
    rows = []
    if facts:
        for v in facts.get("values", []):
            rows.append((v["header"], v.get("perValue")))
            for s in v.get("subValues") or []:
                rows.append((s["header"], s.get("perValue")))
        for v in facts.get("extendedValues") or []:
            rows.append((v["header"], v.get("perValue")))
            for s in v.get("subValues") or []:
                rows.append((s["header"], s.get("perValue")))
    ean_m = re.search(r'"ean":"(\d{8,14})"', u)
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", t, re.S)
    ing_txt = None
    m = re.search(r'"ingredients":\{"ingredients":"(.*?)","allergies":"(.*?)"', u)
    if m:
        ing_txt = one(m.group(1)).replace("Ingredienser:", "").strip()
        allergens = one(m.group(2)).strip(" ,")
    else:
        allergens = None
    brand = url.split("/produkter/")[1].split("/")[0]
    hdr = (facts or {}).get("perValueColumnTitle") or "pr. 100 g"
    # Arla prints 'kJ / Kcal' and 'gram'
    rows = [(a, re.sub(r"\bgram\b", "g", b or "", flags=re.I)) for a, b in rows]
    rec = {"name": one(h1.group(1)) if h1 else None, "brand": brand, "ean": common.norm_ean(ean_m.group(1)) if ean_m else None,
           "ingredients": ing_txt, "allergens": allergens, "nutrition_column_header": hdr, "arla_material_number": (re.search(r'"materialNumber":"(\d+)"', u) or [None, None])[1]}
    rec.update(tables_to_record([(hdr, rows)] if rows else [], numfix=da_numbers))
    if not rows:
        return None
    return rec


if __name__ == "__main__":
    common.run_main("arla-dk", discover, scrape)
