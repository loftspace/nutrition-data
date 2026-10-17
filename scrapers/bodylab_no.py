#!/usr/bin/env python3
"""Bodylab.no (Shopware 6) scraper. Product URLs are single-segment slugs (sitemap + category listings); flavour variants
have their own SEO urls linked from the parent page (class configurator-variant-seo-link). Nutrition tables are server
rendered in #ingredient-content. Output: data/raw/bodylab-no/products.jsonl. Usage: bodylab_no.py [--limit N] [--test]"""
import os, re, sys, json, gzip
from bs4 import BeautifulSoup
sys.path.insert(0, os.path.dirname(__file__))
import nogen as N

SRC = "bodylab-no"
BASE = "https://www.bodylab.no"
OUT = f"{N.ROOT}/data/raw/{SRC}/products.jsonl"
os.makedirs(os.path.dirname(OUT), exist_ok=True)
NONPROD = {"oppskrifter", "muskeloppbygging", "mat-snacks", "vekttap", "energi", "tilskudd", "klaer-utstyr", "tilbud", "pakker", "produkter",
           "team-bodylab", "artikler", "kom-i-gang", "you", "serier", "konkurransebetingelser", "guider", "spoer-ekspertene", "kampanjer"}
SKIP_NAME = re.compile(r"(shaker|t-shirt|tank|hoodie|bukse|shorts|genser|caps?\b|lue|bag|veske|håndkle|belt|strap|gym ?bag|vannflaske|flaske|gavekort|sokker)", re.I)


def meta(s, prop):
    m = s.find("meta", attrs={"property": prop})
    return clean(m.get("content")) if m and m.get("content") else None


clean = N.clean


def discover(cl, crawl=True):
    urls = {}
    r = cl.get(BASE + "/sitemap.xml")
    subs = re.findall(r"<loc>([^<]+)</loc>", r.text) if r else []
    cats = []
    for sm in subs:
        rr = cl.get(sm)
        if not rr:
            continue
        c = rr.content
        if c[:2] == b"\x1f\x8b":
            c = gzip.decompress(c)
        for u in re.findall(r"<loc>([^<]+)</loc>", c.decode("utf8", "replace")):
            path = u.replace(BASE, "").strip("/")
            if path and "/" not in path and path not in NONPROD and "?" not in path:
                urls.setdefault(u, "sitemap")
            elif path.count("/") >= 1 and not path.startswith(("oppskrifter", "rcp_recipe", "information", "kundeservice", "artikler", "guider", "serier", "klaer-utstyr")):
                cats.append(u)
    cl.log(f"sitemap: {len(urls)} root slugs, {len(cats)} category pages")
    for cu in (cats if crawl else []):
        for page in range(1, 8):
            u = cu + ("" if page == 1 else f"?p={page}")
            rr = cl.get(u)
            if not rr:
                break
            hs = set(re.findall(r'href="' + re.escape(BASE) + r'/([a-z0-9][a-z0-9-]*)"', rr.text))
            new = 0
            for h in hs:
                if h in NONPROD or h in ("sitemap",):
                    continue
                full = f"{BASE}/{h}"
                if full not in urls:
                    urls[full] = "category"; new += 1
            if new == 0:
                break
    cl.log(f"discovered {len(urls)} candidate urls")
    return urls


