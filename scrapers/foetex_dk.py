#!/usr/bin/env python
"""Foetex.dk (Salling Group web shop, server-rendered Nuxt). Sitemap -> /produkter/ pages. Saves food items
(nutrition table present, or food category); skips non-food. Food-like slugs are fetched first.
Usage: python foetex_dk.py [max_pages] [max_hours]"""
import re, sys, os, html
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nordic import *
import common

BASE = "https://www.foetex.dk"
PRIORITY = re.compile(r"protein|skyr|yoghurt|yogurt|kvark|maelk|mælk|ost-|-ost|smoer|bar-|-bar\b|proteinbar|snack|chips|chokolade|choko|musli|müsli|havre|granola|kiks|broed|brød|pasta|ris-|kylling|oksekoed|hakket|flaeske|laks|tun-|aeg|skinke|pate|juice|sodavand|energi|drik|saft|kaffe|te-|nodder|nødder|mandel|peanut|jordnod|slik|is-|dessert|pizza|supper|sovs|olie|sukker|mel-|ketchup|salat|gront|frugt|agurk|tomat|kartoffel", re.I)


def discover(cl, log):
    idx = cl.get(BASE + "/sitemap/sitemap-index.xml")
    urls = []
    for sm in sitemap_locs(idx or ""):
        t = cl.get(sm)
        if t:
            urls += [u for u in sitemap_locs(t) if "/produkter/" in u]
    urls = list(dict.fromkeys(urls))
    pri = [u for u in urls if PRIORITY.search(u)]
    rest = [u for u in urls if not PRIORITY.search(u)]
    log(f"sitemap /produkter/ urls {len(urls)} (food-keyword first: {len(pri)})")
    return pri + rest


FOOD_PATH = ("/mad", "/drikke", "/fritid-skoenhed/sportsernaering", "/skoenhed/helse", "/koel", "/frost", "/broed", "/kolonial")


def scrape(cl, url):
    t = cl.get(url)
    if not t:
        return None
    prods = jsonld(t, "Product")
    p = prods[0] if prods else {}
    pcp = re.search(r'primary_category_path:"([^"]*)"', t)
    cat_path = pcp.group(1) if pcp else None
    crumbs = re.findall(r'\{path:[^,}]*,name:"([^"]+)"', t)
    # specification table
    tables, cur_head, cur_rows, other, ingredients = [], None, [], {}, None
    sm = re.search(r'<div class="specification-table".*?<tbody[^>]*>(.*?)</tbody>', t, re.S)
    if sm:
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", sm.group(1), re.S):
            tds = re.findall(r"<td([^>]*)>(.*?)</td>", tr, re.S)
            if not tds:
                continue
            if "colspan" in tds[0][0]:
                if cur_head is not None:
                    tables.append((cur_head, cur_rows))
                cur_head, cur_rows = one(tds[0][1]), []
                continue
            if len(tds) < 2:
                continue
            label = one(tds[0][1])
            val = " ".join(one(x) for x in re.findall(r"<span[^>]*>(.*?)</span>", tds[1][1], re.S) if one(x)) or one(tds[1][1])
            if re.match(r"ingredienser", label, re.I):
                ingredients = val
                if cur_head is not None:
                    tables.append((cur_head, cur_rows))
                    cur_head, cur_rows = None, []
            elif cur_head is not None:
                cur_rows.append((label, val))
            else:
                other[label] = val
        if cur_head is not None:
            tables.append((cur_head, cur_rows))
    rec_n = tables_to_record(tables)
    is_food = bool(tables) or bool(cat_path and cat_path.startswith(FOOD_PATH))
    if not is_food:
        return None
    off = p.get("offers") or {}
    if isinstance(off, list):
        off = off[0] if off else {}
    ean = common.norm_ean(p.get("gtin13"))
    rec = {"name": html.unescape(p.get("name") or ""), "brand": p.get("brand") if isinstance(p.get("brand"), str) else (p.get("brand") or {}).get("name"),
           "ean": ean, "sku": p.get("sku"), "varenummer": other.get("Varenummer"), "pack_size_raw": p.get("description"),
           "price_dkk": off.get("price"), "category_path": cat_path, "categories": crumbs[1:], "ingredients": ingredients,
           "other_spec": other, "chain": "foetex (Salling Group; same catalogue as Bilka/Netto)"}
    rec.update(rec_n)
    return rec


if __name__ == "__main__":
    mp = int(sys.argv[1]) if len(sys.argv) > 1 else None
    hrs = float(sys.argv[2]) if len(sys.argv) > 2 else None
    log = common.Logger("foetex-dk")
    cl = common.Client("foetex-dk", log)
    urls = discover(cl, log)
    if mp:
        urls = urls[:mp]
    run_big("foetex-dk", urls, scrape, max_seconds=hrs * 3600 if hrs else None)
