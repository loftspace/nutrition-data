"""Shared helpers for the uk-us-eu brand scrapers (second pass, 2026-10-16).

Output record shape follows data/raw/bulk and data/raw/myprotein:
  nutrition = {title, serving_label, serving_size{raw,value,unit}, per_100{key:{raw,value,unit,label[,less_than]}, energy_kj/energy_kcal: float},
               per_serving{...}, raw_columns, raw_rows}
Rules: see ../README.md (robots, 1 req/s/host, honest UA, no bypass, no images).
"""
import json
import os
import re
import sys
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import Client, Logger, Blocked, append, load_done, out_paths, today, ROOT  # noqa: E402,F401

EN = {"Accept-Language": "en-GB,en;q=0.8"}


def tonum(s):
    s = s.replace("\xa0", "").replace(" ", "")
    if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", s):  # US thousands separator
        s = s.replace(",", "")
    return float(s.replace(",", "."))


_AMT = re.compile(r"(<|&lt;|less than)?\s*(\d+(?:[.,]\d+)?|[.,]\d+)\s*(kj|kcal|mg|µg|μg|mcg|ug|g|ml|iu|ie|%)?", re.I)


def parse_value(raw):
    raw = (raw or "").replace("\xa0", " ").strip()
    if not raw or raw in ("-", "–", "—", "*", "**", "n/a", "N/A"):
        return None
    m = _AMT.search(raw)
    if not m:
        return None
    unit = m.group(3)
    if unit:
        unit = {"kj": "kJ", "μg": "µg", "mcg": "µg", "ug": "µg", "iu": "IU", "ie": "IU"}.get(unit.lower(), unit.lower())
    d = {"raw": raw, "value": tonum(m.group(2)), "unit": unit}
    if m.group(1):
        d["less_than"] = True
    return d


def parse_energy(raw):
    out = {}
    raw = (raw or "").replace("\xa0", " ")
    for m in re.finditer(r"(\d+(?:[ ,.]\d+)?)\s*(kJ|kcal|Cal\b)", raw, re.I):
        k = "kcal" if m.group(2).lower() in ("kcal", "cal") else "kj"
        out[k] = tonum(m.group(1))
    if not out:
        m = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*", raw)
        if m:
            out["_bare"] = tonum(m.group(1))
    return out


CANON = [
    (r"^(energy|energi|calories|kalorier|energie|kcal)", "energy"),
    (r"(saturat|mettet|mättat|gesättigt)", "saturated_fat"),
    (r"(polyol|sugar alcohol|sukkeralkohol|zuckeralkohol)", "polyols"),
    (r"(mono-?unsat|enumettet|einfach ungesättigt)", "monounsaturated_fat"),
    (r"(poly-?unsat|flerumettet|mehrfach ungesättigt)", "polyunsaturated_fat"),
    (r"trans", "trans_fat"),
    (r"^(total )?(fat|fett|fedt)$", "fat"),
    (r"(added sugar|tilsatt)", "added_sugars"),
    (r"(sugar|sukker|socker|zucker)", "sugars"),
    (r"^(total )?(carbohydrate|carbs|karbohydrat|kolhydrat|kohlenhydrate)", "carbs"),
    (r"(fibre|fiber|kostfiber|ballaststoffe)", "fibre"),
    (r"^protein|^eiweiß|^eiweiss", "protein"),
    (r"^salt$|^salz$", "salt"),
    (r"^(sodium|natrium)", "sodium"),
    (r"cholesterol", "cholesterol"),
]


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def canon(label):
    l = re.sub(r"^(of which|hvorav|varav|davon|incl\.?|includes?)\s*[:\-]?\s*", "", label.lower().strip(" -–:•*"))
    l = re.sub(r"\s+", " ", l).strip(" -–:•*")
    for rx, k in CANON:
        if re.search(rx, l):
            return k
    return "x_" + slug(l)


def _is_basis_header(c):
    return bool(re.search(r"\b\d+(?:[.,]\d+)?\s*(g|ml|kg|l)\b|per\b|serving|portion|bar\b|scoop|pro \d|täglich|daily|dose|capsule|tablet|stk|pack", c, re.I))