def parse(url, html, is_variant=False):
    s = BeautifulSoup(html, "lxml")
    if (meta(s, "og:type") or "") != "product":
        return None, []
    h1 = s.find("h1")
    name = clean(h1.get_text(" ", strip=True)) if h1 else meta(s, "og:title")
    ld = None
    for sc in s.find_all("script", type="application/ld+json"):
        try:
            j = json.loads(sc.string or "")
        except Exception:
            continue
        if isinstance(j, dict) and j.get("@type") == "Product":
            ld = j
        if isinstance(j, dict) and j.get("@type") == "BreadcrumbList":
            crumbs = [clean(i.get("name")) for i in j.get("itemListElement", [])]
    crumbs = locals().get("crumbs", [])
    off = (ld or {}).get("offers") or {}
    if isinstance(off, list):
        off = off[0] if off else {}
    c = s.find(id="ingredient-content")
    tables, text = [], ""
    if c:
        for t in c.find_all("table"):
            st = N.structure_rows(N.table_rows(t))
            if st:
                tables.append(st)
        text = clean(c.get_text(" ", strip=True))
    nut = N.merge_nutrition(tables)
    ing = re.search(r"Ingredienser\s+(.*?)(?=\s+(?:Varebetegnelse|Oppbevaring|Bruksanvisning|Kan inneholde)\b|$)", text)
    allerg = re.search(r"(Kan inneholde[^.]*\.)", text)
    use = re.search(r"Bruksanvisning\s+(.*?)(?=\s+(?:Ingredienser|Varebetegnelse|Oppbevaring)\b|$)", text)
    vlinks = [l for l in re.findall(r'<a href="([^"]+)"\s+class="configurator-variant-seo-link"', html)]
    pack = None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l|stk|kapsler|tabletter)\b", name or "", re.I)
    mult = re.search(r"(\d+)\s*[xX]\s*(\d+(?:[.,]\d+)?)\s*(g|ml)", name or "")
    if m:
        pack = {"size_text": m.group(0), "size_value": N.tonum(m.group(1)), "size_unit": m.group(2).lower()}
    if mult:
        pack = (pack or {}); pack["multipack"] = int(mult.group(1)); pack["size_text"] = mult.group(0)
    flags = []
    if nut is None:
        flags.append("no_nutrition_table")
        if re.search(r"n[æe]ringsinnhold", text, re.I):
            flags.append("nutrition_mentioned_but_no_table_maybe_image")
    else:
        if not nut["per_100"].get("energy_kcal") and not nut["per_100"]:
            flags.append("per_100_missing_per_serving_only")
    flags.append("flavour_nutrition_shared_assumed")
    rec = {
        "source": SRC, "source_url": url, "fetched_on": N.TODAY, "name": name, "brand": meta(s, "product:brand") or (ld or {}).get("brand", {}).get("name"),
        "sku": (ld or {}).get("sku"), "ean": (ld or {}).get("gtin13") or (ld or {}).get("gtin") or None,
        "is_variant_page": is_variant, "breadcrumbs": crumbs, "price_nok": float(off["price"]) if off.get("price") not in (None, "") else None,
        "availability": (off.get("availability") or "").rsplit("/", 1)[-1] or None,
        "pack": pack, "description": clean((ld or {}).get("description") or meta(s, "og:description")),
        "ingredients": ing.group(1).strip() if ing else None, "allergen_text": allerg.group(1) if allerg else None, "usage": use.group(1).strip() if use else None,
        "nutrition": nut, "nutrition_flags": flags, "page_status": "live", "archive_timestamp": None, "discontinued": False,
    }
    return rec, vlinks


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    test = "--test" in sys.argv
    out = OUT.replace("products.jsonl", "test.jsonl") if test else OUT
    cl = N.Client(SRC, BASE)
    urls = discover(cl, crawl=not test)
    done = set() if test else N.load_done(out)
    queue = [u for u in urls if u not in done]
    if limit:
        queue = queue[:limit]
    seen = set(done) | set(queue)
    cl.log(f"to fetch {len(queue)}")
    n = skipped = 0
    with open(out, "w" if test else "a", encoding="utf8") as f:
        i = 0
        while i < len(queue):
            u = queue[i]; i += 1
            r = cl.get(u)
            if not r:
                continue
            rec, vl = parse(u, r.text, is_variant=urls.get(u) == "variant")
            if rec is None:
                skipped += 1
                continue
            f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush(); n += 1
            for v in vl:
                if v not in seen and v.startswith(BASE) and not limit:
                    seen.add(v); urls[v] = "variant"; queue.append(v)
            if n % 50 == 0:
                cl.log(f"progress saved={n} queue={len(queue)-i} reqs={cl.n}")
    cl.log(f"END saved={n} nonproduct_skipped={skipped} requests={cl.n}")


if __name__ == "__main__":
    main()
