#!/usr/bin/env python
"""Proteinbolaget.se (Shopify). Rules: ../README.md.
Discovery: /products.json?limit=250&page=N (the shop's own public JSON; title, vendor, product_type, variants).
Per product page: JSON-LD offers (gtin13 per flavour variant), nutrition tables in the 'Innehåll' tab (one table per
flavour), ingredient/allergen paragraphs per flavour.
One record per variant (flavour) with that variant's EAN; nutrition = the flavour's own table when the flavour name
matches a table, otherwise the first table (flag flavour_nutrition_shared_assumed).
Usage: python proteinbolaget.py [--limit N]
"""
import json
import re
import sys

from se_common import *

SOURCE = "proteinbolaget"
BASE = "https://proteinbolaget.se"
SKIP_TYPES = {"Träningstillbehör", "Träningskläder", "Skönhet&kroppsvård"}
META = {}  # url -> products.json entry
SKIPPED_BUNDLES = []


def discover(f, log):
    urls = []
    for page in range(1, 40):
        d = f.get(f"{BASE}/products.json?limit=250&page={page}", json_mode=True)
        items = (d or {}).get("products") or []
        if not items:
            break
        for p in items:
            if p.get("product_type") in SKIP_TYPES:
                continue
            if looks_nonfood(p.get("title", "")) and not p.get("product_type") in ("Drycker", "Bars", "Proteinpulver"):
                continue
            if re.match(r"\s*\d+\s*[x×]\s", p.get("title", "")) or "bundle" in (p.get("tags") or []):
                SKIPPED_BUNDLES.append(p["handle"])
                continue
            u = f"{BASE}/products/{p['handle']}"
            META[u] = p
            urls.append(u)
        log(f"products.json page {page}: {len(items)} items, kept so far {len(urls)}")
    log(f"skipped multipack/bundle pages (same nutrition as the single product): {len(SKIPPED_BUNDLES)}")
    return urls


def flavour_map(p):
    """variant id -> (flavour, sku, price) from products.json."""
    opt_names = [o.get("name", "") for o in p.get("options", [])]
    out = {}
    for v in p.get("variants", []):
        fl = None
        for i, nm in enumerate(opt_names, 1):
            val = v.get(f"option{i}")
            if val and val != "Default Title" and re.search(r"smak|flavou?r|variant", nm, re.I):
                fl = val
        if fl is None and p.get("options") and len(p["options"]) == 1 and v.get("option1") not in (None, "Default Title"):
            fl = v["option1"]
        out[str(v["id"])] = (fl, v.get("sku"), v.get("price"), v.get("available"), v.get("title"))
    return out


def ld_offers(s):
    for t in s.find_all("script", type="application/ld+json"):
        try:
            d = json.loads(t.string or "")
        except ValueError:
            continue
        for x in (d if isinstance(d, list) else [d]):
            if isinstance(x, dict) and x.get("@type") in ("ProductGroup", "Product"):
                offers = x.get("offers")
                if offers is None and x.get("hasVariant"):
                    offers = []
                    for hv in x["hasVariant"]:
                        o = hv.get("offers")
                        offers += o if isinstance(o, list) else [o] if o else []
                if isinstance(offers, dict):
                    offers = [offers]
                return x, offers or []
    return None, []


