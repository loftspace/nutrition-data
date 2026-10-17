"""Shared parser for the Nortura CMS sites (gilde.no, prior.no): server-rendered tables."""
import re
from bs4 import BeautifulSoup
from common import *


def sitemap_urls(cl, log, sm_urls, pattern):
    out = []
    for sm in sm_urls:
        t = cl.get(sm)
        if not t:
            continue
        locs = re.findall(r"<loc>(.*?)</loc>", t)
        out += [l for l in locs if re.search(pattern, l)]
    return sorted(set(out))


def ingredients_of(s):
    for el in s.find_all(["h2", "h3", "h4", "p", "span", "strong"]):
        if el.get_text(" ", strip=True).lower() == "ingredienser":
            nxt = el.find_next(["p", "div"])
            if nxt:
                t = nxt.get_text(" ", strip=True)
                if t and t.lower() != "ingredienser":
                    return t
    return None


def parse(html, brand):
    s = BeautifulSoup(html, "lxml")
    h1 = s.find("h1")
    name = h1.get_text(" ", strip=True) if h1 else None
    if not name:
        og = s.find("meta", property="og:title")
        name = og["content"].strip() if og and og.get("content") else (s.title.get_text(strip=True) if s.title else None)
    if not name:
        return None
    rec = {"name": name, "brand": brand}
    info, nut_rows, allergens = {}, [], {}
    for tb in s.find_all("table"):
        rows = []
        for tr in tb.find_all("tr"):
            cells = [re.sub(r"\s+", " ", c.get_text(" ", strip=True)) for c in tr.find_all(["td", "th"])]
            if len(cells) >= 2:
                rows.append((cells[0], cells[1]))
            elif len(cells) == 1:
                rows.append((cells[0], ""))
        labels = [r[0].lower() for r in rows]
        if any(l.startswith("energi") for l in labels):
            nut_rows = [(a, b) for a, b in rows if b and a.lower() != "hvorav"]
        elif "gtin" in labels or "opprinnelsesland" in labels:
            info = {a: b for a, b in rows}
        elif "gluten" in labels:
            allergens = {a: b for a, b in rows}
    rec["ean"] = norm_ean(info.get("GTIN"))
    rec["material_number"] = re.sub(r"\D", "", info.get("Materialnummer", "")) or None
    rec["origin_country"] = info.get("Opprinnelsesland")
    w = info.get("Vekt pkn")
    rec["pack_size_raw"] = w
    m = re.search(r"([\d.,]+)\s*kg", w or "")
    rec["pack_size_g"] = round(to_float(m.group(1)) * 1000, 1) if m else None
    rec["storage"] = info.get("Oppbevaring")
    rec["ingredients"] = ingredients_of(s)
    rec["allergens_contained"] = [k for k, v in allergens.items() if v.strip().lower() in ("ja", "yes")]
    rec["allergens_raw"] = allergens or None
    if nut_rows:
        tbl = make_table("Næringsinnhold pr 100g", nut_rows)
        tbl["basis"] = "per_100"
        rec["nutrition"] = {"tables": [tbl]}
        rec["nutrition_per100"] = tbl["values"]
        rec["nutrition_flag"] = None
    else:
        rec["nutrition"] = None
        rec["nutrition_per100"] = None
        rec["nutrition_flag"] = "no_nutrition_on_page"
    return rec
