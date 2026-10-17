import sys, re
from bs4 import BeautifulSoup
from common import *

SOURCE = "mills"


def discover(cl, log):
    t = cl.get("https://mills.no/product-sitemap.xml") or ""
    return sorted(set(l for l in re.findall(r"<loc>(.*?)</loc>", t) if "/produkt/" in l))


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def scrape(cl, url):
    html = cl.get(url)
    if not html:
        return None
    s = BeautifulSoup(html, "lxml")
    h1 = s.find("h1")
    name = clean(h1.get_text(" ", strip=True)) if h1 else None
    if not name and s.title:
        name = clean(s.title.get_text()).rsplit(" - ", 1)[0]
    brand = url.split("/")[3]
    sec = s.find("section", class_="nutrients-section")
    tables = []
    codes = {}
    if sec:
        info = sec.find("p", class_="nutrients-info")
        rows = []
        for it in sec.select(".nutrient-item"):
            sp = it.find_all("span")
            if len(sp) >= 2:
                label = clean(sp[0].get_text(" ", strip=True))
                val = clean(sp[1].get_text(" ", strip=True))
                if val:
                    rows.append((label, val))
                    codes[label] = [c for c in it.get("class", []) if c.isupper() or c.upper() == c and "-" in c][-1:] or None
        if rows:
            tb = make_table(clean(info.get_text()) if info else "100 gram gir", rows)
            if tb["basis"] == "unknown":
                tb["basis"] = "per_100"
            tb["nutrient_codes"] = {k: (v[0] if v else None) for k, v in codes.items()}
            tables.append(tb)
    ing = s.find("p", class_="ingredients-list")
    allg = [clean(x.get_text(" ", strip=True)) for x in s.select(".allergens-section .wp-block-button__link")]
    mt = s.find("meta", attrs={"name": "description"})
    rec = {
        "name": name, "brand": brand, "ean": None,
        "pack_size_raw": pack_size(name),
        "description": clean(mt["content"]) if mt and mt.get("content") else None,
        "ingredients": clean(ing.get_text(" ", strip=True)) if ing else None,
        "allergens_contained": allg,
        "nutrition": {"tables": tables} if tables else None,
        "nutrition_per100": per100_from_tables(tables) if tables else None,
        "nutrition_flag": None if tables else "no_nutrition_on_page",
        "ean_note": "mills.no does not publish EAN",
    }
    return rec


if __name__ == "__main__":
    run_main(SOURCE, discover, scrape, limit=int(sys.argv[1]) if len(sys.argv) > 1 else None)
