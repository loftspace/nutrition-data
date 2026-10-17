#!/usr/bin/env python
"""Barebells.com and Nocco.com brand sites (WordPress, nutrition tables per country). Rules: ../README.md.
Per product page: Swedish nutrition table (Barebells: tr.data-row.country-9; Nocco: data-filter-tags="sweden") is the primary
nutrition; the other countries' tables go to extra_tables with their country label.
Sources: barebells, nocco.  Usage: python nordic_brands.py barebells|nocco [--limit N]
"""
import re
import sys

from se_common import *

CFG = {
    "barebells": {"base": "https://barebells.com", "sitemap": "/sitemap--post--barebells_product.xml", "brand": "Barebells"},
    "nocco": {"base": "https://nocco.com", "sitemap": "/sitemap--post--nocco_products.xml", "brand": "NOCCO"},
}
COUNTRY_IDS = {"9": "Sweden", "18": "Finland", "19": "Norway", "23": "Denmark"}


def discover_for(src):
    def discover(f, log):
        x = f.get(CFG[src]["base"] + CFG[src]["sitemap"])
        urls = [u for u in re.findall(r"<loc>([^<]+)</loc>", x or "") if "/product/" in u]
        log(f"sitemap product urls={len(urls)}")
        return urls
    return discover


def scrape_for(src):
    def scrape(f, url):
        h = f.get(url)
        if not h:
            return []
        s = soup(h)
        name = norm_ws(s.find("h1").get_text(" ")) if s.find("h1") else None
        tables_by_country = {}
        ing_by_country = {}
        if src == "barebells":
            ids = dict(COUNTRY_IDS)
            for o in s.select("select[name=country] option"):
                if o.get("value"):
                    ids[o["value"]] = norm_ws(o.get_text(" "))
            for tr in s.select("tr.data-row"):
                cls = " ".join(tr.get("class", []))
                m = re.search(r"country-(\d+)", cls)
                cid = m.group(1) if m else "?"
                cname = ids.get(cid, cid)
                inner = tr.find("table")
                tbls = []
                if inner is not None:
                    tbls = parse_nutrition_table(table_to_rows(inner))
                tables_by_country[cname] = tbls
                txt = norm_ws(tr.get_text(" "))
                mi = re.search(r"(?:INGREDIENSER|INGREDIENTS|INGREDIENSER|INGREDIENTER|AINESOSAT|SISÄLTÖ)\s*:?\s*(.*?)(?:Näringsvärde|Nutritional|Næringsind|Næringsinn|Ravintosis|$)", txt, re.I)
                if mi:
                    ing_by_country[cname] = mi.group(1).strip()[:4000]
        else:
            for fig in s.select(".nutrition-data"):
                tag = (fig.get("data-filter-tags") or "?").title()
                tbls = []
                for tb in fig.find_all("table"):
                    tbls.extend(parse_nutrition_table(table_to_rows(tb)))
                tables_by_country.setdefault(tag, []).extend(tbls)
                cap = fig.find("figcaption")
        prim_c = "Sweden" if tables_by_country.get("Sweden") else ("Global" if tables_by_country.get("Global") else None)
        flags = []
        nut = None
        if prim_c:
            nut = tables_by_country[prim_c][0]
            if prim_c != "Sweden":
                flags.append("swedish_table_missing_using_" + prim_c.lower())
        else:
            for c, t in tables_by_country.items():
                if t:
                    nut = t[0]
                    flags.append("swedish_table_missing_using_" + c.lower())
                    break
        if nut is None:
            flags.append("no_nutrition_table")
        elif not nut.get("per_100"):
            flags.append("per100_missing_serving_only")
        extra = []
        for c, tl in tables_by_country.items():
            for t in tl:
                if t is not nut:
                    t = dict(t)
                    t["country_label"] = c
                    extra.append(t)
        og = s.select_one('meta[property="og:description"]')
        desc = norm_ws(og["content"]) if og and og.get("content") else None
        rec = base_record(src, url, name=f"{CFG[src]['brand']} {name}", brand=CFG[src]["brand"], flavour=name, pack_size_text=None,
                          description=desc, ingredients=ing_by_country.get("Sweden") or next(iter(ing_by_country.values()), None) if ing_by_country else None,
                          nutrition=nut, nutrition_flags=flags)
        rec["country"] = "SE"
        rec["currency"] = None
        rec["extra_tables"] = extra
        rec["note"] = "brand site, no price/EAN published; nutrition = Swedish market table"
        return [rec]
    return scrape


if __name__ == "__main__":
    src = sys.argv[1]
    log = Logger(src)
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    f = Fetcher(src, CFG[src]["base"], log, lang="sv-SE,sv;q=0.9,en;q=0.5")
    log(f"START {src}")
    urls = discover_for(src)(f, log)
    run_crawl(src, urls, scrape_for(src), f, log, limit=limit)
