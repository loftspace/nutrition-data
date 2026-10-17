import sys, re
from bs4 import BeautifulSoup
from common import *

SOURCE = "firstprice"
SITEMAPS = {"firstprice": "https://firstprice.no/sitemap/products.xml", "eldorado": "https://eldorado.no/sitemap/products.xml"}


def discover(cl, log):
    t = cl.get(SITEMAPS[SOURCE]) or ""
    return sorted(set(re.findall(r"<loc>(.*?)</loc>", t)))


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def scrape(cl, url):
    html = cl.get(url)
    if not html:
        return None
    s = BeautifulSoup(html, "lxml")
    hs = [clean(h.get_text(" ", strip=True)) for h in s.find_all(["h1", "h2"])]
    cand = [h for h in hs if h and h.lower() not in ("first price", "eldorado", "finn våre produkter i din butikk")]
    name = cand[0] if cand else None
    # nutrition rows: <td name>Label:</td><td amount>value unit</td>
    rows = []
    for tr in s.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) == 2:
            a = clean(tds[0].get_text(" ", strip=True)).rstrip(":").strip()
            b = clean(tds[1].get_text(" ", strip=True))
            if a and b:
                rows.append((a, b))
    for x in s(["script", "style", "svg", "noscript"]):
        x.decompose()
    lines = [clean(l) for l in s.get_text("\n").split("\n") if clean(l)]

    def after(label):
        for i, l in enumerate(lines):
            if l.rstrip(":") == label:
                j = i + 1
                if j < len(lines) and lines[j] == ":":
                    j += 1
                return lines[j] if j < len(lines) else None
        return None

    ean = norm_ean(after("GTIN")) or norm_ean(url.rsplit("-", 1)[-1])
    ingr = None
    for i, l in enumerate(lines):
        if l.startswith("Ingredienser"):
            k = i + 1
            buf = []
            while k < len(lines) and not lines[k].startswith("Opprinnelsesland") and k < i + 12:
                buf.append(lines[k])
                k += 1
            ingr = clean(" ".join(buf))
            break
    allerg = None
    if "Allergener" in lines:
        i = lines.index("Allergener")
        buf = []
        k = i + 1
        while k < len(lines) and lines[k] != "Produktinformasjon":
            buf.append(lines[k])
            k += 1
        allerg = buf
    # description is line after name (second occurrence)
    desc = None
    if name and name in lines:
        i = lines.index(name)
        for l in lines[i + 1:i + 4]:
            if l != name and l not in ("First Price",):
                desc = l
                break
    tables = []
    if rows:
        tb = make_table("Næringsinnhold per 100 gram", rows)
        tb["basis"] = "per_100"
        tables.append(tb)
    rec = {
        "name": name, "brand": after("Merke") or "First Price", "supplier": after("Leverandør"),
        "ean": ean, "origin_country": after("Opprinnelsesland"),
        "pack_size_raw": pack_size(name),
        "description": desc, "ingredients": ingr, "allergens_contained": allerg,
        "nutrition": {"tables": tables} if tables else None,
        "nutrition_per100": per100_from_tables(tables) if tables else None,
        "nutrition_flag": None if tables else "no_nutrition_on_page",
    }
    return rec


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in SITEMAPS:
        SOURCE = sys.argv.pop(1)
    run_main(SOURCE, discover, scrape, limit=int(sys.argv[1]) if len(sys.argv) > 1 else None)
