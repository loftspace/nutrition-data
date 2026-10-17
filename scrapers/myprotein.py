#!/usr/bin/env python3
"""no.myprotein / www.myprotein.no scraper. Rules: see ../README.md.

Discovery: robots.txt Sitemap -> sitemapindex-product -> sitemap-product-N (product URLs, only food/
supplement categories) plus /c/ list pages from sitemap-list that look like nutrition (product links).
Product pages are server rendered: JSON-LD ProductGroup (variants, gtin13, price, weight, flavour)
and HTML nutrition tables per flavour (Per 100g / per portion), ingredients per flavour.
Output: data/raw/myprotein/products.jsonl: one line per variant (record_type=variant) plus one
line per page (record_type=page) holding all flavour tables. Resume-safe by page URL.
"""
import argparse, json, os, re, time, datetime, html as htmlmod, difflib
import requests
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = "myprotein"
BASE = "https://www.myprotein.no"
UA = "macro-library-personal/1.0 (single-user personal research; github.com/Maxaubert)"
OUT = os.path.join(ROOT, "data", "raw", SRC, "products.jsonl")
LOG = os.path.join(ROOT, "logs", SRC + ".log")
MIN_INTERVAL = 1.1
FOOD_CATS = {"sports-nutrition", "vitamins", "food", "protein", "health-wellbeing", "healthy-food-drink"}
SKIP_WORDS = ("deodorant", "antiperspirant", "workout-plan", "sun-", "spray-spf", "eye-sleep-mask")

_last = 0.0
nreq = 0
sess = requests.Session()
sess.headers["User-Agent"] = UA


def log(msg):
    line = f"{datetime.datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


class Robots:
    def __init__(self, text):
        self.rules = []
        grp = False
        for raw in text.splitlines():
            ln = raw.split("#")[0].strip()
            if ":" not in ln:
                continue
            k, v = (x.strip() for x in ln.split(":", 1))
            if k.lower() == "user-agent":
                grp = v == "*"
            elif grp and k.lower() == "disallow" and v:
                end = v.endswith("$")
                v = v.rstrip("$")
                self.rules.append(re.compile("^" + ".*".join(re.escape(x) for x in v.split("*")) + ("$" if end else "")))

    def allowed(self, url):
        path = url.split(".no", 1)[-1] or "/"
        return not any(r.match(path) for r in self.rules)


def get(url):
    global _last, nreq
    for attempt in range(5):
        wait = MIN_INTERVAL - (time.time() - _last)
        if wait > 0:
            time.sleep(wait)
        _last = time.time()
        nreq += 1
        try:
            r = sess.get(url, timeout=40)
        except requests.RequestException as e:
            log(f"ERR {url} {e}")
            time.sleep(2 ** attempt * 2)
            continue
        if r.status_code in (200, 404, 410):
            return r
        log(f"HTTP {r.status_code} {url} attempt {attempt}")
        time.sleep(2 ** attempt * (10 if r.status_code in (403, 429, 503) else 2))
    return None


def tonum(s):
    return float(s.replace(" ", "").replace(" ", "").replace(",", "."))


def parse_value(raw):
    raw = raw.replace(" ", " ").strip()
    if not raw or raw in ("-", "–"):
        return None
    m = re.search(r"(<)?\s*(\d+(?:[ ]\d{3})*(?:[.,]\d+)?|\d*[.,]\d+)\s*([^\d\s/|(][^/|]*)?", raw)
    if not m:
        return {"raw": raw, "value": None, "unit": None}
    d = {"raw": raw, "value": tonum(m.group(2)), "unit": (m.group(3) or "").strip() or None}
    if m.group(1):
        d["less_than"] = True
    return d


def parse_energy(raw):
    out = {}
    for m in re.finditer(r"(\d+(?:[ ]\d{3})*(?:[.,]\d+)?)\s*(kJ|kcal)", raw.replace(" ", " "), re.I):
        out[m.group(2).lower()] = tonum(m.group(1))
    return out


CANON = [(r"^(energi|energy)", "energy"), (r"^(fett|fat)$", "fat"), (r"(mettet fett|saturates|saturated)", "saturated_fat"),
         (r"(enumettet|mono-?unsaturate)", "monounsaturated_fat"), (r"(flerumettet|poly-?unsaturate)", "polyunsaturated_fat"),
         (r"^(karbohydrat|carbohydrate)", "carbs"), (r"(sukker|sugar)", "sugars"), (r"(polyol)", "polyols"),
         (r"(kostfiber|^fiber|^fibre)", "fibre"), (r"^(protein)", "protein"), (r"^salt", "salt"), (r"^(natrium|sodium)", "sodium")]