def scrape(f, url):
    p = META.get(url) or {}
    h = f.get(url)
    if not h:
        return []
    s = soup(h)
    top, offers = ld_offers(s)
    fm = flavour_map(p) if p else {}
    # nutrition panel
    panel = None
    for hd in s.find_all(["h2", "h3", "h4"]):
        if re.search(r"n[äa]rings", hd.get_text(" "), re.I):
            panel = hd.parent
            break
    scope = panel if panel is not None else s
    tables = []
    for tb in scope.find_all("table"):
        tables.extend(parse_nutrition_table(table_to_rows(tb)))
    # ingredient / allergen paragraphs per flavour
    ing_by, all_by = {}, {}
    ing_generic = all_generic = None
    for pp in scope.find_all("p"):
        t = norm_ws(pp.get_text(" "))
        m = re.match(r"^Ingredienser?\s*(?:[–\-:]\s*([^:]+?))?\s*:\s*(.+)$", t, re.I)
        if m:
            if m.group(1):
                ing_by[fold(m.group(1))] = m.group(2)[:4000]
            elif ing_generic is None:
                ing_generic = m.group(2)[:4000]
            continue
        m = re.match(r"^Allergi\w*\s*(?:[–\-:]\s*([^:]+?))?\s*:\s*(.+)$", t, re.I)
        if m:
            if m.group(1):
                all_by[fold(m.group(1))] = m.group(2)[:1500]
            elif all_generic is None:
                all_generic = m.group(2)[:1500]
    name = norm_ws(p.get("title")) or norm_ws((top or {}).get("name"))
    brand = p.get("vendor") or ((top or {}).get("brand") or {}).get("name")
    cat = [p.get("product_type")] if p.get("product_type") else []
    desc = norm_ws(soup(p.get("body_html") or "").get_text(" "))[:1500] or None
    # variants from offers
    recs = []
    seen = set()
    entries = []
    for o in offers:
        m = re.search(r"variant=(\d+)", o.get("url", ""))
        vid = m.group(1) if m else None
        entries.append((vid, o))
    if not entries:
        for vid in fm:
            entries.append((vid, {}))
    for vid, o in entries:
        if vid in seen:
            continue
        seen.add(vid)
        fl, sku, price, avail, vtitle = fm.get(vid, (None, None, None, None, None))
        if fl is None and o.get("name") and " - " in o["name"]:
            fl = o["name"].rsplit(" - ", 1)[1]
        ean = ean_ok(o.get("gtin13") or o.get("gtin") or o.get("gtin12") or o.get("gtin8"))
        nut, flags = pick_primary(tables, fl)
        if not tables and s.find("img", src=re.compile(r"n[aä]ring|nutrition", re.I)):
            flags.append("nutrition_image_only")
        fkey = fold(fl or "")
        ing = ing_by.get(fkey) or next((v for k, v in ing_by.items() if fkey and (k in fkey or fkey in k)), None) or ing_generic
        if ing is None and ing_by:
            ing = next(iter(ing_by.values()))
            flags.append("ingredients_of_first_flavour")
        alg = all_by.get(fkey) or all_generic or (next(iter(all_by.values())) if all_by else None)
        try:
            pr = float(o.get("price") or price)
        except (TypeError, ValueError):
            pr = None
        rec = base_record(SOURCE, f"{url}?variant={vid}" if vid else url, page_url=url, name=name + (f" {fl}" if fl and fl.lower() not in name.lower() else ""),
                          brand=brand, sku=o.get("sku") or sku, ean=ean, flavour=fl, price_sek=pr, categories=cat + (p.get("tags") or [])[:0],
                          pack_size_text=pack_from_name(name), description=desc, ingredients=ing, allergens_text=alg, nutrition=nut,
                          nutrition_flags=flags)
        rec["product_name"] = name
        rec["tags"] = p.get("tags") or []
        rec["available"] = avail
        rec["extra_tables"] = [t for t in tables if t is not nut][:12]
        rec["is_bundle"] = bool(re.match(r"\s*\d+\s*[x×]\s", name or "") or "bundle" in (p.get("tags") or []) or "paket" in (name or "").lower())
        if "flavour_nutrition_shared_assumed" in flags:
            rec["flavour_nutrition_shared_assumed"] = True
        recs.append(rec)
    return recs


def load_done_pages(path):
    return load_done(path)


if __name__ == "__main__":
    log = Logger(SOURCE)
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    f = Fetcher(SOURCE, BASE, log)
    log(f"START {SOURCE}")
    urls = discover(f, log)
    run_crawl(SOURCE, urls, scrape, f, log, limit=limit)
