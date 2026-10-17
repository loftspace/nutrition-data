#!/usr/bin/env python3
"""Kost1.no (Norwegian supplement shop, mystore platform). robots.txt asks Crawl-delay 5 (honoured by nogen.Client).
Product urls from sitemap.xml (/products/...). Nutrition table is in the description (HTML table), sometimes prose.
No EAN is published on the page (sku only). Output: data/raw/kost1-no/products.jsonl. Usage: kost1_no.py [--limit N] [--test]"""
import os, re, sys, json
from bs4 import BeautifulSoup
sys.path.insert(0, os.path.dirname(__file__))
import nogen as N

SRC = "kost1-no"
BASE = "https://www.kost1.no"
OUT = f"{N.ROOT}/data/raw/{SRC}/products.jsonl"
os.makedirs(os.path.dirname(OUT), exist_ok=True)
clean = N.clean


def parse(url, html):
    s = BeautifulSoup(html, "lxml")
    prod = None
    for sc in s.find_all("script", type="application/ld+json"):
        try:
            j = json.loads(sc.string or "")
        except Exception:
            continue
        for g in (j.get("@graph") or [j]) if isinstance(j, dict) else []:
            me = g.get("mainEntity") if isinstance(g, dict) else None
            if isinstance(me, dict) and me.get("@type") == "Product":
                prod = me
            elif isinstance(g, dict) and g.get("@type") == "Product":
                prod = g
    if not prod:
        return None
    name = clean(prod.get("name"))
    off = prod.get("offers") or {}
    if isinstance(off, list):
        off = off[0] if off else {}
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
    ing = re.search(r"Ingredienser:?\s*(.*?)(?=\s+(?:Må ikke|Oppbevar|Dette kosttilskuddet|Allergen|Bruk|Anbefalt)|$)", text)
    flavour = re.search(r"Smak:\s*([^:]{2,40}?)(?:\s+(?:Anbefalt|Innhold|Nærings)|$)", text)
    size = re.search(r"Innhold per [a-z]+:\s*([^:]{2,60}?)(?:\s+(?:Smak|Anbefalt)|$)", text)
    flags = ["flavour_nutrition_shared_assumed"]
    if nut is None:
        flags.append("no_nutrition_table")
        if re.search(r"næringsinnhold|næringsdeklarasjon", text, re.I):
            flags.append("nutrition_mentioned_but_no_table_maybe_image")
    elif not nut["per_100"]:
        flags.append("per_100_missing_per_serving_only")
    pack = re.search(r"(\d+(?:[.,]\d+)?)\s*(kg|gram|g|ml|kapsler|tabletter|stk)\b", name or "", re.I)
    return {
        "source": SRC, "source_url": url, "fetched_on": N.TODAY, "name": name, "brand": (prod.get("brand") or {}).get("name") if isinstance(prod.get("brand"), dict) else prod.get("brand"),
        "sku": prod.get("sku"), "ean": prod.get("gtin13") or prod.get("gtin") or None, "price_nok": off.get("price"),
        "pack": {"size_text": pack.group(0)} if pack else None, "pack_contents_text": size.group(1) if size else None,
        "flavour": flavour.group(1).strip() if flavour else None, "description": clean(prod.get("description")),
        "ingredients": ing.group(1)[:1500] if ing else None, "nutrition": nut, "nutrition_flags": flags,
        "page_status": "live", "archive_timestamp": None, "discontinued": False,
    }


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    test = "--test" in sys.argv
    out = OUT.replace("products.jsonl", "test.jsonl") if test else OUT
    cl = N.Client(SRC, BASE)
    r = cl.get(BASE + "/sitemap.xml")
    urls = [u for u in re.findall(r"<loc>([^<]+)</loc>", r.text) if "/products/" in u] if r else []
    cl.log(f"{len(urls)} product urls")
    done = set() if test else N.load_done(out)
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
                rec = parse(u, rr.content.decode("utf-8", "replace"))
            except Exception as e:
                cl.log(f"PARSE-ERR {u} {type(e).__name__} {e}")
                continue
            if rec:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush(); n += 1
            if i % 25 == 0:
                cl.log(f"progress {i}/{len(todo)} saved={n} reqs={cl.n}")
    cl.log(f"END saved={n} requests={cl.n}")


if __name__ == "__main__":
    main()