def canon(label):
    l = re.sub(r"^\(|\)$", "", label.lower().strip()).strip(" -–:")
    for rx, k in CANON:
        if re.search(rx, l):
            return k
    return None


def norm(s):
    return re.sub(r"[^a-z0-9æøåäö]", "", s.lower())


def parse_table(t, label):
    rows = [[c.get_text(" ", strip=True).replace(" ", " ") for c in tr.find_all(["td", "th"])] for tr in t.find_all("tr") if not tr.find("table")]
    return parse_rows(rows, label)


def parse_rows(rows, label):
    rows = [[c.strip() for c in r] for r in rows]
    rows = [r for r in rows if any(r)]
    h = next((i for i, r in enumerate(rows) if any(re.match(r"per\b", c, re.I) for c in r[1:])), 0)
    title_rows = rows[:h]
    rows = rows[h:]
    if len(rows) < 2:
        return None
    cols = [c for c in rows[0][1:] if c]
    i100 = next((i for i, c in enumerate(cols) if re.match(r"per\s*100", c, re.I)), None)
    iserv = next((i for i, c in enumerate(cols) if re.match(r"per\b", c, re.I) and not re.match(r"per\s*100", c, re.I)), None)
    per100, perserv, raw_rows, section = {}, {}, [], None
    for r in rows[1:]:
        if len(r) == 1 or all(not v for v in r[1:]):
            section = r[0]
            raw_rows.append(r)
            continue
        raw_rows.append(r)
        lab, vals = r[0], r[1:]
        key = canon(lab) or ("x_" + re.sub(r"[^a-z0-9æøå]+", "_", lab.lower()).strip("_"))
        for idx, tgt in ((i100, per100), (iserv, perserv)):
            if idx is None or idx >= len(vals):
                continue
            if key == "energy":
                e = parse_energy(vals[idx])
                tgt["energy_kj"], tgt["energy_kcal"] = e.get("kj"), e.get("kcal")
                continue
            pv = parse_value(vals[idx])
            if pv:
                pv["label"] = lab
                if section:
                    pv["section"] = section
                tgt[key] = pv
    serving = None
    if iserv is not None:
        m = re.search(r"per\s*(.*)", cols[iserv], re.I)
        serving = m.group(1) if m else cols[iserv]
    return {"flavour_label": label, "title": (title_rows[-1][0] if title_rows else rows[0][0]), "serving_label": cols[iserv] if iserv is not None else None,
            "serving_size": parse_value(re.sub(r"\s*porsjon.*", "", serving)) if serving else None,
            "per_100": per100, "per_serving": perserv, "raw_columns": cols, "raw_rows": raw_rows}


def variant_content(h):
    """Per-variant structured content blocks (cm_nutritionalPanel, cm_ingredientsInformation, ...)."""
    dec = json.JSONDecoder()
    seen = {}
    for mm in re.finditer(r'"content":\[\{"key":', h):
        pos = mm.start() + len('"content":')
        sk = list(re.finditer(r'"sku":(\d+),"title":"([^"]*)"', h[max(0, pos - 3000):pos]))
        if not sk:
            continue
        try:
            arr, _ = dec.raw_decode(h, pos)
        except Exception:
            continue
        d = {a["key"]: a["value"] for a in arr if isinstance(a, dict) and "key" in a}
        sc = len(json.dumps(d))
        sku = sk[-1].group(1)
        if sku not in seen or sc > seen[sku][0]:
            seen[sku] = (sc, d)
    return {k: v[1] for k, v in seen.items()}


def rich_html(v):
    """Concatenate the HTML of a ProductContentRich(List)Value."""
    if not v:
        return None
    out = []

    def walk(x):
        if isinstance(x, dict):
            if x.get("type") == "HTML" and isinstance(x.get("content"), str):
                out.append(x["content"])
            else:
                for y in x.values():
                    walk(y)
        elif isinstance(x, list):
            for y in x:
                walk(y)
    walk(v)
    return "\n".join(out) if out else None


def html_text(x):
    return re.sub(r"\s+", " ", BeautifulSoup(x, "lxml").get_text(" ", strip=True)).strip() if x else None