def col_kind(c):
    c = c.lower()
    if re.search(r"%|\bri\b|\bnrv\b|\bdri\b|\brdi\b|\bdv\b|reference intake|daily value|\bris\b", c) and not re.search(r"\d+\s*(g|ml)\b", c):
        return "ri"
    if re.search(r"(per|pro|/)?\s*100\s*(g|ml)\b|^100\s*(g|ml)", c):
        return "per100"
    return "serving"


def parse_rows(rows, label=None, title=None):
    """rows: list of cell lists (first cell = nutrient label). Returns the nutrition dict, or None."""
    rows = [[re.sub(r"\s+", " ", (c or "").replace("\xa0", " ")).strip() for c in r] for r in rows]
    rows = [r for r in rows if any(r)]
    if len(rows) < 2:
        return None
    # header row: first row where the cells after the first look like basis headers and hold no nutrient numbers with units mixed in
    hdr = None
    for i, r in enumerate(rows[:4]):
        cells = [c for c in r[1:] if c]
        if cells and all(_is_basis_header(c) or col_kind(c) == "ri" for c in cells) and not any(re.search(r"\d\s*(mg|µg|kcal|kj)", c, re.I) for c in cells):
            hdr = i
            break
    if hdr is None:
        # US/single-column panel without header: treat as per serving, header may sit in the label cell
        hdr_cells = ["per serving"]
        body = rows
        first_hdr = None
    else:
        first_hdr = rows[hdr][0]
        hdr_cells = rows[hdr][1:]
        body = rows[hdr + 1:]
    if hdr is not None and first_hdr and re.match(r"amount per", first_hdr, re.I) and not any(col_kind(c) != "ri" for c in hdr_cells):
        hdr_cells = [first_hdr] + hdr_cells  # US panel: header lacks a cell for the nutrient label column
    kinds = [col_kind(c) for c in hdr_cells]
    i100 = next((i for i, k in enumerate(kinds) if k == "per100"), None)
    iserv = next((i for i, k in enumerate(kinds) if k == "serving"), None)
    per100, perserv, raw_rows, section = {}, {}, [], None
    for r in body:
        raw_rows.append(r)
        if len(r) == 1 or all(not v for v in r[1:]):
            section = r[0]
            continue
        lab, vals = r[0], r[1:]
        if hdr is None:
            vals = vals[:1]
        k = canon(lab)
        for idx, tgt in ((i100, per100), (iserv, perserv)):
            if idx is None or idx >= len(vals) or not vals[idx]:
                continue
            if k == "energy":
                e = parse_energy(vals[idx])
                if "_bare" in e:
                    b = e.pop("_bare")
                    if re.search(r"kcal|calor", lab, re.I):
                        e["kcal"] = b
                    elif re.search(r"kj", lab, re.I):
                        e["kj"] = b
                if "kj" in e:
                    tgt["energy_kj"] = e["kj"]
                if "kcal" in e:
                    tgt["energy_kcal"] = e["kcal"]
                continue
            pv = parse_value(vals[idx])
            if pv:
                pv["label"] = lab
                if pv["unit"] is None and k in ("fat", "saturated_fat", "monounsaturated_fat", "polyunsaturated_fat", "trans_fat", "carbs", "sugars", "added_sugars", "polyols", "fibre", "protein", "salt"):
                    pv["unit"] = "g"
                    pv["unit_inferred"] = True
                if section:
                    pv["section"] = section
                key = k
                n = 2
                while key in tgt:
                    key = f"{k}_{n}"
                    n += 1
                tgt[key] = pv
    if not per100 and not perserv:
        return None
    ser_label = hdr_cells[iserv] if iserv is not None else None
    ser = None
    if ser_label:
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*(g|ml)\b", ser_label, re.I)
        if m:
            ser = {"raw": m.group(0), "value": tonum(m.group(1)), "unit": m.group(2).lower()}
    return {"flavour_label": label, "title": title or first_hdr, "serving_label": ser_label, "serving_size": ser,
            "per_100": per100, "per_serving": perserv, "raw_columns": hdr_cells, "raw_rows": raw_rows}


def table_rows(tb):
    rows = []
    for tr in tb.find_all("tr"):
        if tr.find("table"):
            continue
        rows.append([c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])])
    return rows


