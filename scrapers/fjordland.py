import sys, json, re
from bs4 import BeautifulSoup
from common import *

SOURCE = "fjordland"


def discover(cl, log):
    t = cl.get("https://www.fjordland.no/sitemap.xml")
    return sorted(set(l for l in re.findall(r"<loc>(.*?)</loc>", t) if re.search(r"/(fjordland|yoplait|kos)/produkter/", l)))


def rsc_text(html):
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', html, re.S)
    out = []
    for c in chunks:
        try:
            out.append(json.loads('"' + c + '"'))
        except Exception:
            pass
    return "".join(out)


TD = r'\["\$","td",null,\{[^{}]*?"children":"((?:[^"\x5c]|\x5c.)*)"\}\]'


def section(rsc, title):
    i = rsc.find('"title":"%s"' % title)
    return rsc[i:i + 12000] if i >= 0 else ""


def scrape(cl, url):
    html = cl.get(url)
    if not html:
        return None
    rsc = rsc_text(html)
    s = BeautifulSoup(html, "lxml")
    h1 = s.find("h1")
    name = h1.get_text(" ", strip=True) if h1 else None
    brand = url.split("/")[3].capitalize()
    # pack size: text next to h1 e.g. "150 | g"
    text_lines = [l.strip() for l in s.get_text("\n").split("\n") if l.strip() and l.strip() != "\u200c"]
    pack = None
    if name and name in text_lines:
        k = text_lines.index(name)
        nxt = text_lines[k + 1:k + 4]
        if nxt and re.fullmatch(r"[\d.,]+", nxt[0]) and len(nxt) > 1:
            pack = f"{nxt[0]} {nxt[1]}"
    cat = None
    # nutrition
    tables = []
    sec = section(rsc, "Næringsinnhold")
    if sec:
        end = sec.find("</") if False else len(sec)
        headers = re.findall(r'\["\$","th",null,\{[^{}]*?"children":"((?:[^"\x5c]|\x5c.)*)"\}\]', sec)
        rows = []
        for tr in re.finditer(r'\["\$","tr","[^"]*",\{"children":\[(.*?)\]\}\]', sec):
            tds = [json.loads('"' + x + '"') for x in re.findall(TD, tr.group(1))]
            if len(tds) >= 2:
                rows.append((tds[0].strip(), tds[1].strip()))
        if rows:
            tables.append(make_table(headers[1] if len(headers) > 1 else "100g vare", rows))
            tables[0]["basis"] = "per_100"
    ing = None
    m = re.search(r'"title":"Ingredienser".*?"__html":"((?:[^"\x5c]|\x5c.)*)"', rsc[:], re.S)
    if m:
        ing = BeautifulSoup(json.loads('"' + m.group(1) + '"'), "lxml").get_text(" ", strip=True)
    all_sec = section(rsc, "Allergener")
    allergens = []
    if all_sec:
        allergens = re.findall(r'"children":" ?","([a-zæøå ]+)"\]', all_sec)[:0]
        allergens = [x.strip() for x in re.findall(r'\]\}\]," ","([^"]+)"\]\}\]', all_sec)]
    flags = [h.get_text(" ", strip=True) for h in s.find_all("h4")]
    rec = {
        "name": name, "brand": brand if brand != "Kos" else "KOS",
        "ean": None, "pack_size_raw": pack or pack_size(name),
        "ingredients": ing, "allergens_contained": allergens,
        "claims": [f for f in flags if f and f.lower() not in ("plast",)],
        "nutrition": {"tables": tables} if tables else None,
        "nutrition_per100": per100_from_tables(tables) if tables else None,
        "nutrition_flag": None if tables else "no_nutrition_on_page",
        "ean_note": "fjordland.no does not publish EAN",
    }
    return rec


if __name__ == "__main__":
    run_main(SOURCE, discover, scrape, limit=int(sys.argv[1]) if len(sys.argv) > 1 else None)
