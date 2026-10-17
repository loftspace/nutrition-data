import sys, json, re, os
from bs4 import BeautifulSoup
from common import *

SOURCE = "q-meieriene"
EXTRA = os.path.join(ROOT, "data", "raw", SOURCE, "_extra_urls.json")


def add_extra(urls):
    cur = set(json.load(open(EXTRA, encoding="utf-8"))) if os.path.exists(EXTRA) else set()
    cur |= set(urls)
    json.dump(sorted(cur), open(EXTRA, "w", encoding="utf-8"))


def discover(cl, log):
    t = cl.get("https://www.q-meieriene.no/sitemap.xml")
    urls = set(l for l in re.findall(r"<loc>(.*?)</loc>", t) if "/produkter/" in l)
    if os.path.exists(EXTRA):
        urls |= set(json.load(open(EXTRA, encoding="utf-8")))
    return sorted(urls)


def strip_html(h):
    return re.sub(r"\s+", " ", BeautifulSoup(h or "", "lxml").get_text(" ", strip=True))


def scrape(cl, url):
    html = cl.get(url)
    if not html:
        return None
    props = None
    for m in re.finditer(r'<script data-react4xp-app-name[^>]*type="application/json">(.*?)</script>', html, re.S):
        if '"nutritionFacts"' in m.group(1):
            props = json.loads(m.group(1))["props"]
            break
    if not props:
        for m in re.finditer(r'<script data-react4xp-app-name[^>]*type="application/json">(.*?)</script>', html, re.S):
            if "product-category" in m.group(1)[:200]:
                prods = json.loads(m.group(1))["props"].get("products") or []
                add_extra([p["href"] for p in prods if p.get("href", "").startswith("https://www.q-meieriene.no/produkter/")])
                cl.log(f"category page {url}: {len(prods)} product links queued")
                return None
        return {"name": BeautifulSoup(html, "lxml").title.get_text(strip=True) if "<title>" in html else url,
                "brand": "Q-Meieriene", "ean": None, "nutrition": None, "nutrition_per100": None,
                "nutrition_flag": "no_product_data_on_page"}
    tables = []
    for nf in props.get("nutritionFacts") or []:
        rows = [(r["text"], r["value"]) for r in nf.get("rows", []) if r.get("value")]
        tables.append(make_table(nf.get("title", ""), rows))
    pk = props.get("additionalPackaging") or {}
    packs = []
    for grp in ("inStore", "largeHouseholds"):
        for p in (pk.get(grp) or {}).get("packagingOptions", []):
            packs.append({"group": grp, "size": p.get("volume"), "barcode": p.get("barcode") or None})
    sizes = [s.get("title") for s in props.get("sectionStores", []) if s.get("title")]
    eans = [norm_ean(p["barcode"]) for p in packs if norm_ean(p["barcode"])]
    rec = {
        "name": props.get("title"),
        "brand": "Q-Meieriene",
        "ean": eans[0] if eans else None,
        "eans_all": eans,
        "pack_size_raw": ", ".join(sizes) or (packs[0]["size"] if packs else None),
        "packagings": packs,
        "description": strip_html(props.get("intro")),
        "ingredients": strip_html(props.get("ingredients")),
        "allergens_contained": [a.get("title") for a in props.get("allergens", []) if a.get("title")],
        "traces_of": [a.get("title") if isinstance(a, dict) else a for a in props.get("tracesOf", [])],
        "nutrition": {"tables": tables} if tables else None,
        "nutrition_per100": per100_from_tables(tables) if tables else None,
        "nutrition_flag": None if tables else "no_nutrition_on_page",
    }
    return rec


if __name__ == "__main__":
    run_main(SOURCE, discover, scrape, limit=int(sys.argv[1]) if len(sys.argv) > 1 else None)
