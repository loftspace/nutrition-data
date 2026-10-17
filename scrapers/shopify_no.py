#!/usr/bin/env python3
"""Shopify-based Norwegian supplement shops (proteincompany.no). Product urls from sitemap.xml -> sitemap_products_*.xml.
Each page has a schema.org Product with one Offer per variant (gtin13 = EAN, sku, price, flavour in name) plus the nutrition
table in the description. One 'variant' record per offer (nutrition shared across flavours: flavour_nutrition_shared_assumed).
Output: data/raw/<shop>/products.jsonl. Usage: shopify_no.py <shop-key> [--limit N] [--test]"""
import os, re, sys, json
from bs4 import BeautifulSoup
sys.path.insert(0, os.path.dirname(__file__))
import nogen as N

SHOPS = {"proteincompany-no": "https://proteincompany.no", "goonshop-no": "https://go-on-shop.no"}
clean = N.clean
NONFOOD = re.compile(r"(gloves?|hansker|wrist|wraps?|strap|belt|belte|shaker|smartshake|bag\b|backpack|ryggsekk|bottle|flaske|t-?shirt|hoodie|shorts|tights|leggings|sock|kne|knee|elbow|sleeve|\bmat\b|matte|rope|\bband\b|bands\b|gavekort|gift-?card|gorilla-wear|better-bodies|gasp-|venum|bukse|jakke|jacket|singlet|\bbra\b|\bcap\b|\blue\b|towel|h[aå]ndkle|foam-?roller|dumbbell|kettlebell|hoppetau|massage|lifting|vektvest|pillekasse|pill-?box)", re.I)


def parse(shop, url, html):
    s = BeautifulSoup(html, "lxml")
    prod = None
    for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            j = json.loads(m.group(1))
        except Exception:
            continue
        for g in (j.get("@graph") or [j]) if isinstance(j, dict) else []:
            if isinstance(g, dict) and g.get("@type") == "Product":
                prod = g
    if not prod:
        return []
    name = clean(prod.get("name"))
    tabs = []
    for t in s.find_all("table"):
        st = N.structure_rows(N.table_rows(t))
        if st and (st["per_100"] or st["per_serving"]):
            tabs.append(st)
    nut = N.merge_nutrition(tabs)
    text = clean(s.get_text(" ", strip=True))
    if nut is None:
        nut = N.parse_inline_nutrition(text)
        if nut:
            nut["from_inline_text"] = True
    ing = re.search(r"Ingredienser:?\s*(.*?)(?=\s+(?:N[æe]ringsinnhold|N[æe]ringsdeklarasjon|Oppbevar|Bruksanvisning|Allergen|Anbefalt|Kan inneholde)|$)", text)
    flags = ["flavour_nutrition_shared_assumed"]
    if nut is None:
        flags.append("no_nutrition_table")
        if re.search(r"n[æe]ringsinnhold|n[æe]ringsdeklarasjon", text, re.I):
            flags.append("nutrition_mentioned_but_no_table_maybe_image")
    elif not nut["per_100"]:
        flags.append("per_100_missing_per_serving_only")
    offers = prod.get("offers") or []
    if isinstance(offers, dict):
        offers = [offers]
    brand = prod.get("brand")
    brand = brand.get("name") if isinstance(brand, dict) else brand
    pack = re.search(r"(\d+)\s*[xX]\s*(\d+(?:[.,]\d+)?)\s*(g|ml|gr)\b|(\d+(?:[.,]\d+)?)\s*(kg|g|gr|ml|l|kapsler|tabletter|stk)\b", name or "", re.I)
    out = []
    for o in offers or [{}]:
        oname = clean(o.get("name") or name)
        flav = oname[len(name):].lstrip(" -") if name and oname.startswith(name) and len(oname) > len(name) else None
        out.append({
            "record_type": "variant", "source": shop, "source_url": url, "page_url": url, "fetched_on": N.TODAY, "name": oname, "product_name": name, "brand": brand,
            "sku": o.get("sku") or prod.get("sku"), "ean": o.get("gtin13") or o.get("gtin") or (prod.get("gtin13") if len(offers) <= 1 else None),
            "flavour": flav or None, "price_nok": float(o["price"]) if o.get("price") not in (None, "") else None,
            "availability": (o.get("availability") or "").rsplit("/", 1)[-1] or None, "variant_url": o.get("url"),
            "pack": {"size_text": pack.group(0)} if pack else None, "description": clean(prod.get("description")),
            "ingredients": ing.group(1)[:1500] if ing else None, "nutrition": nut, "nutrition_flags": flags,
            "page_status": "live", "archive_timestamp": None, "discontinued": False,
        })
    return out


def main():
    shop = sys.argv[1]
    host = SHOPS[shop]
    out_path = f"{N.ROOT}/data/raw/{shop}/products.jsonl"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    test = "--test" in sys.argv
    out = out_path.replace("products.jsonl", "test.jsonl") if test else out_path
    cl = N.Client(shop, host)
    r = cl.get(host + "/sitemap.xml")
    subs = re.findall(r"<loc>([^<]+)</loc>", r.text) if r else []
    urls = []
    for sm in subs:
        if "product" in sm:
            rr = cl.get(sm)
            if rr:
                urls += [u for u in re.findall(r"<loc>([^<]+)</loc>", rr.text) if "/products/" in u]
    urls = [u for u in dict.fromkeys(urls) if not NONFOOD.search(u.rsplit("/", 1)[-1])]
    cl.log(f"{len(urls)} product urls")
    done = set() if test else N.load_done(out, "page_url")
    todo = [u for u in urls if u not in done]
    if test:
        todo = todo[::max(1, len(todo) // (limit or 5))]
    if limit:
        todo = todo[:limit]
    n = 0
    with open(out, "w" if test else "a", encoding="utf8") as f:
        for i, u in enumerate(todo, 1):
            rr = cl.get(u)
            if not rr:
                continue
            try:
                recs = parse(shop, u, rr.content.decode("utf-8", "replace"))
            except Exception as e:
                cl.log(f"PARSE-ERR {u} {type(e).__name__} {e}")
                continue
            for rec in recs:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush(); n += 1 if recs else 0
            if i % 50 == 0:
                cl.log(f"progress {i}/{len(todo)} pages_saved={n} reqs={cl.n}")
    cl.log(f"END pages_saved={n} requests={cl.n}")


if __name__ == "__main__":
    main()
