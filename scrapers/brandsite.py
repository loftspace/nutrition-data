#!/usr/bin/env python3
"""Generic brand-site scraper (second pass uk-us-eu-brands, 2026-10-16). Rules: see ../README.md.

Catalogue: Shopify /products.json (only when robots.txt allows it) or a sitemap; then one HTML page per product for the
nutrition panel (HTML tables, JSON-LD additionalProperty or a text panel). Image-only panels are NOT read: nutrition=None
plus flag nutrition_image_only. One nutrition panel per product page; flavours share it (flag nutrition_page_level_not_flavour_verified).
Output: data/raw/<source>/products.jsonl, one record_type=page line per product page and one record_type=variant line per
variant (sku/ean/flavour/price). Resume-safe by page URL.

Usage: python brandsite.py <key> [--limit N] [--out PATH]
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ukus_common as uc  # noqa: E402
from ukus_common import Client, Logger, Blocked, append, today  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

SITES = {
    # key: (source folder, host, brand, country(of the shop), currency, catalogue)
    "quest": dict(host="www.questnutrition.com", brand="Quest Nutrition", country="US", cur="USD", cat="shopify"),
    "fulfil": dict(host="fulfilnutrition.com", brand="Fulfil", country="IE", cur="GBP", cat="shopify"),
    "reflex": dict(host="reflexnutrition.com", brand="Reflex Nutrition", country="GB", cur="GBP", cat="shopify"),
    "esn": dict(host="www.esn.com", brand="ESN", country="DE", cur="EUR", cat="shopify"),
    "grenade": dict(host="www.grenade.com", brand="Grenade", country="GB", cur="GBP", cat="shopify"),
    "cellucor": dict(host="cellucor.com", brand="Cellucor", country="US", cur="USD", cat="shopify"),
    "muscletech": dict(host="www.muscletech.com", brand="MuscleTech", country="US", cur="USD", cat="shopify"),
    "applied-nutrition": dict(host="appliednutrition.uk", brand="Applied Nutrition", country="GB", cur="GBP", cat="shopify"),
    "weider": dict(host="www.weider.com", brand="Weider", country="US", cur="USD", cat="shopify"),
    "ghost": dict(host="www.ghostlifestyle.com", brand="Ghost", country="US", cur="USD", cat="shopify"),
    "transparent-labs": dict(host="www.transparentlabs.com", brand="Transparent Labs", country="US", cur="USD", cat="shopify"),
    "gorilla-mind": dict(host="gorillamind.com", brand="Gorilla Mind", country="US", cur="USD", cat="shopify"),
    "legion": dict(host="legionathletics.com", brand="Legion Athletics", country="US", cur="USD", cat="sitemap-urls",
                   sitemap="/product-sitemap.xml", url_rx=r"/products/supplements/[a-z0-9\-]+/$"),
    "bodybuilding": dict(host="shop.bodybuilding.com", brand=None, country="US", cur="USD", cat="shopify"),
    "optimum-nutrition": dict(host="www.optimumnutrition.com", brand="Optimum Nutrition", country="EU", cur="EUR", cat="collections"),
}


def get_json(cl, url):
    t = cl.get(url)
    if t is None:
        return None
    try:
        return json.loads(t)
    except Exception:
        return None


def catalogue(cl, cfg, log):
    host = cfg["host"]
    prods = []
    if cfg["cat"] == "shopify":
        if not cl.allowed(f"https://{host}/products.json"):
            log("ROBOTS disallows /products.json; cannot use")
            return []
        for pg in range(1, 30):
            d = get_json(cl, f"https://{host}/products.json?limit=250&page={pg}")
            ps = (d or {}).get("products", [])
            prods += ps
            if len(ps) < 250:
                break
    elif cfg["cat"] == "sitemap-urls":
        t = cl.get(f"https://{host}{cfg['sitemap']}") or ""
        for u in re.findall(r"<loc>([^<]+)</loc>", t):
            if re.search(cfg["url_rx"], u):
                prods.append({"title": u.rstrip("/").rsplit("/", 1)[1].replace("-", " ").title(), "handle": u.rstrip("/").rsplit("/", 1)[1],
                              "_url": u, "variants": [{"id": None}], "options": [], "body_html": ""})
    elif cfg["cat"] == "collections":  # robots disallows sitemap.xml/products.json: walk /collections/all pages
        handles = []
        for pg in range(1, 40):
            t = cl.get(f"https://{host}/collections/all?page={pg}")
            if not t:
                break
            hs = list(dict.fromkeys(re.findall(r'href="(?:/[a-z]{2}-[a-z]{2})?/products/([a-z0-9\-_%]+)', t)))
            new = [h for h in hs if h not in handles]
            if not new:
                break
            handles += new
        for h in handles:
            j = get_json(cl, f"https://{host}/products/{h}.js")
            if j:
                j["handle"] = h
                j["body_html"] = j.get("description")
                j["_js"] = True
                prods.append(j)
    else:  # sitemap-shopify: product pages from the sitemap, each also has /products/<handle>.js
        idx = cl.get(f"https://{host}/sitemap.xml") or ""
        subs = [u.replace("&amp;", "&") for u in re.findall(r"<loc>([^<]+)</loc>", idx) if "sitemap_products" in u]
        handles = []
        for s in subs:
            t = cl.get(s) or ""
            handles += [u.rsplit("/products/", 1)[1] for u in re.findall(r"<loc>([^<]+)</loc>", t) if "/products/" in u]
        for h in handles:
            j = get_json(cl, f"https://{host}/products/{h}.js")
            if j:
                j["handle"] = h
                # .js format: variants have 'name','price' in cents, options list of names
                j["body_html"] = j.get("description")
                j["_js"] = True
                prods.append(j)
    log(f"catalogue {host}: {len(prods)} products")
    return prods


def variant_records(p, cfg, page_url, base_flags):
    out = []
    cfg = dict(cfg, brand=cfg["brand"] or p.get("vendor"))
    opts = p.get("options") or []
    optnames = [(o.get("name") if isinstance(o, dict) else o) for o in opts]
    for v in p.get("variants") or []:
        vals = [v.get("option1"), v.get("option2"), v.get("option3")]
        flav = None
        pack = []
        for n, val in zip(optnames, vals):
            if not val:
                continue
            if re.search(r"flavou?r|taste|geschmack|smak|flavor", str(n), re.I):
                flav = val
            else:
                pack.append(val)
        if flav is None and len(optnames) == 1 and re.search(r"flavou?r|taste|geschmack", str(optnames[0]), re.I):
            flav = vals[0]
        price = v.get("price")
        if p.get("_js") and isinstance(price, (int, float)):
            price = price / 100.0
        out.append({
            "record_type": "variant", "name": p.get("title"), "brand": cfg["brand"], "sku": v.get("sku"),
            "ean": uc_norm_ean(v.get("barcode")), "flavour": flav, "option_values": [x for x in vals if x],
            "price": float(price) if price not in (None, "") else None, "currency": cfg["cur"], "country": cfg["country"],
            "brand_site": cfg["host"], "available": v.get("available"), "page_url": page_url,
            "source_url": f"{page_url}?variant={v.get('id')}" if v.get("id") else page_url + "#default",
        })
    return out


def uc_norm_ean(s):
    d = re.sub(r"\D", "", str(s or ""))
    return d if len(d) in (8, 12, 13, 14) else None


NUTR_LAB = re.compile(r"(protein|energy|calories|carbohydrate|kohlenhydrat|eiwei|brennwert|energi|fat\b|fett)", re.I)


def extract_nutrition(html, jl):
    """Return (nutrition dict | None, ingredients | None, flags[], extra)."""
    s = BeautifulSoup(html, "lxml")
    flags = []
    extra = {}
    cands = []
    # 0. text panel 'Nutrition Facts. Serving size: ... Protein: 21g' (US sites, e.g. Quest)
    txt0 = s.get_text(" ", strip=True)
    m0 = re.search(r"Nutrition Facts\.?\s*Serving size:.{0,1500}?Protein:?\s*\d+\s*g", txt0, re.I)
    if m0:
        t0 = uc.text_panel(m0.group(0))
        if t0:
            cands.append(t0)
            flags.append("nutrition_from_text_panel")
    # 1. HTML tables (leaf tables only)
    for tb in ([] if cands else s.find_all("table")):
        if tb.find("table"):
            continue
        rows = uc.table_rows(tb)
        labs = [r[0] for r in rows if r]
        if sum(1 for l in labs if NUTR_LAB.search(l or "")) < 2:
            continue
        # strip a leading title row holding a single cell
        t = uc.parse_rows(rows)
        if t:
            cap = tb.find_previous(["h1", "h2", "h3", "h4", "h5", "p", "strong"])
            t["flavour_label"] = t.get("flavour_label") or (cap.get_text(" ", strip=True)[:80] if cap else None)
            cands.append(t)
    # 1b. div-based tables (Grenade: .nutrition_table > .nutrition_title > .nutrition_name + .nutrition_value*)
    if not cands:
        for nt in s.select(".nutrition_table"):
            rows = []
            for d in nt.select(".nutrition_title"):
                nm = d.select_one(".nutrition_name")
                vals = [v.get_text(" ", strip=True) for v in d.select(".nutrition_value")]
                if nm:
                    rows.append([nm.get_text(" ", strip=True)] + vals)
            t = uc.parse_rows(rows)
            if t:
                cands.append(t)
    # also split tables: header table + body table(s) (Scitec: a header row then rows)
    if not cands:
        tbl_list = [tb for tb in s.find_all("table") if not tb.find("table")]
        for a, b in zip(tbl_list, tbl_list[1:]):
            ra, rb = uc.table_rows(a), uc.table_rows(b)
            if ra and len(ra) == 1 and sum(1 for r in rb if r and NUTR_LAB.search(r[0] or "")) >= 2:
                t = uc.parse_rows(ra + rb)
                if t:
                    cands.append(t)
    # 2. JSON-LD additionalProperty (Scitec style): name -> value (+ description = basis)
    if not cands:
        for g in jl:
            if g.get("@type") == "Product" and isinstance(g.get("additionalProperty"), list):
                rows = [[ap.get("name"), ap.get("value"), ap.get("description")] for ap in g["additionalProperty"] if isinstance(ap, dict)]
                if sum(1 for r in rows if NUTR_LAB.search(r[0] or "")) >= 2:
                    extra["jsonld_additional_property"] = rows
    # 3. text panel
    if not cands:
        txt = s.get_text(" ", strip=True)
        m = re.search(r"Nutrition Facts\.?\s*Serving size:.{0,1500}?Protein:?\s*\d+\s*g", txt, re.I)
        if m:
            t = uc.text_panel(m.group(0))
            if t:
                cands.append(t)
                flags.append("nutrition_from_text_panel")
    nut = None
    if cands:
        # prefer the candidate with a per-100 column and energy
        def score(t):
            return (bool(t["per_100"]) * 2 + bool(t["per_100"].get("energy_kcal") or t["per_serving"].get("energy_kcal")) + bool(t["per_100"].get("protein") or t["per_serving"].get("protein")))
        nut = sorted(cands, key=score, reverse=True)[0]
        if len(cands) > 1:
            flags.append(f"{len(cands)}_nutrition_tables_on_page_first_best_used")
            extra["other_table_labels"] = [c.get("flavour_label") for c in cands]
        flags.append("nutrition_page_level_not_flavour_verified")
    else:
        imgs = [i.get("src", "") + " " + (i.get("alt") or "") for i in s.find_all("img")]
        if any(re.search(r"(nfp|sfp|nutrition|supplement[-_ ]?facts|nutri)", i, re.I) for i in imgs) or re.search(r"(nutrition|supplement) facts", html, re.I):
            flags.append("nutrition_image_only")
        else:
            flags.append("no_nutrition_found")
    ing = None
    m = re.search(r"(?i)\b(ingredients?|zutaten|ingrediënten)\s*[:\-]\s*(.{20,1500}?)(?:\.\s*(?:allergen|may contain|suitable|nutrition|directions|suggested|warning|produced)|<)", s.get_text(" ", strip=True))
    if m:
        ing = m.group(2).strip()
    return nut, ing, flags, extra


def run(key, limit=0, out=None):
    cfg = SITES[key]
    log = Logger(key)
    path = out or uc.out_paths(key)
    cl = Client(key, log)
    cl.s.headers.update(uc.EN)
    log(f"START {key} ({cfg['host']})")
    n_new = 0
    try:
        prods = catalogue(cl, cfg, log)
        keep = [p for p in prods if uc.is_foodish(p.get("title") or "", p.get("product_type") or p.get("type") or "", p.get("tags") if isinstance(p.get("tags"), str) else " ".join(p.get("tags") or []))]
        log(f"food-ish (not apparel/gear): {len(keep)} of {len(prods)}")
        done = uc.load_done(path)
        def purl(p):
            return p.get("_url") or f"https://{cfg['host']}/products/{p['handle']}"
        todo = [p for p in keep if purl(p) not in done]
        if limit:
            todo = todo[:limit]
        for i, p in enumerate(todo, 1):
            url = purl(p)
            html = cl.get(url)
            if html is None:
                log(f"SKIP no page {url}")
                continue
            jl = uc.jsonld(html)
            if p.get("_url"):
                mt = re.search(r'<meta property="og:title" content="([^"]+)"', html)
                if mt:
                    import html as _h
                    p["title"] = _h.unescape(mt.group(1)).split(" - ")[0].split(" | ")[0]
            nut, ing, flags, extra = extract_nutrition(html, jl)
            gt = None
            for g in jl:
                if g.get("@type") in ("Product", "ProductGroup"):
                    gt = g.get("gtin") or g.get("gtin12") or g.get("gtin13") or g.get("gtin8") or gt
            page = {"record_type": "page", "source": key, "source_url": url, "fetched_on": today(), "name": p.get("title"),
                    "brand": cfg["brand"] or p.get("vendor"), "brand_site": cfg["host"], "country": cfg["country"], "product_type": p.get("product_type") or p.get("type"),
                    "tags": p.get("tags"), "description": uc.strip_html(p.get("body_html"))[:3000], "ingredients": ing, "page_gtin": gt,
                    "nutrition": nut, "nutrition_flags": flags, "extra": extra,
                    "options": p.get("options")}
            vs = variant_records(p, cfg, url, flags)
            for v in vs:
                v.update({"source": key, "fetched_on": today(), "nutrition": nut, "nutrition_flags": list(flags), "ingredients": ing})
                if not v["ean"] and gt and len(vs) == 1:
                    v["ean"] = uc_norm_ean(gt)
                append(path, v)
            append(path, page)
            n_new += 1
            if i % 25 == 0:
                log(f"progress {i}/{len(todo)} pages={n_new} requests={cl.requests_made}")
    except Blocked as e:
        log(f"BLOCKED: {e}")
    log(f"END {key} pages_new={n_new} requests={cl.requests_made}")
    return n_new


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("key")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out")
    a = ap.parse_args()
    run(a.key, a.limit, a.out)
