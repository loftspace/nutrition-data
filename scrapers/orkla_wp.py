"""Orkla WordPress brand sites: grandiosa.no, nidar.no, toro.no (robots-allowed, sitemaps)."""
import sys, re, json
from bs4 import BeautifulSoup
from common import *

SITES = {
    "grandiosa": dict(brand="Grandiosa", sitemaps=["https://www.grandiosa.no/product-sitemap.xml"], pat=r"grandiosa\.no/produkter/[^/]+/"),
    "nidar": dict(brand="Nidar", sitemaps=["https://www.nidar.no/product-sitemap.xml"], pat=r"nidar\.no/produkt/[^/]+/"),
    "saetre": dict(brand="Saetre", sitemaps=["https://www.saetre.no/product-sitemap.xml"], pat=r"saetre\.no/product/[^/]+/"),
    "toro": dict(brand="Toro", sitemaps=["https://www.toro.no/products-sitemap.xml"], pat=r"toro\.no/produkter/[^/]+/"),
}
DOT = {"reddot": "contains", "orangedot": "may_contain", "greendot": "free_from"}


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def discover_for(key):
    cfg = SITES[key]

    def discover(cl, log):
        out = []
        for sm in cfg["sitemaps"]:
            t = cl.get(sm) or ""
            out += [l for l in re.findall(r"<loc>(.*?)</loc>", t) if re.search(cfg["pat"], l)]
        return sorted(set(out))
    return discover


def eael_tables(s):
    tables = []
    for tb in s.find_all("table"):
        rows = [[clean(c.get_text(" ", strip=True)) for c in tr.find_all(["td", "th"])] for tr in tb.find_all("tr")]
        rows = [r for r in rows if any(r)]
        if not rows:
            continue
        flat = " ".join(" ".join(r) for r in rows).lower()
        if rows[0] and rows[0][0] == "" and len(rows[0]) >= 2 and any(k in flat for k in ("energi", "kcal")) and "allergen" not in flat[:40]:
            heads = rows[0][1:]
            body = [r for r in rows[1:] if len(r) >= 2 and r[0]]
            for ci, h in enumerate(heads, start=1):
                rr = [(r[0], r[ci]) for r in body if ci < len(r) and r[ci]]
                tables.append(make_table(h, rr))
    return tables


def toro_tables(s):
    tables = []
    sec = s.find("section", class_="nutrients")
    if not sec:
        return tables
    for content in sec.find_all("div", class_="content"):
        h3 = content.find("h3")
        title = clean(h3.get_text(" ", strip=True)) if h3 else ""
        labels = [clean(sp.get_text(" ", strip=True)) for sp in content.select(".nutrient .contents span")]
        portion = content.select_one(".quantity .portion")
        per100 = content.select_one(".quantity .per100")
        if per100:
            vals = [clean(sp.get_text(" ", strip=True)) for sp in per100.find_all("span")]
            rr = [(a, b) for a, b in zip(labels, vals) if b]
            t = make_table((title + " per 100 g").strip(), rr)
            t["basis"] = "prepared_per_100" if "tilbred" in title.lower() else "per_100"
            t["state"] = title or None
            tables.append(t)
        if portion:
            vals = [clean(sp.get_text(" ", strip=True)) for sp in portion.find_all("span")]
            st = portion.find("style")
            hdr = re.search(r"content:\s*'([^']*)'", st.get_text()) if st else None
            rr = [(a, b) for a, b in zip(labels, vals) if b]
            t = make_table(((title + " ") if title else "") + (hdr.group(1) if hdr else "per portion"), rr)
            t["basis"] = "per_serving"
            t["state"] = title or None
            tables.append(t)
    return tables


def ingredients(s):
    for a in s.select("a.elementor-toggle-title"):
        if clean(a.get_text()).lower().startswith("ingredienser"):
            h3 = a.find_parent("h3")
            nxt = h3.find_next_sibling("div") if h3 else None
            if nxt:
                return clean(nxt.get_text(" ", strip=True))
    sec = s.find("section", class_=re.compile("ingredients"))
    if sec:
        p = sec.find("p")
        return clean(p.get_text(" ", strip=True)) if p else None
    for h in s.find_all(["h2", "h3"]):
        if clean(h.get_text()).lower() == "ingredienser":
            p = h.find_next(["p", "div"])
            if p:
                return clean(p.get_text(" ", strip=True))
    return None


def allergens(s, key):
    res = {}
    if key == "toro":
        sec = s.find("section", class_="allergens")
        if sec:
            lab = [clean(li.get_text(" ", strip=True)) for li in sec.select(".label li")]
            cont = sec.select(".containment ul > li")
            m = {"FREE_FROM": "free_from", "CONTAINS": "contains", "TRACES": "may_contain", "MAY_CONTAIN": "may_contain"}
            for l, c in zip(lab, cont):
                sp = c.find("span")
                if sp and sp.get("class"):
                    res[l] = m.get(sp["class"][0], sp["class"][0])
        return res or None
    for tb in s.find_all("table"):
        for tr in tb.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) == 4:
                d = tds[1].find("p")
                if d and d.get("class") and d["class"][0] in DOT:
                    res[clean(tds[0].get_text(" ", strip=True))] = DOT[d["class"][0]]
    return res or None


def scrape_for(key):
    cfg = SITES[key]

    def scrape(cl, url):
        html = cl.get(url)
        if not html:
            return None
        s = BeautifulSoup(html, "lxml")
        h1 = s.find("h1")
        title = clean(h1.get_text(" ", strip=True)) if h1 else None
        if not title:
            og = s.find("meta", property="og:title")
            title = clean(og["content"]).split(" - ")[0] if og else None
        text_lines = [clean(l) for l in s.get_text("\n").split("\n") if clean(l)]
        pack = None
        if title and title in text_lines:
            k = text_lines.index(title)
            for l in text_lines[k + 1:k + 4]:
                if re.fullmatch(r"\d+(?:[.,]\d+)?\s*(g|kg|ml|cl|dl|l|stk)", l, re.I):
                    pack = l
                    break
        if key == "toro":
            tables = toro_tables(s)
            pk = s.find(string=re.compile(r"^\s*\d+(?:[.,]\d+)?\s*(g|kg|ml|l)\s*$", re.I))
            pack = pack or (clean(pk) if pk else None)
        else:
            tables = eael_tables(s)
        rec = {
            "name": title, "brand": cfg["brand"], "ean": None,
            "pack_size_raw": pack or pack_size(title),
            "ingredients": ingredients(s),
            "allergens_status": allergens(s, key),
            "nutrition": {"tables": tables} if tables else None,
            "nutrition_per100": per100_from_tables(tables) if tables else None,
            "nutrition_flag": None if tables else "no_nutrition_on_page",
            "ean_note": f"{key}.no does not publish EAN",
        }
        full = [t for t in tables if t["values"]]
        if tables and not full:
            rec["nutrition_flag"] = "nutrition_table_empty"
            rec["nutrition_per100"] = None
        elif key == "toro" and full:
            asold = [t for t in full if t["basis"] == "per_100"]
            prep = [t for t in full if t["basis"] == "prepared_per_100"]
            if asold:
                rec["nutrition_per100"] = asold[0]["values"]
            elif prep:
                rec["nutrition_per100"] = prep[0]["values"]
                rec["per100_is_prepared"] = True
            else:
                rec["nutrition_per100"] = None
        return rec
    return scrape


if __name__ == "__main__":
    key = sys.argv[1]
    run_main(key, discover_for(key), scrape_for(key), limit=int(sys.argv[2]) if len(sys.argv) > 2 else None)
