#!/usr/bin/env python3
"""Life.no (Norce shop, Norwegian health-store chain). URLs from googlesitemap.axd (products). Page has schema.org Product
JSON-LD (gtin, sku, brand, price) and a server-rendered nutrition table in the description. Some tables give a range
'Naeringsinnhold pr. | 20 - 100 gram' with values 'a - b' (serving and 100 g): split into both columns, never converted.
Output: data/raw/life-no/products.jsonl. Usage: life_no.py [--limit N] [--test]"""
import os, re, sys, json
from bs4 import BeautifulSoup
sys.path.insert(0, os.path.dirname(__file__))
import nogen as N

SRC = "life-no"
BASE = "https://www.life.no"
OUT = f"{N.ROOT}/data/raw/{SRC}/products.jsonl"
os.makedirs(os.path.dirname(OUT), exist_ok=True)
KEEP = ("mat-drikke", "kosttilskudd", "trening", "behov", "varemerker", "tips-rad")
clean = N.clean


def split_range_table(rows):
    """header like 'Naeringsinnhold pr. | 20 - 100 gram' -> two bases; values 'a - b'. Returns rows with 3 columns or None."""
    if not rows or len(rows[0]) != 2:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*[-–]\s*(\d+(?:[.,]\d+)?)\s*(g|gram|ml)\b", rows[0][1], re.I)
    if not m:
        return None
    unit = "g" if m.group(3).lower() in ("g", "gram") else "ml"
    out = [[rows[0][0], f"{m.group(1)} {unit}", f"{m.group(2)} {unit}"]]
    for r in rows[1:]:
        if len(r) != 2:
            continue
        v = r[1]
        if re.match(r"energi", r[0], re.I):
            mm = re.match(r"\s*(\d+)\s*/\s*(\d+)\s*[-–]\s*(\d+)\s*/\s*(\d+)", v.replace("\xa0", " "))
            if mm:
                out.append([r[0], f"{mm.group(1)} kJ / {mm.group(2)} kcal", f"{mm.group(3)} kJ / {mm.group(4)} kcal"])
            continue
        parts = re.split(r"\s+[-–]\s+", v)
        if len(parts) == 2:
            u = re.search(r"(mg|µg|μg|g|ml)\s*$", parts[1].strip(), re.I)
            a = parts[0] if re.search(r"[a-zµμ]$", parts[0].strip(), re.I) else parts[0] + (" " + u.group(1) if u else "")
            out.append([r[0], a, parts[1]])
    # make the 100 g column the per_100 one by relabelling: bases are (serving, 100) ordered as given
    return out


def parse(url, html):
    s = BeautifulSoup(html, "lxml")
    ld = None
    for sc in s.find_all("script", type="application/ld+json"):
        try:
            j = json.loads(sc.string or "")
        except Exception:
            continue
        if isinstance(j, dict) and j.get("@type") == "Product" and j.get("gtin") is not None or (isinstance(j, dict) and j.get("@type") == "Product" and j.get("offers")):
            if ld is None or j.get("gtin"):
                ld = j
    if not ld:
        return None
    h1 = s.find("h1")
    name = clean(h1.get_text(" ", strip=True)) if h1 else ld.get("name")
    off = ld.get("offers") or {}
    if isinstance(off, list):
        off = off[0] if off else {}
    tabs = []
    for t in s.find_all("table"):
        rows = N.table_rows(t)
        if not rows:
            continue
        rr = split_range_table(rows) or rows
        st = N.structure_rows(rr)
        if st and (st["per_100"] or st["per_serving"]):
            tabs.append(st)
    nut = N.merge_nutrition(tabs)
    text = clean(s.get_text(" ", strip=True))
    if nut is None:
        nut = N.parse_inline_nutrition(text)
        if nut:
            nut["from_inline_text"] = True
    ing = re.search(r"Ingredienser:?\s*(.*?)(?=\s+(?:N[æe]ringsinnhold|Oppbevaring|Bruksanvisning|Allergener|Anbefalt)|$)", text)
    flags = ["flavour_nutrition_shared_assumed"]
    if nut is None:
        flags.append("no_nutrition_table")
    elif not nut["per_100"]:
        flags.append("per_100_missing_per_serving_only")
    crumbs = []
    for sc in s.find_all("script", type="application/ld+json"):
        try:
            j = json.loads(sc.string or "")
        except Exception:
            continue
        if isinstance(j, dict) and j.get("@type") == "BreadcrumbList":
            crumbs = [clean(i.get("name") or (i.get("item") or {}).get("name") or "") for i in j.get("itemListElement", [])]
    pack = None
    m = re.search(r"(\d+)\s*[xX]\s*(\d+(?:[.,]\d+)?)\s*(g|ml|kg|l)\b", name or "") or re.search(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l|stk|tbl|kaps|kapsler)\b", name or "", re.I)
    if m:
        pack = {"size_text": m.group(0)}
    path = url.replace(BASE, "").strip("/").split("/")
    return {
        "source": SRC, "source_url": url, "fetched_on": N.TODAY, "name": name, "brand": (ld.get("brand") or {}).get("name") if isinstance(ld.get("brand"), dict) else ld.get("brand"),
        "sku": ld.get("sku"), "ean": ld.get("gtin") or ld.get("gtin13"), "category_path": path[:-1], "breadcrumbs": crumbs,
        "price_nok": off.get("price"), "availability": (off.get("availability") or "").rsplit("/", 1)[-1] or None,
        "pack": pack, "description": clean(ld.get("description"))[:2000] if ld.get("description") else None,
        "ingredients": ing.group(1)[:1500] if ing else None, "nutrition": nut, "nutrition_flags": flags,
        "page_status": "live", "archive_timestamp": None, "discontinued": False,
    }


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    test = "--test" in sys.argv
    out = OUT.replace("products.jsonl", "test.jsonl") if test else OUT
    cl = N.Client(SRC, BASE)
    r = cl.get(BASE + "/googlesitemap.axd?SitemapType=products&page=1")
    urls = [u for u in re.findall(r"<loc>([^<]+)</loc>", r.text) if u.replace(BASE, "").strip("/").split("/")[0] in KEEP] if r else []
    cl.log(f"sitemap food-ish product urls: {len(urls)}")
    done = set() if test else N.load_done(out)
    todo = [u for u in urls if u not in done]
    if test:
        todo = todo[::max(1, len(todo) // (limit or 5))]
    if limit:
        todo = todo[:limit]
    n = 0
    with open(out, "w" if test else "a", encoding="utf8") as f:
        for i, u in enumerate(todo, 1):
            r = cl.get(u)
            if not r:
                continue
            try:
                rec = parse(u, r.content.decode("utf-8", "replace"))
            except Exception as e:
                cl.log(f"PARSE-ERR {u} {type(e).__name__} {e}")
                continue
            if rec is None:
                continue
            f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush(); n += 1
            if i % 50 == 0:
                cl.log(f"progress {i}/{len(todo)} saved={n} reqs={cl.n}")
    cl.log(f"END saved={n} requests={cl.n}")


if __name__ == "__main__":
    main()
