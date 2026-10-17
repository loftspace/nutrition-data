#!/usr/bin/env python
"""Helsam.dk (Shopify health-food store). Product list from the storefront's public /products.json (not disallowed
in robots.txt); only product_type 'Foedevarer' and 'Kosttilskud' are fetched. Product page: metafield spec list under
'Naeringsindhold' (+ gtin13 / barcode in page JSON). Usage: python helsam_dk.py [max_pages]"""
import re, sys, os, json, html
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nordic import *
import common

BASE = "https://helsam.dk"
KEEP = {"Fødevarer", "Kosttilskud"}
META = {}


def discover(cl, log):
    urls, page = [], 1
    while True:
        t = cl.get(f"{BASE}/products.json?limit=250&page={page}")
        if not t:
            break
        prods = json.loads(t).get("products", [])
        if not prods:
            break
        for p in prods:
            if p.get("product_type") in KEEP:
                u = f"{BASE}/products/{p['handle']}"
                urls.append(u)
                META[u] = {"title": p["title"], "vendor": p.get("vendor"), "product_type": p.get("product_type"), "tags": p.get("tags"),
                           "price_dkk": (p["variants"][0].get("price") if p.get("variants") else None), "sku": (p["variants"][0].get("sku") if p.get("variants") else None)}
        page += 1
    log(f"products.json pages {page-1}; kept {len(urls)} (types {sorted(KEEP)})")
    return urls


def energy_fix(label, val):
    m = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*/\s*(\d+(?:[.,]\d+)?)\s*", val or "")
    if m and re.match(r"energi", label, re.I):
        return f"{m.group(1)} kJ / {m.group(2)} kcal"
    return val


def scrape(cl, url):
    if not META:
        discover(cl, lambda *_: None)
    t = cl.get(url)
    if not t:
        return None
    chunks = re.split(r'<h2 class="disclosure__title', t)
    tables, ing = [], None
    for ch in chunks[1:]:
        title = one(ch.split("</h2>")[0].split(">", 1)[-1])
        body = ch.split("</h2>", 1)[-1]
        body = body.split("<hr", 1)[0]
        if re.match(r"Ingrediens", title, re.I):
            ing = one(body)[:3000]
        if re.match(r"N[æe]ring|Indhold|N[æe]rings", title, re.I):
            for blk in re.split(r'<div class="product-spec__top-content', body):
                hh = re.search(r"<h\d>(.*?)</h\d>", blk, re.S)
                header = one(hh.group(1)) if hh else title
                rows = []
                for a, b in re.findall(r'product-spec__label[^>]*>\s*(.*?)\s*</div>\s*<div class="product-spec__value[^>]*>(.*?)</div>', blk, re.S):
                    a, b = one(a), one(b)
                    rows.append((a, energy_fix(a, b)))
                if rows:
                    tables.append((header, rows))
            for tb in re.findall(r"<table.*?</table>", body, re.S):
                trs = [[one(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S)] for tr in re.findall(r"<tr.*?</tr>", tb, re.S)]
                if len(trs) < 2 or len(trs[0]) < 2:
                    continue
                header = (title + ": " + trs[0][1]).strip()
                rows = []
                for r in trs[1:]:
                    if len(r) < 2:
                        continue
                    lab, val = r[0], r[1]
                    um = re.search(r"\(\s*(mg|µg|ug|mcg|g|IU|ie|kcal|kj)\s*\)\s*$", lab, re.I)
                    if um and re.fullmatch(r"[<>]?\s*[\d.,]+", val):
                        lab = lab[:um.start()].strip()
                        val = f"{val} {um.group(1)}"
                    rows.append((lab, val))
                if rows:
                    tables.append((header, rows))
    gt = re.search(r'"gtin13":\s*"(\d+)"', t) or re.search(r'"barcode":"(\d+)"', t)
    if not tables:
        return None
    m = META.get(url, {})
    rec = {"name": m.get("title"), "brand": m.get("vendor"), "ean": common.norm_ean(gt.group(1)) if gt else None, "sku": m.get("sku"),
           "product_type": m.get("product_type"), "tags": m.get("tags"), "price_dkk": m.get("price_dkk"), "ingredients": ing,
           "pack_size_raw": common.pack_size(m.get("title") or "")}
    rec.update(tables_to_record(tables, numfix=da_numbers))
    return rec


if __name__ == "__main__":
    mp = int(sys.argv[1]) if len(sys.argv) > 1 else None
    log = common.Logger("helsam-dk")
    cl = common.Client("helsam-dk", log)
    urls = discover(cl, log)
    if mp:
        urls = urls[:mp]
    run_big("helsam-dk", urls, scrape)
