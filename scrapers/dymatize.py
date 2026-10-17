#!/usr/bin/env python3
"""dymatize.com (US brand, BellRing). Rules: see ../README.md.
Discovery: sitemaps-1-section-products-1-sitemap.xml (robots allows). One page per flavour; US Nutrition Facts HTML table
(per serving + %DV), serving size in the text above it, ingredients in the page. No EAN on the pages (flag).
Output: data/raw/dymatize/products.jsonl (record_type=page + one record_type=variant per page).
"""
import re, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ukus_common as uc
from bs4 import BeautifulSoup

KEY = "dymatize"


def main(limit=0, out=None):
    log = uc.Logger(KEY)
    path = out or uc.out_paths(KEY)
    cl = uc.Client(KEY, log)
    cl.s.headers.update(uc.EN)
    log("START dymatize")
    n = 0
    try:
        idx = cl.get("https://dymatize.com/sitemaps-1-section-products-1-sitemap.xml") or ""
        urls = [u for u in re.findall(r"<loc>([^<]+)</loc>", idx) if "/products/" in u]
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
            h1 = s.find("h1")
            name = h1.get_text(" ", strip=True) if h1 else u
            nut = None
            tb = s.select_one("table.nutrition-facts")
            if tb:
                nut = uc.parse_rows(uc.table_rows(tb), None, "Nutrition Facts")
                txt = s.get_text(" ", strip=True)
                m = re.search(r"Serving Size:\s*([^()]{0,40}\(\s*(\d+(?:[.,]\d+)?)\s*(g|ml)\s*\))", txt, re.I)
                if nut and m:
                    nut["serving_label"] = "Serving Size: " + m.group(1)
                    nut["serving_size"] = {"raw": m.group(1), "value": uc.tonum(m.group(2)), "unit": m.group(3)}
            flags = ["no_ean_on_page"]
            flags.append("nutrition_from_html_table" if nut else "no_nutrition_found")
            m = re.search(r"INGREDIENTS:\s*</strong></p>\s*<p>(.{10,1500}?)</p>", t, re.S | re.I)
            ing = uc.strip_html(m.group(1)) if m else None
            bc = None
            for g in uc.jsonld(t):
                if g.get("@type") == "BreadcrumbList":
                    bc = g["itemListElement"][-1]["name"]
            desc = s.find("meta", attrs={"name": "description"})
            page = {"record_type": "page", "source": KEY, "source_url": u, "fetched_on": uc.today(), "name": bc or name, "title": name,
                    "brand": "Dymatize", "brand_site": "dymatize.com", "country": "US", "ingredients": ing, "nutrition": nut,
                    "nutrition_flags": flags, "description": desc.get("content") if desc else None}
            var = {"record_type": "variant", "source": KEY, "source_url": u + "#variant", "page_url": u, "fetched_on": uc.today(),
                   "name": bc or name, "brand": "Dymatize", "sku": None, "ean": None, "flavour": None, "nutrition": nut,
                   "nutrition_flags": flags, "ingredients": ing, "country": "US", "brand_site": "dymatize.com"}
            uc.append(path, var)
            uc.append(path, page)
            n += 1
    except uc.Blocked as e:
        log(f"BLOCKED: {e}")
    log(f"END dymatize pages={n} requests={cl.requests_made}")


if __name__ == "__main__":
    lim = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 0
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
    main(lim, out)
