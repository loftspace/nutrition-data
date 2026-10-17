#!/usr/bin/env python
"""Sportkost.se and Bodypower.se (same Norce/Apollo web-shop platform; sister shops). Rules: ../README.md.
No sitemap: category listings are paged (?page=N). Each listing page embeds window.__APOLLO_STATE__ (the shop's own page data)
which already contains, per product, name, article number, brand (subName), price and the 'Innehall' HTML custom field with the
nutrition table(s) -> no per-product page fetch is needed.
Article numbers that are valid GTINs (8/12/13/14 digits with correct check digit) are stored as ean (flag ean_from_article_number).
Usage: python shape_shops.py sportkost|bodypower [--limit-pages N]
"""
import json
import re
import sys

from se_common import *

CFG = {
    "sportkost": {"base": "https://www.sportkost.se", "cats": ["kosttillskott", "halsokost", "drycker"]},
    "bodypower": {"base": "https://www.bodypower.se", "cats": ["kosttillskott-1", "drycker-1"]},
}


def apollo(h):
    m = re.search(r'window\.__APOLLO_STATE__=JSON\.parse\("', h)
    if not m:
        return None
    i = m.end()
    j = i
    while True:
        k = h.find('")', j)
        if k < 0:
            return None
        b, t = 0, k - 1
        while h[t] == "\\":
            b += 1
            t -= 1
        if b % 2 == 0:
            break
        j = k + 1
    return json.loads(json.loads('"' + h[i:k] + '"'))


def gtin_ok(s):
    d = re.sub(r"\D", "", str(s or ""))
    if len(d) not in (8, 12, 13, 14):
        return None
    digits = [int(c) for c in d]
    check = digits[-1]
    body = digits[:-1][::-1]
    total = sum(x * (3 if i % 2 == 0 else 1) for i, x in enumerate(body))
    return d if (10 - total % 10) % 10 == check else None


def listing_products(st):
    best, total = [], None
    for obj in st.values():
        if not isinstance(obj, dict):
            continue
        for k, v in obj.items():
            if k.startswith("products(") and isinstance(v, dict) and isinstance(v.get("result"), list):
                refs = [r.get("__ref") for r in v["result"] if isinstance(r, dict) and str(r.get("__ref", "")).startswith("Product:")]
                if len(refs) > len(best):
                    best, total = refs, v.get("totalResults")
    return best, total


def build_record(src, base, p, st):
    name = norm_ws(p.get("name"))
    route = None
    pr = p.get("primaryRoute") or {}
    if isinstance(pr, dict) and pr.get("__ref"):
        route = pr["__ref"].split(":", 1)[1]
        r = st.get(pr["__ref"]) or {}
        route = r.get("route") or route
    url = f"{base}/{route}" if route else None
    if not url or looks_nonfood(name):
        return None
    price = None
    pp = p.get("price")
    if isinstance(pp, dict) and pp.get("incVat") is not None:
        price = float(pp["incVat"])
    elif isinstance(pp, dict) and pp.get("__ref") and st.get(pp["__ref"]):
        price = float(st[pp["__ref"]].get("incVat"))
    cf = {}
    for c in p.get("customFields") or []:
        if isinstance(c, dict) and c.get("__ref"):
            c = st.get(c["__ref"], {})
        if isinstance(c, dict) and c.get("key"):
            cf[c["key"]] = c.get("value")
    html_inh = cf.get("Innehall") or ""
    s = soup(html_inh) if html_inh else None
    tables = []
    if s is not None:
        for tb in s.find_all("table"):
            rows = table_to_rows(tb)
            tables.extend(parse_table_el(tb, rows=rows))
    flags = []
    nut, f2 = pick_primary(tables)
    flags += f2
    text = norm_ws(s.get_text(" ")) if s is not None else ""
    if html_inh and not tables and s.find("img"):
        flags.append("nutrition_image_only")
    ing = None
    m = re.search(r"Ingredienser?\s*:?\s*(.{15,2000}?)(?=Allergi|N.ringsv.rde|N.ringsinneh|Bruksanvisning|Anv.ndning|F.rvaring|$)", text)
    if m:
        ing = m.group(1).strip()
    ma = re.search(r"Allergi\w*\s*(?:information)?\s*:?\s*(.{5,300}?\.)", text)
    art = str(p.get("articleNumber") or "")
    ean = gtin_ok(art)
    if ean:
        flags.append("ean_from_article_number")
    cats = [c for c in route.split("/")[:-1]] if route else []
    rec = base_record(src, url, name=name, brand=norm_ws(p.get("subName")) or None, sku=art, ean=ean, price_sek=price, categories=cats,
                      pack_size_text=pack_from_name(name), description=None, ingredients=ing,
                      allergens_text=ma.group(1).strip() if ma else None, nutrition=nut, nutrition_flags=flags)
    rec["extra_tables"] = [t for t in tables if t is not nut][:12]
    rec["custom_field_keys"] = sorted(cf)
    if len(tables) > 1:
        rec["flavour_nutrition_shared_assumed"] = True
    return rec


def main():
    src = sys.argv[1]
    cfg = CFG[src]
    log = Logger(src)
    f = Fetcher(src, cfg["base"], log)
    path = out_path(src)
    done = load_done(path)
    seen_ids = set()
    n_new = 0
    max_pages = int(sys.argv[sys.argv.index("--limit-pages") + 1]) if "--limit-pages" in sys.argv else 400
    log(f"START {src}; already saved {len(done)}")
    try:
        for cat in cfg["cats"]:
            page = 1
            total = None
            while page <= max_pages:
                h = f.get(f"{cfg['base']}/{cat}?page={page}")
                if not h:
                    break
                st = apollo(h)
                if not st:
                    log(f"no apollo state at {cat} page {page}")
                    break
                refs, tot = listing_products(st)
                if tot is not None:
                    total = tot
                if not refs:
                    break
                new_here = 0
                for ref in refs:
                    if ref in seen_ids:
                        continue
                    seen_ids.add(ref)
                    new_here += 1
                    rec = build_record(src, cfg["base"], st[ref], st)
                    if rec is None:
                        continue
                    if rec["page_url"] in done:
                        continue
                    rec["fetched_on"] = today()
                    rec["listing_category"] = cat
                    append(path, rec)
                    done.add(rec["page_url"])
                    n_new += 1
                log(f"{cat} page {page}: refs={len(refs)} new_ids={new_here} total_results={total} saved_new={n_new} requests={f.requests_made}")
                if new_here == 0:
                    break
                page += 1
    except Blocked as e:
        log(f"BLOCKED: {e}")
    log(f"END {src} new={n_new} requests={f.requests_made}")


if __name__ == "__main__":
    main()
