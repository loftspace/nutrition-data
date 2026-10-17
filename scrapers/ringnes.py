"""ringnes.no (Carlsberg Norge, drinks). robots.txt asks Crawl-delay 10: Client honours it."""
import sys, re
from bs4 import BeautifulSoup
from common import *

SOURCE = "ringnes"


def discover(cl, log):
    t = cl.get("https://www.ringnes.no/sitemap/") or ""
    us = re.findall(r"<loc>(.*?)</loc>", t)
    # product pages are /produkter/<brand>/<product>/ (depth 2 below /produkter/)
    return sorted(set(u for u in us if re.search(r"/produkter/[^/]+/[^/]+/?$", u)))


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def scrape(cl, url):
    html = cl.get(url)
    if not html:
        return None
    s = BeautifulSoup(html, "lxml")
    h1 = s.find("h1")
    name = clean(h1.get_text(" ", strip=True)) if h1 else None
    if not name:
        og = s.find("meta", property="og:title")
        name = clean(og["content"]).split(" | ")[0] if og and og.get("content") else (clean(s.title.get_text()).split(" | ")[0] if s.title else None)
    mod = s.find(class_="module--product-nutritional")
    tables = []
    if mod:
        hdr = mod.find("h3")
        span = hdr.find("span") if hdr else None
        basis_txt = clean(span.get_text()) if span else "Per 100ml"
        rows = []
        for dt in mod.find_all("dt"):
            dd = dt.find_next_sibling("dd")
            if dd:
                rows.append((clean(dt.get_text(" ", strip=True)), clean(dd.get_text(" ", strip=True))))
        if rows:
            tb = make_table(basis_txt, rows)
            tables.append(tb)
    text = [clean(l) for l in s.get_text("\n").split("\n") if clean(l)]
    cat = None
    if "Kategori:" in text:
        cat = text[text.index("Kategori:") + 1]
    abv = None
    for l in text:
        if re.fullmatch(r"\d+(?:[.,]\d+)?\s*%", l):
            abv = l
            break
    ing = None
    allergen = None
    for i, l in enumerate(text):
        if l == "Ingredienser" and i + 1 < len(text):
            ing = text[i + 1]
            if i + 2 < len(text) and text[i + 2].startswith("Allergener"):
                allergen = text[i + 2]
            break
    rec = {
        "name": name, "brand": url.split("/")[4], "ean": None,
        "category": cat, "abv_raw": abv,
        "pack_size_raw": pack_size(name),
        "ingredients": ing, "allergens_raw": allergen,
        "nutrition": {"tables": tables} if tables else None,
        "nutrition_per100": per100_from_tables(tables) if tables else None,
        "nutrition_basis_note": "per 100 ml" if tables else None,
        "nutrition_flag": None if tables else "no_nutrition_on_page",
        "ean_note": "ringnes.no does not publish EAN",
    }
    return rec


if __name__ == "__main__":
    run_main(SOURCE, discover, scrape, limit=int(sys.argv[1]) if len(sys.argv) > 1 else None)
