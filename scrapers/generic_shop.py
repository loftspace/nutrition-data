#!/usr/bin/env python3
"""Generic collector for small Norwegian supplement / food shops whose product pages carry schema.org Product JSON-LD and a
server-rendered nutrition table or nutrition prose. Per shop only the host, product-URL discovery and filters differ (SHOPS).
One record per product page (variants in JSON-LD offers become 'variants'); nutrition is shared across flavours
(flavour_nutrition_shared_assumed). Never converts per-serving to per-100. Output: data/raw/<shop>/products.jsonl.
Usage: generic_shop.py <shop-key> [--limit N] [--test]"""
import os, re, sys, json, gzip
from bs4 import BeautifulSoup
sys.path.insert(0, os.path.dirname(__file__))
import nogen as N

NONFOOD = re.compile(r"(gloves?|hansker|wrist|wraps?|strap|belt|belte|shaker|smartshake|blender-?bottle|bag\b|backpack|ryggsekk|bottle|flaske|t-?shirt|hoodie|shorts|tights|leggings|sock|knee|elbow|sleeve|\bmat\b|matte|rope|\bband\b|bands\b|gavekort|gift-?card|gorilla-wear|better-bodies|gasp-|venum|bukse|jakke|jacket|singlet|\bbra\b|\bcap\b|\blue\b|towel|h[aå]ndkle|foam-?roller|dumbbell|kettlebell|hoppetau|massage|lifting|vektvest|pillekasse|pill-?box|sjampo|shampoo|deodorant|ansiktskrem|sminke|neglelakk|parfyme|tannkrem|sapen|sukkertoy)", re.I)

SHOPS = {
    # key: (host, sitemap urls (index or direct), include regex on product url, exclude regex)
    "sportylab-no": ("https://www.sportylab.no", ["/sitemap.xml"], r"/produkt/", None),
    "helsekost-no": ("https://helsekost.no", ["/sitemap.xml"], r"/products/", None),
    "apex-no": ("https://apex.no", ["/sitemap_index.xml"], r"/produkt/", None),
    "nordicpower-no": ("https://nordicpower.no", ["/sitemap.xml"], r"/produkt/", None),
    "cooperscandy-no": ("https://www.cooperscandy.no", ["/sitemap.xml"], r"cooperscandy\.no/(?!bars/|kategori)[a-z0-9æøå\-]+-\d+[a-z]*$|/product\.php/", None),
    "sweats-no": ("https://sweats.no", ["/sitemap.xml"], r"/products/", None),
    "goonshop-no": ("https://go-on-shop.no", ["/sitemap.xml"], r"/products/", None),
    "hcdealer-no": ("https://www.hcdealer.no", ["/sitemap.xml"], r"/products/", None),
    "coore-no": ("https://coore.no", ["/sitemap.xml"], r"/products/", None),
    "diggbox-no": ("https://www.diggbox.no", ["/sitemap.xml"], r"/butikk/[^/]+/[^/]+/[^/]+/[^/]+/?$", None),
    "kinsarvik-no": ("https://www.kinsarvik.no", ["/sitemap.xml"], r"/products/", None),
}
clean = N.clean


def sitemap_urls(cl, paths, depth=0):
    out = []
    for p in paths:
        u = p if p.startswith("http") else cl.host + p
        r = cl.get(u)
        if not r:
            continue
        c = r.content
        if c[:2] == b"\x1f\x8b":
            c = gzip.decompress(c)
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", c.decode("utf-8", "replace"))
        subs = [x for x in locs if re.search(r"\.xml(\.gz)?(\?|$)", x)]
        if subs and depth < 2:
            keep = [x for x in subs if re.search(r"product|produkt|sitemap_products|post-sitemap|^((?!page|blog|collection|article|category|tag|author).)*$", x, re.I) and not re.search(r"blog|article|page-sitemap|collection|categor|tag|author|post-sitemap|brand|manufactur", x, re.I)]
            out += sitemap_urls(cl, keep, depth + 1)
        out += [x for x in locs if x not in subs]
    return out


