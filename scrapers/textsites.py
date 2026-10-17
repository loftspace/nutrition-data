"""synnove.no, kavli.no, hennig-olsen.no: product pages whose nutrition block is label/value text after a 'Næringsinnhold' heading."""
import sys, re
from bs4 import BeautifulSoup
from common import *

SITES = {
    "synnove": dict(brand="Synnove", sm="https://www.synnove.no/sitemap.xml", pat=r"synnove\.no/produkt/[^/]+/?$"),
    "kavli": dict(brand="Kavli", sm="https://www.kavli.no/sitemap.xml", pat=r"kavli\.no/produkter/[^/]+/?$"),
    "hennig-olsen": dict(brand="Hennig-Olsen", sm="https://www.hennig-olsen.no/sitemap.xml", pat=r"hennig-olsen\.no/(iskrem|iskremarkiv)/[^/]+/[^/]+/?$"),
}
STOP = ("ingredienser", "allergener", "har du prøvd", "vareinformasjon", "utsalgssteder", "butikker", "finn produktet", "relaterte", "oppskrifter", "tilgjengelige", "hva syns", "næringsinnhold")
VALUE = re.compile(r"^(<|>|ca\.?\s*)?\s*(\d|[–-]\s*(g|mg)?$)")


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def discover_for(key):
    cfg = SITES[key]

    def discover(cl, log):
        t = cl.get(cfg["sm"]) or ""
        us = re.findall(r"<loc>(.*?)</loc>", t)
        out = sorted(set(u for u in us if re.search(cfg["pat"], u)))
        return out
    return discover


def nutrition_rows(lines):
    """Return (header, rows) for the first 'Næringsinnhold' block that holds label/value pairs."""
    for i, l in enumerate(lines):
        if l.lower().startswith("næringsinnhold"):
            hdr = [l]
            j = i + 1
            # header continuation: 'per 100g', 'Pr. 100 g', 'Vis mer/mindre'
            while j < len(lines) and (re.search(r"(per|pr\.?)\s*100|vis mer|vis mindre|porsjon", lines[j], re.I)):
                if not re.search(r"vis mer|vis mindre", lines[j], re.I):
                    hdr.append(lines[j])
                j += 1
            rows = []
            k = j
            while k + 1 < len(lines):
                a, b = lines[k], lines[k + 1]
                if a.lower().startswith(STOP) and not VALUE.match(a):
                    break
                if VALUE.match(a):  # stray value without label
                    k += 1
                    continue
                if VALUE.match(b):
                    if not re.search(r"epd|varenummer|gtin|artikkel", a, re.I):
                        rows.append((a, b))
                    k += 2
                else:
                    break
            if rows:
                return " ".join(hdr), rows
    return None, []


def scrape_for(key):
    cfg = SITES[key]

    def scrape(cl, url):
        html = cl.get(url)
        if not html:
            return None
        s = BeautifulSoup(html, "lxml")
        h1 = s.find("h1")
        name = clean(h1.get_text(" ", strip=True)) if h1 else None
        for x in s(["script", "style", "svg", "noscript"]):
            x.decompose()
        lines = [clean(l) for l in s.get_text("\n").split("\n") if clean(l)]
        hdr, rows = nutrition_rows(lines)
        tables = []
        if rows:
            tb = make_table(hdr, rows)
            if tb["basis"] == "unknown":
                tb["basis"] = "per_100"
            tables.append(tb)

        def after(label):
            for i, l in enumerate(lines):
                if l.rstrip(":").strip().lower() == label.lower():
                    j = i + 1
                    if j < len(lines) and lines[j] == ":":
                        j += 1
                    return lines[j] if j < len(lines) else None
            return None

        ing = None
        for i, l in enumerate(lines):
            if l.lower() == "ingredienser" and i + 1 < len(lines):
                buf = []
                j = i + 1
                while j < len(lines) and len(buf) < 12 and not lines[j].lower().startswith(("allergener", "næringsinnhold", "merk at", "naturlig laktose")):
                    buf.append(lines[j])
                    j += 1
                ing = clean(re.sub(r"Vis mer|Vis mindre", "", " ".join(buf)))
                break
        gtin = norm_ean(after("GTIN"))
        allerg = after("Inneholder")
        traces = after("Kan inneholde spor av")
        rec = {
            "name": name, "brand": cfg["brand"], "ean": gtin,
            "pack_size_raw": pack_size(name),
            "ingredients": ing,
            "allergens_raw": allerg, "traces_raw": traces,
            "archived": "/iskremarkiv/" in url or None,
            "nutrition": {"tables": tables} if tables else None,
            "nutrition_per100": per100_from_tables(tables) if tables else None,
            "nutrition_flag": None if tables else "no_nutrition_on_page",
        }
        if not gtin:
            rec["ean_note"] = f"{key} page shows no GTIN"
        return rec
    return scrape


if __name__ == "__main__":
    key = sys.argv[1]
    run_main(key, discover_for(key), scrape_for(key), limit=int(sys.argv[2]) if len(sys.argv) > 2 else None)
