#!/usr/bin/env python3
"""barebells.com (brand site) product pages. Each page carries a per-country nutrition/ingredient row; Norway = country-19
(shared Danish/Norwegian label text). If Norway is missing we fall back to International (24) then Sweden (9) with a flag.
Output: data/raw/barebells/products.jsonl. Usage: barebells.py [--limit N] [--test]"""
import os, re, sys, json
from bs4 import BeautifulSoup
sys.path.insert(0, os.path.dirname(__file__))
import nogen as N

SRC = "barebells-no"
BASE = "https://barebells.com"
OUT = f"{N.ROOT}/data/raw/{SRC}/products.jsonl"
os.makedirs(os.path.dirname(OUT), exist_ok=True)
COUNTRIES = {"19": "Norway", "23": "Denmark", "9": "Sweden", "24": "International", "18": "Finland", "17": "UK/Ireland"}
PREF = ["19", "23", "24", "9", "18"]
clean = N.clean


def parse(url, html):
    s = BeautifulSoup(html, "lxml")
    h1 = s.find("h1")
    if not h1:
        return None
    name = clean(h1.get_text(" ", strip=True))
    rows = {}
    for tr in s.select("tr.data-row"):
        cid = next((c.split("-", 1)[1] for c in tr.get("class", []) if c.startswith("country-")), None)
        if not cid:
            continue
        tabs = [N.structure_rows(N.table_rows(t)) for t in tr.find_all("table")]
        tabs = [t for t in tabs if t and (t["per_100"] or t["per_serving"])]
        txt = clean(tr.get_text(" ", strip=True))
        ing = re.search(r"(?:INGREDIENS?|INGREDIENT|INGREDIENSER|INGREDIENTS)\s*:?\s*(.*?)(?=\s+(?:N[æa]rings|Nutrition|Närings|Ravitsemus)|$)", txt, re.I)
        rows[cid] = {"nutrition": N.merge_nutrition(tabs), "ingredients": ing.group(1).strip() if ing else None, "head_over": txt.lower().startswith("head over") or txt.lower().startswith("can")}
    pick = next((c for c in PREF if rows.get(c) and rows[c]["nutrition"]), None)
    flags = ["flavour_nutrition_shared_assumed"]
    nut = rows[pick]["nutrition"] if pick else None
    if pick and pick != "19":
        flags.append(f"nutrition_from_{COUNTRIES.get(pick, pick).lower().replace('/', '_')}_not_norway")
    if nut is None:
        flags.append("no_nutrition_table")
    desc = s.find("meta", attrs={"name": "description"})
    others = {COUNTRIES.get(c, c): r["nutrition"]["per_100"] for c, r in rows.items() if r["nutrition"] and c != pick and c in COUNTRIES}
    kind = "bar"
    if nut:
        sl = (nut.get("serving_label") or "") + " " + " ".join(nut.get("raw_columns") or [])
        if re.search(r"ml|burk|can|flaske|bottle", sl, re.I):
            kind = "drink"
    return {
        "source": SRC, "source_url": url, "fetched_on": N.TODAY, "name": name, "brand": "Barebells", "sku": None, "ean": None,
        "product_type_guess": kind, "country_label_used": COUNTRIES.get(pick, pick), "description": clean(desc.get("content")) if desc else None,
        "ingredients": rows[pick]["ingredients"] if pick else None, "nutrition": nut, "nutrition_other_countries_per100": others or None,
        "nutrition_flags": flags, "page_status": "live", "archive_timestamp": None, "discontinued": False,
    }


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    test = "--test" in sys.argv
    out = OUT.replace("products.jsonl", "test.jsonl") if test else OUT
    cl = N.Client(SRC, BASE)
    r = cl.get(BASE + "/sitemap--post--barebells_product.xml")
    urls = re.findall(r"<loc>([^<]+)</loc>", r.text) if r else []
    cl.log(f"{len(urls)} product urls")
    done = set() if test else N.load_done(out)
    todo = [u for u in urls if u not in done]
    if limit:
        todo = todo[:limit]
    n = 0
    with open(out, "w" if test else "a", encoding="utf8") as f:
        for u in todo:
            rr = cl.get(u)
            if not rr:
                continue
            rec = parse(u, rr.content.decode("utf-8", "replace"))
            if rec:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush(); n += 1
    cl.log(f"END saved={n} requests={cl.n}")


if __name__ == "__main__":
    main()