def jsonld_products(s):
    prods = []
    for sc in s.find_all("script", type="application/ld+json"):
        try:
            j = json.loads(sc.string or sc.get_text() or "")
        except Exception:
            continue
        stack = [j]
        while stack:
            g = stack.pop()
            if isinstance(g, list):
                stack += g
            elif isinstance(g, dict):
                t = g.get("@type")
                if t == "Product" or (isinstance(t, list) and "Product" in t):
                    prods.append(g)
                for k in ("@graph", "mainEntity", "itemListElement"):
                    if k in g:
                        stack.append(g[k])
    return prods


def parse(shop, url, html):
    s = BeautifulSoup(html, "lxml")
    prods = jsonld_products(s)
    prods = [p for p in prods if p.get("name")]
    prod = prods[0] if prods else None
    h1 = s.find("h1")
    name = clean(h1.get_text(" ", strip=True)) if h1 else clean((prod or {}).get("name"))
    if not name:
        return None
    offers = (prod or {}).get("offers") or []
    if isinstance(offers, dict):
        offers = [offers]
    variants = []
    for o in offers:
        if not isinstance(o, dict):
            continue
        if o.get("@type") == "AggregateOffer" and o.get("offers"):
            o2 = o["offers"] if isinstance(o["offers"], list) else [o["offers"]]
            offers += [x for x in o2 if isinstance(x, dict)]
            continue
        variants.append({"name": clean(o.get("name")) or None, "sku": o.get("sku"), "ean": o.get("gtin13") or o.get("gtin") or o.get("gtin14") or o.get("gtin8") or o.get("ean"),
                         "price": o.get("price") or o.get("lowPrice"), "availability": (o.get("availability") or "").rsplit("/", 1)[-1] or None, "url": o.get("url")})
    ean = (prod or {}).get("gtin13") or (prod or {}).get("gtin") or (prod or {}).get("gtin14") or (prod or {}).get("gtin8") or (prod or {}).get("ean")
    if not ean and variants and len({v["ean"] for v in variants if v["ean"]}) == 1:
        ean = variants[0]["ean"]
    if not ean:
        m = re.search(r"-(\d{13})/?$", url)
        ean = m.group(1) if m else None
        if not ean:
            m = re.search(r'(?:itemprop="gtin1?[34]?"|class="[^"]*\bean\b[^"]*")[^>]*?(?:content="|>)\s*(\d{8,14})', html, re.I) or re.search(r"(?:EAN|GTIN|Strekkode)[^0-9<]{0,30}(\d{13})", html, re.I)
            ean = m.group(1) if m else None
    tabs = []
    for t in s.find_all("table"):
        rows_t = N.table_rows(t)
        flat = " ".join(" ".join(r) for r in rows_t)
        if re.search(r"\bpris\b|\bkr\b|price|butikk|frakt|antall\s+pris|rabatt|\bqty\b", flat, re.I) and not re.search(r"energi|kcal|protein|karbohydrat|vitamin|mg\b|µg", flat, re.I):
            continue
        st = N.structure_rows(rows_t)
        if st and (st["per_100"] or st["per_serving"]) and any(k in st["per_100"] or k in st["per_serving"] for k in ("energy_kcal", "protein", "fat", "carbs", "salt") ) or (st and len(st["raw_rows"]) >= 2 and (st["per_100"] or st["per_serving"])):
            tabs.append(st)
    nut = N.merge_nutrition(tabs)
    text = clean(s.get_text(" ", strip=True))
    if nut is None:
        nut = N.parse_inline_nutrition(text)
        if nut:
            nut["from_inline_text"] = True
    ing = re.search(r"Ingredienser:?\s*(.*?)(?=\s+(?:N[æe]ringsinnhold|N[æe]ringsdeklarasjon|Oppbevar|Bruksanvisning|Allergen|Anbefalt|Kan inneholde|Produsent|Pakningsst)|$)", text, re.I)
    flags = ["flavour_nutrition_shared_assumed"]
    if nut is None:
        flags.append("no_nutrition_table")
        if re.search(r"n[æe]ringsinnhold|n[æe]ringsdeklarasjon", text, re.I) or s.find("img", src=re.compile(r"n[æe]ring|nutri", re.I)):
            flags.append("nutrition_mentioned_but_no_table_maybe_image")
    elif not nut["per_100"]:
        flags.append("per_100_missing_per_serving_only")
    brand = (prod or {}).get("brand")
    brand = brand.get("name") if isinstance(brand, dict) else brand
    price = None
    if variants and variants[0]["price"] not in (None, ""):
        try:
            price = float(str(variants[0]["price"]).replace(",", "."))
        except ValueError:
            pass
    crumbs = []
    for sc in s.find_all("script", type="application/ld+json"):
        try:
            j = json.loads(sc.string or "")
        except Exception:
            continue
        for g in (j.get("@graph") or [j]) if isinstance(j, dict) else []:
            if isinstance(g, dict) and g.get("@type") == "BreadcrumbList":
                crumbs = [clean((i.get("item") or {}).get("name") if isinstance(i.get("item"), dict) else i.get("name")) for i in g.get("itemListElement", [])]
    pack = re.search(r"(\d+)\s*[xX]\s*(\d+(?:[.,]\d+)?)\s*(g|ml|gr)\b|(\d+(?:[.,]\d+)?)\s*(kg|g|gr|gram|ml|l|kapsler|kaps|tabletter|tabs|stk)\b", name or "", re.I)
    return {
        "source": shop, "source_url": url, "fetched_on": N.TODAY, "name": name, "brand": clean(brand) or None, "sku": (prod or {}).get("sku"), "ean": ean,
        "price_nok": price, "availability": variants[0]["availability"] if variants else None, "breadcrumbs": [c for c in crumbs if c],
        "pack": {"size_text": pack.group(0)} if pack else None, "variants": variants if len(variants) > 1 else None,
        "description": clean((prod or {}).get("description"))[:1500] or None, "ingredients": ing.group(1)[:1500] if ing else None,
        "nutrition": nut, "nutrition_flags": flags, "page_status": "live", "archive_timestamp": None, "discontinued": False,
    }


