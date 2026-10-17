#!/usr/bin/env python
"""Bodylab.dk (Shopware 6). Sitemap -> product pages (ld+json Product) -> nutrition table
+ flavour list via the site's own /ingredient/variants endpoint. Usage: python bodylab_dk.py [limit]"""
import re, sys, os, html
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nordic import *
import common

BASE = "https://www.bodylab.dk"
SKIP_TOP = {"muskelopbygning", "mad-snacks", "vaegttab", "energi", "tilskud", "toej-udstyr", "serier", "tilbud", "pakker",
            "opskrifter", "kundeservice", "guider", "guides", "artikler", "spoerg-eksperterne", "kom-i-gang",
            "konkurrencebetingelser", "stay-updated"}


def discover(cl, log):
    idx = cl.get(BASE + "/sitemap.xml")
    urls = []
    for sm in sitemap_locs(idx or ""):
        t = cl.get(sm)
        if t:
            urls += sitemap_locs(t)
    out = []
    for u in dict.fromkeys(urls):
        parts = u[len(BASE):].strip("/").split("/")
        if len(parts) == 1 and parts[0] and parts[0] not in SKIP_TOP:
            out.append(u)
    log(f"sitemap product-like urls {len(out)}")
    return out


def scrape(cl, url):
    t = cl.get(url)
    if not t:
        return None
    prods = jsonld(t, "Product")
    if not prods:
        return None
    p = prods[0]
    name = html.unescape(p.get("name") or "")
    off = p.get("offers") or {}
    if isinstance(off, list):
        off = off[0] if off else {}
    crumbs = []
    for b in jsonld(t, "BreadcrumbList"):
        crumbs = [html.unescape(i["name"]) for i in b.get("itemListElement", [])][1:-1]
    tables = []
    for tm in re.finditer(r'<table class="ingredient-nutrition-table__table">(.*?)</table>', t, re.S):
        tb = tm.group(1)
        head = [one(x) for x in re.findall(r'ingredient-nutrition-table__header-label">(.*?)</div>', tb, re.S)]
        header = " ".join(h for h in head if h)
        rows = []
        for tr in re.findall(r'<tr class="ingredient-nutrition-table__row">(.*?)</tr>', tb, re.S):
            cells = [one(c) for c in re.findall(r'ingredient-nutrition-table__value">(.*?)</div>', tr, re.S)]
            if len(cells) >= 2:
                rows.append((cells[0], cells[1]))
        tables.append((header, rows))
    ing = None
    m = re.search(r"Ingredienser\s*</[^>]+>(.*?)(?:Varebetegnelse|Brugsanvisning|</div>\s*</div>)", t, re.S)
    if m:
        ing = one(m.group(1)) or None
    b = p.get("brand")
    rec = {"name": name, "brand": b.get("name") if isinstance(b, dict) else b,
           "sku": p.get("sku"), "ean": None, "ean_note": "bodylab.dk does not publish EAN on product pages",
           "price_dkk": off.get("price"), "currency": off.get("priceCurrency"), "categories": crumbs,
           "description": html.unescape(p.get("description") or "")[:600], "ingredients": ing,
           "pack_size_raw": common.pack_size(name), "flavours": [],
           "flavour_note": "nutrition table is the page default; flavours assumed to share nutrition"}
    pid = re.search(r"/ingredient/variants/([0-9a-f]{32})\?", t)
    if pid:
        v = get_soft(cl, f"{BASE}/ingredient/variants/{pid.group(1)}?currentProductId={pid.group(1)}")
        if v:
            rec["flavours"] = [one(x) for x in re.findall(r"<option[^>]*>(.*?)</option>", v, re.S) if one(x)]
    rec.update(tables_to_record(tables))
    return rec


if __name__ == "__main__":
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else None
    common.run_main("bodylab-dk", discover, scrape, limit=lim)
