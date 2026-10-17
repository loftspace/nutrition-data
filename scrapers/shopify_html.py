#!/usr/bin/env python
"""Small Swedish Shopify shops whose nutrition tables sit in the product description (body_html of the public /products.json).
Currently: halsafitnessbutiken (Halsa & Fitness, Gothenburg). Rules: ../README.md.
One request per 250 products (the shop's own JSON feed, allowed by robots.txt); no per-page fetch, no EAN published.
Usage: python shopify_html.py halsafitnessbutiken
"""
import re
import sys

from se_common import *

CFG = {
    "halsafitnessbutiken": {"base": "https://www.halsafitnessbutiken.se", "skip_types": {"Kläder", "Tillbehör", "Shaker"}},
}


def main():
    src = sys.argv[1]
    cfg = CFG[src]
    log = Logger(src)
    f = Fetcher(src, cfg["base"], log)
    path = out_path(src)
    done = load_done(path)
    n = 0
    log(f"START {src}; already saved {len(done)}")
    try:
        for page in range(1, 40):
            d = f.get(f"{cfg['base']}/products.json?limit=250&page={page}", json_mode=True)
            items = (d or {}).get("products") or []
            if not items:
                break
            for p in items:
                url = f"{cfg['base']}/products/{p['handle']}"
                if url in done:
                    continue
                name = norm_ws(p.get("title"))
                if looks_nonfood(name) or p.get("product_type") in cfg["skip_types"]:
                    continue
                s = soup(p.get("body_html") or "")
                tables = []
                for tb in s.find_all("table"):
                    if re.search(r"(?i)energi|kcal|protein|inneh.ll per|n.ringsv.rde|per portion|per dos|per 100", tb.get_text(" ")):
                        tables.extend(parse_table_el(tb))
                nut, flags = pick_primary(tables)
                text = norm_ws(s.get_text(" "))
                ing = None
                m = re.search(r"Ingredienser?\s*:?\s*(.{15,2000}?)(?=Allergi|N.ringsv.rde|N.ringsinneh|Bruksanvisning|Anv.ndning|F.rvaring|Viktig information|$)", text)
                if m:
                    ing = m.group(1).strip()
                ma = re.search(r"Allergi\w*\s*(?:information)?\s*:?\s*(.{5,300}?\.)", text)
                variants = [{"title": v.get("title"), "sku": v.get("sku"), "price": v.get("price"), "available": v.get("available")} for v in p.get("variants", [])]
                prices = [float(v["price"]) for v in p.get("variants", []) if v.get("price")]
                rec = base_record(src, url, name=name, brand=p.get("vendor"), sku=(p["variants"][0].get("sku") if p.get("variants") else None), ean=None,
                                  price_sek=min(prices) if prices else None, categories=[p.get("product_type")] if p.get("product_type") else [],
                                  pack_size_text=pack_from_name(name), description=text[:1500] or None, ingredients=ing,
                                  allergens_text=ma.group(1).strip() if ma else None, nutrition=nut, nutrition_flags=flags)
                rec["extra_tables"] = [t for t in tables if t is not nut][:12]
                rec["variants"] = variants
                rec["tags"] = p.get("tags")
                if len(tables) > 1 or len(variants) > 1:
                    rec["flavour_nutrition_shared_assumed"] = True
                rec["fetched_on"] = today()
                append(path, rec)
                done.add(url)
                n += 1
            log(f"page {page}: {len(items)} items, saved_new={n}")
    except Blocked as e:
        log(f"BLOCKED: {e}")
    log(f"END {src} new={n} requests={f.requests_made}")


if __name__ == "__main__":
    main()