def text_panel(text):
    """US text panel 'Serving size: 1 bar (60g). Calories: 180. Total Fat: 7g 9% Daily Value*. ...' -> nutrition dict (per serving)."""
    t = re.sub(r"\s+", " ", text)
    ss = re.search(r"serving size:?\s*(.{1,80}?)\s*(?:\.|amount per|servings? per|calories)", t, re.I)
    per = {}
    cal = re.search(r"calories:?\s*(\d+(?:[.,]\d+)?)", t, re.I)
    if cal:
        per["energy_kcal"] = tonum(cal.group(1))
    labels = ["Total Fat", "Saturated Fat", "Trans Fat", "Cholesterol", "Sodium", "Total Carbohydrate", "Dietary Fiber", "Total Sugars",
              "Includes [\\d.]*\\s*g? ?Added Sugars", "Added Sugars", "Sugar Alcohols", "Protein", "Vitamin D", "Calcium", "Iron", "Potassium"]
    for lab in labels:
        m = re.search(rf"(?<![A-Za-z]){lab}:?\s*(<?\s*\d+(?:[.,]\d+)?\s*(?:mg|µg|mcg|g)\b)", t, re.I)
        if m:
            pv = parse_value(m.group(1))
            if pv:
                pv["label"] = lab.split("[")[0].strip() if "[" not in lab else "Added Sugars"
                k = canon(pv["label"])
                per.setdefault(k, pv)
    if not per:
        return None
    ser = None
    if ss:
        g = re.search(r"(\d+(?:[.,]\d+)?)\s*(g|ml)\b", ss.group(1), re.I)
        if g:
            ser = {"raw": g.group(0), "value": tonum(g.group(1)), "unit": g.group(2).lower()}
    return {"flavour_label": None, "title": "Nutrition Facts", "serving_label": ss.group(1) if ss else None, "serving_size": ser,
            "per_100": {}, "per_serving": per, "raw_columns": ["per serving"], "raw_rows": [[t[:1500]]]}


def jsonld(html):
    out = []
    for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            j = json.loads(m.group(1))
        except Exception:
            continue
        items = j if isinstance(j, list) else (j.get("@graph") or [j])
        for g in items:
            if isinstance(g, dict):
                out.append(g)
    return out


FOOD_RX = re.compile(r"(protein|whey|casein|isolate|creatine|bcaa|eaa|amino|pre-?workout|pump|mass|gainer|bar\b|bars\b|cookie|crisp|chips|wafer|spread|shake|drink|rtd|collagen|vitamin|omega|multi|mineral|magnesium|zinc|caffeine|electrolyte|hydrat|greens|fibre|fiber|probiotic|oat|pudding|snack|candy|gummies|capsule|tablet|powder|supplement|energy|clear|recovery|glutamine|carnitine|ashwagandha|nootropic|focus|sleep|testosterone|fat burn|thermo|cereal|granola|syrup|sauce|peanut|nut|butter|chocolate|candy)", re.I)
NONFOOD_RX = re.compile(r"(tee\b|t-shirt|hoodie|hoody|jogger|shorts|legging|hat\b|cap\b|beanie|crew|sweat|jacket|bag\b|backpack|shaker|bottle|gift ?card|apparel|merch|sticker|towel|gloves|strap|belt|sleeve|socks|tank|vest|bra\b|book\b|e-?book|plan\b|guide|pill ?box|scoop|mug|cup\b|blender|hoody)", re.I)


def is_foodish(title, ptype="", tags=""):
    s = f"{title} {ptype} {tags}"
    if NONFOOD_RX.search(title or "") and not re.search(r"(protein|whey|bar)", title or "", re.I):
        return False
    if re.search(r"(apparel|accessor|merch|gift card|clothing|gear|hats?|bottoms|tops|shaker)", ptype or "", re.I):
        return False
    return True


def strip_html(h):
    return re.sub(r"\s+", " ", BeautifulSoup(h or "", "lxml").get_text(" ", strip=True)).strip()


def finish(rec_base, nut, flags):
    rec = dict(rec_base)
    rec["nutrition"] = nut
    rec["nutrition_flags"] = flags
    return rec


NUTR_LAB = re.compile(r"(protein|energy|calories|carbohydrate|kohlenhydrat|eiwei|brennwert|energi|fat|fett)", re.I)