def main():
    shop = sys.argv[1]
    host, sm, inc, exc = SHOPS[shop]
    out_path = f"{N.ROOT}/data/raw/{shop}/products.jsonl"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    test = "--test" in sys.argv
    out = out_path.replace("products.jsonl", "test.jsonl") if test else out_path
    cl = N.Client(shop, host, delay=float(os.environ.get("SHOP_DELAY", "1.1")))
    urls = sitemap_urls(cl, sm)
    urls = [u for u in dict.fromkeys(urls) if re.search(inc, u) and not (exc and re.search(exc, u)) and not NONFOOD.search(u.rstrip("/").rsplit("/", 1)[-1])]
    cl.log(f"{len(urls)} product urls after filters")
    done = set() if test else N.load_done(out)
    todo = [u for u in urls if u not in done]
    if test:
        todo = todo[:: max(1, len(todo) // (limit or 5))]
    if limit:
        todo = todo[:limit]
    n = 0
    with open(out, "w" if test else "a", encoding="utf8") as f:
        for i, u in enumerate(todo, 1):
            rr = cl.get(u)
            if not rr:
                continue
            try:
                rec = parse(shop, u, rr.content.decode("utf-8", "replace"))
            except Exception as e:
                cl.log(f"PARSE-ERR {u} {type(e).__name__} {e}")
                continue
            if rec:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush(); n += 1
            if i % 50 == 0:
                cl.log(f"progress {i}/{len(todo)} saved={n} reqs={cl.n}")
    cl.log(f"END saved={n} requests={cl.n}")


if __name__ == "__main__":
    main()
