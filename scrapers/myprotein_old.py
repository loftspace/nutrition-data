"""Parser for the OLD myprotein.no page template (2015-2021 snapshots, /<category>/<slug>/<id>.html): server-rendered
'nutritional-info-table' (Per 100g / Per Serving / *RI) plus ingredients tab. Used only for Internet Archive snapshots."""
import re, sys, os, datetime
from bs4 import BeautifulSoup
sys.path.insert(0, os.path.dirname(__file__))
import nogen as N

clean = N.clean


def _fix_rows(rows):
    out = []
    for r in rows:
        # sub-rows like ['', 'of which saturates', '1.7 g', '0.4 g', '2%'] carry an empty first cell
        if len(r) > 2 and not r[0] and re.match(r"[A-Za-z]", r[1]) and not re.match(r"per\b", r[1], re.I):
            r = r[1:]
        out.append(r)
    return out


def parse_colon_prose(text):
    """'Per Bar (60g): Energy: 1013KJ Energy: 242kcal Fat: 8.0g Of which saturates: 3.2g Carbohydrate: 23.0g ... Protein: 22.0g Salt: 0.05g'"""
    m = re.search(r"Per\s+([^:]{2,30}?):\s*(Energy:.{20,700})", text)
    if not m:
        return None
    basis, body = m.group(1).strip(), m.group(2)
    pairs = re.findall(r"([A-Za-z][A-Za-z ]{1,40}?):\s*([<]?\d[\d.,]*\s*(?:KJ|kJ|kj|kcal|Kcal|g|mg|µg|mcg))(?![A-Za-z])", body)
    rows = [["Nutrition", "Per " + basis]]
    en = []
    for lab, val in pairs:
        if lab.strip().lower() == "energy":
            en.append(val)
            continue
        if en:
            rows.append(["Energy", " / ".join(en)]); en = []
        rows.append([lab.strip(), val])
    if en:
        rows.append(["Energy", " / ".join(en)])
    return N.structure_rows(rows) if len(rows) > 4 else None


def parse_old(url, body):
    h = body.decode("utf-8", "replace") if isinstance(body, bytes) else body
    s = BeautifulSoup(h, "lxml")
    h1 = s.find("h1")
    if not h1:
        return []
    name = clean(h1.get_text(" ", strip=True))
    if not name or re.search(r"^(404|siden|page not found)", name, re.I):
        return []
    tabs = []
    for t in s.find_all("table", class_="nutritional-info-table"):
        st = N.structure_rows(_fix_rows(N.table_rows(t)))
        if st and (st["per_100"] or st["per_serving"]):
            tabs.append(st)
    if not tabs:
        for t in s.find_all("table"):
            rows = _fix_rows(N.table_rows(t))
            flat = " ".join(" ".join(r) for r in rows)
            if re.search(r"energi|energy|protein|kcal", flat, re.I):
                st = N.structure_rows(rows)
                if st and (st["per_100"] or st["per_serving"]):
                    tabs.append(st)
    nut = N.merge_nutrition(tabs)
    panel = s.select_one(".js-prodInfo-nutrition")
    serving_text = clean(panel.get_text(" ", strip=True))[:400] if panel else None
    txt = clean(s.get_text(" ", strip=True))
    if nut is None:
        nut = N.parse_inline_nutrition(txt)
        if nut:
            nut["from_inline_text"] = True
    if nut is None:
        nut = parse_colon_prose(txt)
        if nut:
            nut["from_inline_text"] = True
    ing = None
    ip = s.select_one(".js-prodInfo-ingredients, #prodInfo-ingredients, .prodInfo-ingredients")
    if ip:
        ing = clean(ip.get_text(" ", strip=True))[:2000]
    else:
        m = re.search(r"Ingredienser\s+(.*?)(?=\s+(?:N[æe]ringsinformasjon|Anbefalt|Bruk|Allergen)|$)", txt)
        ing = m.group(1)[:1500] if m else None
    pid = re.search(r"/(\d+)\.html", url)
    flags = ["flavour_nutrition_shared_assumed"]
    if nut is None:
        flags.append("no_nutrition_table")
    elif not nut["per_100"]:
        flags.append("per_100_missing_per_serving_only")
    desc = s.find("meta", attrs={"name": "description"})
    pack = re.search(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l|kapsler|tabletter)\b", name, re.I)
    return [{
        "record_type": "page", "source": "myprotein-discontinued", "source_url": url, "page_url": url, "product_group_id": pid.group(1) if pid else None,
        "name": name, "brand": "Myprotein", "sku": None, "ean": None, "description": clean(desc.get("content")) if desc else None,
        "ingredients": ing, "serving_info_text": serving_text, "nutrition": nut, "nutrition_flags": flags,
        "pack": {"size_text": pack.group(0)} if pack else None, "template": "myprotein_old_2016",
    }]
