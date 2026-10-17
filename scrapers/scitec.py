#!/usr/bin/env python3
"""scitecnutrition.com (Hungarian brand, EUR shop). Rules: see ../README.md.
Discovery: media/sitemaps/sitemap_58_product.xml (robots allows), product pages end in -p<id>; /reviews pages skipped.
Each page: JSON-LD Product (gtin of the default variant, price EUR), a variant table (flavours, stock), a 'Supplement Facts'
panel as HTML tables (per serving + RI + per 100 g, then vitamins/other actives). One panel per page, flavours share it.
Output: data/raw/scitec/products.jsonl (record_type=page + one record_type=variant per flavour).
"""
import re, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ukus_common as uc
from bs4 import BeautifulSoup

KEY = "scitec"


def fix_rows(rows):
    """Rows may omit the RI/NRV cell: re-insert an empty cell so columns line up with the header."""
    hdr = rows[0]
    ri = [i for i, c in enumerate(hdr) if re.fullmatch(r"(RI|NRV|%RI|%NRV|DRI)", c.strip(), re.I)]
    out = [hdr]
    for r in rows[1:]:
        if ri and len(r) == len(hdr) - 1 and len(r) > 1:
            r = r[:ri[0]] + [""] + r[ri[0]:]
        out.append(r)
    return out


def is_flavour_table(rows):
    return bool(rows and rows[0] and rows[0][0].strip().lower() in ("flavor", "flavour") and len(rows[0]) == 2)


def main(limit=0, out=None):
    log = uc.Logger(KEY)
    path = out or uc.out_paths(KEY)
    cl = uc.Client(KEY, log)
    cl.s.headers.update(uc.EN)
    log("START scitec")
    n = 0
    try:
        idx = cl.get("https://scitecnutrition.com/media/sitemaps/sitemap_58_product.xml") or ""
        urls = [u for u in re.findall(r"<loc>([^<]+)</loc>", idx) if re.search(r"-p\d+$", u)]
        done = uc.load_done(path)
        todo = [u for u in urls if u not in done]
        if limit:
            todo = todo[:limit]
        log(f"{len(urls)} product urls, {len(todo)} to fetch")
        for u in todo:
            t = cl.get(u)
            if not t:
                continue
            s = BeautifulSoup(t, "lxml")
            jl = uc.jsonld(t)
            prod = {}
            for g in jl:
                ty = g.get("@type")
                ty = ty if isinstance(ty, list) else [ty]
                if "Product" in ty:
                    prod = g
                    break
            name = prod.get("name") or (s.find("h1").get_text(" ", strip=True) if s.find("h1") else u)
            offer = prod.get("offers") or {}
            tables = [tb for tb in s.find_all("table") if not tb.find("table")]
            flavours, nut_tabs = [], []
            for tb in tables:
                rows = uc.table_rows(tb)
                if is_flavour_table(rows):
                    flavours = [r[0] for r in rows[1:] if r]
                elif rows and sum(1 for r in rows if r and (uc.NUTR_LAB.search(r[0] or "") or re.search(r"\d\s*(mg|µg|μg|g)\b", r[1] if len(r) > 1 else ""))) >= 2:
                    nut_tabs.append(rows)
            parsed = [uc.parse_rows(fix_rows(r), None) for r in nut_tabs]
            parsed = [p for p in parsed if p]
            nut = parsed[0] if parsed else None
            extra_tables = parsed[1:]
            flags = []
            txt = s.get_text(" ", strip=True)
            if nut:
                flags.append("nutrition_page_level_not_flavour_verified")
                m = re.search(r"1 serving[:\s]+(\d+(?:[.,]\d+)?)\s*(g|ml)", txt, re.I)
                if m and not nut.get("serving_size"):
                    nut["serving_size"] = {"raw": m.group(0), "value": uc.tonum(m.group(1)), "unit": m.group(2).lower()}
            else:
                flags.append("no_nutrition_found")
            ing = None
            m = re.search(r"INGREDIENTS\s+(.{20,3000}?)(?:\s+(?:Allergen|Directions|Suggested use|Recommended|Warning|Nutrition)|$)", txt)
            if m:
                ing = m.group(1)
            pk = re.search(r"Packaging\s+([\d.,]+\s*(?:kg|g|ml|l|caps|capsules|tablets|tabs|pcs)\b)", txt, re.I)
            gtin = prod.get("gtin") or prod.get("gtin13")
            brand = (prod.get("brand") or {}).get("name") or "Scitec Nutrition"
            cat = prod.get("category")
            price = offer.get("price") if isinstance(offer, dict) else None
            page = {"record_type": "page", "source": KEY, "source_url": u, "fetched_on": uc.today(), "name": name, "brand": brand,
                    "brand_site": "scitecnutrition.com", "country": "HU", "category": cat, "pack_size_raw": pk.group(1) if pk else None,
                    "price_eur": price, "page_gtin": gtin, "sku": prod.get("sku"),
                    "flavours": flavours, "ingredients": ing, "nutrition": nut, "extra_tables": extra_tables, "nutrition_flags": flags,
                    "description": prod.get("description")}
            for fl in (flavours or [None]):
                tag = re.sub(r"[^a-z0-9]+", "-", (fl or "default").lower())
                v = {"record_type": "variant", "source": KEY, "source_url": f"{u}#{tag}", "page_url": u,
                     "fetched_on": uc.today(), "name": name, "brand": brand, "sku": None, "ean": None, "flavour": fl, "nutrition": nut,
                     "extra_tables": extra_tables, "nutrition_flags": list(flags) + ["ean_is_page_level_see_page_gtin"], "ingredients": ing,
                     "country": "HU", "brand_site": "scitecnutrition.com", "pack_size_raw": pk.group(1) if pk else None,
                     "price_eur": price, "category": cat}
                uc.append(path, v)
            uc.append(path, page)
            n += 1
            if n % 25 == 0:
                log(f"progress {n}/{len(todo)} requests={cl.requests_made}")
    except uc.Blocked as e:
        log(f"BLOCKED: {e}")
    log(f"END scitec pages={n} requests={cl.requests_made}")


if __name__ == "__main__":
    lim = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 0
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
    main(lim, out)