def panel_table(htmlstr):
    s = BeautifulSoup(htmlstr, "lxml")
    rows = []
    for tr in s.find_all("tr"):
        if tr.find("table"):
            continue
        cells = [re.sub(r"\s+", " ", c.get_text(" ", strip=True).replace(" ", " ")) for c in tr.find_all(["td", "th"])]
        if any(cells):
            rows.append(cells)
    return parse_rows(rows, None)


def parse_page(url, body):
    h = body.decode("utf-8", "replace")
    s = BeautifulSoup(h, "lxml")
    group = None
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', h, re.S):
        try:
            j = json.loads(m.group(1))
        except Exception:
            continue
        for g in (j.get("@graph") or [j]) if isinstance(j, dict) else []:
            if g.get("@type") == "ProductGroup" or (g.get("@type") == "Product" and group is None):
                group = g
    if not group:
        return None, []
    sec = s.find(id="nutritionalinfo")
    tables = []
    if sec:
        for t in sec.find_all("table"):
            p = t.find_previous("p")
            lab = p.get_text(" ", strip=True) if p else None
            pt = parse_table(t, lab)
            if pt:
                tables.append(pt)
    ing = {}
    ie = s.find(id="ingredients")
    ing_text = ie.get_text(" ", strip=True) if ie else None
    if ing_text and tables:
        pos = []
        for tb in tables:
            lab = tb["flavour_label"]
            if lab and lab not in [x[1] for x in pos]:
                i = ing_text.find(lab)
                if i >= 0:
                    pos.append((i, lab))
        pos.sort()
        for n, (i, lab) in enumerate(pos):
            j = pos[n + 1][0] if n + 1 < len(pos) else len(ing_text)
            ing[lab] = ing_text[i + len(lab):j].strip()
    de = s.find(id="directions") or s.find(id="suggestedUse")
    page = {
        "record_type": "page", "source": SRC, "source_url": url, "fetched_on": datetime.date.today().isoformat(),
        "product_group_id": group.get("productGroupID") or group.get("sku"), "name": group.get("name"),
        "brand": (group.get("brand") or {}).get("name"), "description": group.get("description"),
        "ingredients_text": ing_text, "ingredients_by_flavour": ing,
        "flavour_tables": tables, "directions": de.get_text(" ", strip=True) if de else None,
    }
    variants = []
    vcontent = variant_content(h)
    vlist = group.get("hasVariant")
    if vlist is None:  # plain Product: offers carry sku/gtin
        offs = group.get("offers") or []
        offs = offs if isinstance(offs, list) else [offs]
        vlist = [{"sku": o.get("sku"), "name": o.get("name") or group.get("name"), "gtin13": o.get("gtin13"),
                  "additionalProperty": [], "offers": o, "weight": {}} for o in offs]
    for v in vlist:
        props = {p["name"]: p["value"] for p in v.get("additionalProperty", [])}
        offer = v.get("offers") or {}
        w = v.get("weight") or {}
        flav = props.get("flavour")
        vrec = {
            "record_type": "variant", "source": SRC, "source_url": offer.get("url") or url, "page_url": url,
            "fetched_on": datetime.date.today().isoformat(), "name": v.get("name"), "brand": page["brand"],
            "sku": v.get("sku"), "ean": v.get("gtin13"), "flavour": flav, "price_nok": offer.get("price"),
            "availability": (offer.get("availability") or "").rsplit("/", 1)[-1],
            "pack": {"weight_value": w.get("value"), "weight_unit": w.get("unitText")},
            "description": page["description"], "nutrition": None, "nutrition_flags": [],
        }
        vc = vcontent.get(str(v.get("sku")), {})
        panel = rich_html(vc.get("cm_nutritionalPanel"))
        pick, meth = None, None
        if panel:
            pt = panel_table(panel)
            if pt:
                pick, meth = pt, "variant_content_panel"
                vrec["ingredients"] = html_text(rich_html(vc.get("cm_ingredientsInformation")))
                vrec["directions"] = html_text(rich_html(vc.get("cm_suggestedUseInformation")))
                vrec["dietary_suitability"] = html_text(rich_html(vc.get("cm_dietarySuitability")))
                vrec["warnings"] = html_text(rich_html(vc.get("cm_warningStatements")))
                vrec["legal_name"] = html_text(rich_html(vc.get("cm_legalName")))
        if pick:
            pass
        elif len(tables) == 1:
            pick, meth = tables[0], "single"
        elif flav:
            nf = norm(flav)
            for t in tables:
                if t["flavour_label"] and norm(t["flavour_label"]) == nf:
                    pick, meth = t, "exact_flavour"
                    break
            if not pick:
                # flavour names can be English in JSON-LD and Norwegian in the table: try the variant name tail, fuzzy
                best, bs = None, 0
                for t in tables:
                    sc = difflib.SequenceMatcher(None, norm(t["flavour_label"] or ""), nf).ratio()
                    if sc > bs:
                        best, bs = t, sc
                if best and bs >= 0.9:
                    pick, meth = best, "fuzzy_flavour"
        if pick:
            vrec["nutrition"] = {k: v2 for k, v2 in pick.items()}
            vrec["nutrition"]["match_method"] = meth
            if meth != "variant_content_panel":
                vrec["ingredients"] = ing.get(pick["flavour_label"]) if pick["flavour_label"] else ing_text
        else:
            vrec["nutrition_flags"].append("no_table" if not tables else "flavour_table_not_matched")
            vrec["candidate_flavours"] = [t["flavour_label"] for t in tables]
        variants.append(vrec)
    return page, variants


