#!/usr/bin/env python
"""Nutramino.com /da-dk/ products (Webflow, ~24 products). Product list page -> product pages; nutrition is a
plain-text block 'NUTRITION INFORMATION Typical Values Per 100 g  Per X g ...' (English labels).
Usage: python nutramino_dk.py"""
import re, sys, os, html
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nordic import *
import common

BASE = "https://www.nutramino.com"
LABELS = r"Energy|Fat|Of Which Saturates|Of Which Mono-?unsaturates|Of Which Polyunsaturates|Carbohydrate|Of Which Sugars|Of Which Polyols|Of Which Starch|Fib(?:re|er)|Protein|Salt|Sodium|Vitamin [A-Z0-9]+|Thiamin|Riboflavin|Niacin|Folic acid|Folate|Biotin|Pantothenic acid|Calcium|Magnesium|Iron|Zinc|Potassium|Phosphorus|Iodine|Selenium|Copper|Manganese|Chromium|Molybdenum|Caffeine|Taurine|Creatine|Cholesterol"
DIS = "Typical Values|Per 100 ?(?:g|ml)|Per \\d"


def discover(cl, log):
    t = cl.get(BASE + "/da-dk/products")
    u = sorted(set(re.findall(r'href="(/da-dk/product/[^"#?]+)"', t or "")))
    log(f"product links {len(u)}")
    return [BASE + x for x in u]


def scrape(cl, url):
    t = cl.get(url)
    if not t:
        return None
    txt = clean(re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", t, flags=re.S | re.I))
    txt = re.sub(r"\s+", " ", txt)
    m = re.search(r"Typical Values(.*?)(?:INGREDIENTS|Ingredients)(.*?)(?:ALLERGEN|Allergen|DIRECTIONS|Directions|STORAGE|©|$)", txt)
    if not m:
        return None
    block, ing = m.group(1), m.group(2)
    hdr = re.findall(r"Per (\d+(?:[.,]\d+)?\s*(?:g|ml))", block)
    pieces = re.split(rf"\b({LABELS})\b", block)
    rows100, rowsS = [], []
    for i in range(1, len(pieces) - 1, 2):
        lab, val = pieces[i], pieces[i + 1]
        if lab == "Energy":
            pairs = re.findall(r"(\d+(?:[.,]\d+)?)\s*kj\s*/\s*(\d+(?:[.,]\d+)?)\s*kcal", val, re.I)
            if pairs:
                rows100.append((lab, f"{pairs[0][0]} kJ / {pairs[0][1]} kcal"))
                if len(pairs) > 1:
                    rowsS.append((lab, f"{pairs[1][0]} kJ / {pairs[1][1]} kcal"))
            continue
        vs = re.findall(r"(<?\d+(?:[.,]\d+)?)\s*(g|mg|µg|ug|mcg)\b", val)
        if vs:
            rows100.append((lab, f"{vs[0][0]} {vs[0][1]}"))
            if len(vs) > 1:
                rowsS.append((lab, f"{vs[1][0]} {vs[1][1]}"))
    tables = []
    if rows100:
        tables.append(("Typical Values Per 100 g", rows100))
    if rowsS:
        tables.append((f"Per serving {hdr[1] if len(hdr) > 1 else ''}".strip(), rowsS))
    tt = re.search(r"<title>(.*?)</title>", t, re.S)
    rec = {"name": re.sub(r"\s*[|\-–].*$", "", one(tt.group(1))) if tt else url.rsplit("/", 1)[-1], "slug": url.rsplit("/", 1)[-1], "brand": "Nutramino", "ean": None,
           "ean_note": "nutramino.com does not publish EAN", "ingredients": one(ing)[:3000],
           "pack_size_raw": common.pack_size(url.rsplit("/", 1)[-1].replace("-", " ")), "serving_text": hdr[1] if len(hdr) > 1 else None,
           "language": "en (page text), da-dk site"}
    rec.update(tables_to_record(tables, numfix=ident))
    return rec


if __name__ == "__main__":
    common.run_main("nutramino-dk", discover, scrape)
