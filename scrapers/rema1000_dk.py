#!/usr/bin/env python
"""shop.rema1000.dk product pages (Nuxt SSR payload __NUXT_DATA__ holds nutrition_info + declaration).
robots.txt allows all. The page gives no EAN. Values are unit-less per 100 g (energy as 'kJ / kcal').
Usage: python rema1000_dk.py [max_pages] [max_hours]"""
import re, sys, os, json, html
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nordic import *
import common

BASE = "https://shop.rema1000.dk"
PRIORITY = re.compile(r"protein|skyr|yoghurt|kvark|maelk|mælk|ost|bar|snack|chips|chokolade|musli|havre|granola|kiks|broed|kylling|pålæg|paalaeg", re.I)


def discover(cl, log):
    idx = cl.get(BASE + "/sitemap_index.xml")
    urls = []
    for sm in sitemap_locs(idx or ""):
        if "/products-" in sm:
            t = cl.get(sm)
            if t:
                urls += sitemap_locs(t)
    urls = list(dict.fromkeys(urls))
    pri = [u for u in urls if PRIORITY.search(u)]
    rest = [u for u in urls if u not in set(pri)]
    log(f"sitemap product urls {len(urls)} (priority {len(pri)})")
    return pri + rest


def _res(arr, i):
    v = arr[i]
    if isinstance(v, list):
        if v and v[0] in ("ShallowReactive", "Reactive", "Ref", "EmptyRef", "EmptyShallowRef", "ShallowRef"):
            return _res(arr, v[1])
        return [_res(arr, x) if isinstance(x, int) else x for x in v]
    if isinstance(v, dict):
        return {k: (_res(arr, x) if isinstance(x, int) else x) for k, x in v.items()}
    return v


def scrape(cl, url):
    t = cl.get(url)
    if not t:
        return None
    m = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', t, re.S)
    if not m:
        return None
    arr = json.loads(m.group(1))
    try:
        d = _res(arr, 0)["state"]["$svue-query"]["queries"][0]["state"]["data"]["data"]
    except Exception:
        return None
    ni = d.get("nutrition_info") or []
    if not ni:
        return None
    rows = []
    for r in ni:
        label, val = r.get("name"), (r.get("value") or "").strip()
        if val and re.fullmatch(r"[\d.,<> ]+", val):
            val += " g"          # source gives bare numbers; grams per 100 g
        rows.append((label, val))
    rec_n = tables_to_record([("Næringsindhold pr. 100 g (basis assumed: source prints no unit/basis)", rows)])
    und = d.get("underline") or ""
    pack, _, brand = und.partition("/")
    cat = d.get("category") or {}
    dep = d.get("department") or {}
    pr = (d.get("prices") or [{}])[0]
    rec = {"name": d.get("name"), "brand": brand.strip() or None, "ean": None, "ean_note": "shop.rema1000.dk does not publish EAN",
           "rema_id": d.get("id"), "pack_size_raw": pack.strip() or None, "department": dep.get("name"), "category": cat.get("name"),
           "price_dkk": pr.get("price"), "compare_unit": pr.get("compare_unit"), "compare_unit_price": pr.get("compare_unit_price"),
           "ingredients": one(d.get("declaration") or "") or None, "labels": [l.get("name") for l in d.get("labels") or []],
           "origin_country": d.get("origin_country")}
    rec.update(rec_n)
    rec["nutrition_flag"] = rec["nutrition_flag"] or "basis_not_printed_assumed_per_100g_or_100ml"
    return rec


if __name__ == "__main__":
    mp = int(sys.argv[1]) if len(sys.argv) > 1 else None
    hrs = float(sys.argv[2]) if len(sys.argv) > 2 else None
    log = common.Logger("rema1000-dk")
    cl = common.Client("rema1000-dk", log)
    urls = discover(cl, log)
    if mp:
        urls = urls[:mp]
    run_big("rema1000-dk", urls, scrape, max_seconds=hrs * 3600 if hrs else None)