def discover(rob):
    urls = []
    r = get(BASE + "/sitemapindex-product.xml.gz")
    subs = re.findall(r"<loc>([^<]+)</loc>", r.text) if r and r.status_code == 200 else []
    for sm in subs:
        rr = get(sm)
        if rr and rr.status_code == 200:
            urls += re.findall(r"<loc>([^<]+)</loc>", rr.text)
    log(f"sitemap product urls: {len(urls)}")
    # list pages that are nutrition-ish
    r = get(BASE + "/sitemapindex-list.xml.gz")
    lists = []
    for sm in re.findall(r"<loc>([^<]+)</loc>", r.text) if r and r.status_code == 200 else []:
        rr = get(sm)
        if rr and rr.status_code == 200:
            lists += re.findall(r"<loc>([^<]+)</loc>", rr.text)
    nl = [u for u in lists if re.search(r"/c/(nutrition|ranges/myvitamins|food|healthy)", u) and "/accessories/" not in u and "offers" not in u]
    log(f"nutrition-ish list pages: {len(nl)}")
    for lu in nl:
        if not rob.allowed(lu):
            continue
        rr = get(lu)
        if not rr or rr.status_code != 200 or rr.url.rstrip("/") == BASE:
            continue
        for p in re.findall(r'href="(/p/[^"#?]+)"', rr.text):
            urls.append(BASE + p)
    out = []
    for u in dict.fromkeys(urls):
        parts = u.replace(BASE, "").strip("/").split("/")
        if len(parts) < 3 or parts[0] != "p":
            continue
        if parts[1] not in FOOD_CATS or any(w in parts[2] for w in SKIP_WORDS):
            continue
        if rob.allowed(u):
            out.append(u)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    log(f"START {SRC}")
    r = get(BASE + "/robots.txt")
    rob = Robots(r.text if r and r.status_code == 200 else "")
    urls = discover(rob)
    log(f"food-ish product pages: {len(urls)}")
    done = set()
    if os.path.exists(a.out):
        for ln in open(a.out, encoding="utf-8"):
            try:
                d = json.loads(ln)
                if d["record_type"] == "page":
                    done.add(d["source_url"])
            except Exception:
                pass
    todo = [u for u in urls if u not in done]
    if a.limit:
        todo = todo[: a.limit]
    fails = 0
    with open(a.out, "a", encoding="utf-8") as f:
        for i, u in enumerate(todo, 1):
            r = get(u)
            if r is None:
                fails += 1
                log(f"FAIL {u}")
                if fails >= 8:
                    log("too many failures, stopping source")
                    break
                continue
            if r.status_code != 200:
                log(f"SKIP {r.status_code} {u}")
                continue
            fails = 0
            try:
                page, variants = parse_page(u, r.content)
            except Exception as e:
                log(f"PARSE-ERR {u} {e!r}")
                continue
            if not page:
                log(f"NO-PRODUCTGROUP {u}")
                continue
            for rec in variants + [page]:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            if i % 25 == 0:
                log(f"progress {i}/{len(todo)} requests={nreq}")
    log(f"END requests={nreq}")


if __name__ == "__main__":
    main()
