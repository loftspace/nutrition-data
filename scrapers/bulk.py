#!/usr/bin/env python3
"""bulk.com EU store (ships to Norway per its delivery table). Rules: see ../README.md.

Discovery: https://www.bulk.com/eu/products-index.json (the site's own product index, 309 pages).
Each product page is server rendered: JSON-LD Product (offers with sku/gtin/price per flavour+size),
sections for flavour/size lists, ingredients, and a nutrition table (per 100 g and per serving).
The page shows ONE nutrition table (not per flavour): recorded at page level with a flag.
Output: data/raw/bulk/products.jsonl (record_type=page + one record_type=offer per sku/EAN).
"""
import argparse, json, os, re, time, datetime, html as htmlmod
import requests
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = "bulk"
BASE = "https://www.bulk.com"
UA = "macro-library-personal/1.0 (single-user personal research; github.com/Maxaubert)"
OUT = os.path.join(ROOT, "data", "raw", SRC, "products.jsonl")
LOG = os.path.join(ROOT, "logs", SRC + ".log")
MIN_INTERVAL = 1.1
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
        path = url.split(".com", 1)[-1] or "/"
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
    m = re.search(r"(<)?\s*(\d+(?:[.,]\d+)?|[.,]\d+)\s*([^\d\s/|(][^/|]*)?", raw)
    if not m:
        return {"raw": raw, "value": None, "unit": None}
    d = {"raw": raw, "value": tonum(m.group(2)), "unit": (m.group(3) or "").strip() or None}
    if m.group(1):
        d["less_than"] = True
    return d


CANON = [(r"^energy", "energy"), (r"^fat$", "fat"), (r"saturate", "saturated_fat"), (r"mono-?unsaturate", "monounsaturated_fat"),
         (r"poly-?unsaturate", "polyunsaturated_fat"), (r"^carbohydrate", "carbs"), (r"sugar", "sugars"), (r"polyol", "polyols"),
         (r"^(fibre|fiber|dietary fibre)", "fibre"), (r"^protein", "protein"), (r"^salt", "salt"), (r"^sodium", "sodium")]


def canon(label):
    l = label.lower().strip(" -–:*")
    l = re.sub(r"^of which\s+", "", l)
    if label.lower().startswith("of which"):
        for rx, k in CANON:
            if re.search(rx, l) and k in ("saturated_fat", "sugars", "monounsaturated_fat", "polyunsaturated_fat", "polyols"):
                return k
        return None
    for rx, k in CANON:
        if re.search(rx, l):
            return k
    return None


def expand_rows(table):
    """Rows whose cells hold several <p> become several logical rows."""
    out = []
    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        parts = []
        for c in cells:
            ps = c.find_all("p")
            parts.append([p.get_text(" ", strip=True) for p in ps] if ps else [c.get_text(" ", strip=True)])
        n = max(len(p) for p in parts) if parts else 0
        if n == 0:
            continue
        for i in range(n):
            out.append([p[i] if i < len(p) else "" for p in parts])
    return out


def parse_nutrition(table):
    rows = expand_rows(table)
    hdr = next((r for r in rows if any(re.match(r"per\b", c, re.I) for c in r[1:])), None)
    if not hdr:
        return None
    body = rows[rows.index(hdr) + 1:]
    i100 = next((i for i, c in enumerate(hdr) if re.match(r"per\s*100", c, re.I)), None)
    iserv = next((i for i, c in enumerate(hdr) if re.match(r"per\b", c, re.I) and i != i100), None)
    per100, perserv, raw_rows = {}, {}, []
    for r in body:
        lab = r[0]
        raw_rows.append(r)
        key = canon(lab) or ("x_" + re.sub(r"[^a-z0-9]+", "_", lab.lower()).strip("_"))
        for idx, tgt in ((i100, per100), (iserv, perserv)):
            if idx is None or idx >= len(r):
                continue
            raw = r[idx]
            if key == "energy" or re.match(r"energy", lab, re.I):
                m = re.match(r"\s*([\d.,]+)\s*/\s*([\d.,]+)", raw)
                if m:
                    tgt["energy_kj"], tgt["energy_kcal"] = tonum(m.group(1)), tonum(m.group(2))
                else:
                    for mm in re.finditer(r"([\d.,]+)\s*(kJ|kcal)", raw, re.I):
                        tgt["energy_" + mm.group(2).lower()] = tonum(mm.group(1))
                tgt["_raw_energy"] = raw
                continue
            pv = parse_value(raw)
            if pv:
                pv["label"] = lab
                tgt[key] = pv
    serving = hdr[iserv] if iserv is not None else None
    sm = re.search(r"\(([^)]*)\)", serving or "")
    return {"title": hdr[0], "serving_label": serving, "serving_size": parse_value(sm.group(1)) if sm else None,
            "per_100": per100, "per_serving": perserv, "raw_columns": hdr, "raw_rows": raw_rows}


def section_text(s, hid):
    h = s.find(id=hid)
    if not h:
        return None
    blk = h.find_parent("div")
    blk = blk.find_parent("div") if blk and blk.find_parent("div") else blk
    texts = []
    for sib in (h.find_parent("div") or h).find_next_siblings():
        if sib.find(["h2"]):
            break
        texts.append(sib.get_text(" ", strip=True))
    return re.sub(r"\s+", " ", " ".join(texts)).strip() or None


def parse_page(url, body):
    h = body.decode("utf-8", "replace")
    s = BeautifulSoup(h, "lxml")
    prod = None
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', h, re.S):
        try:
            j = json.loads(m.group(1))
        except Exception:
            continue
        for g in j.get("@graph", [j]) if isinstance(j, dict) else []:
            if g.get("@type") == "Product":
                prod = g
    if not prod:
        return None, []
    li = lambda hid: [x.get_text(" ", strip=True) for x in (s.find(id=hid).find_parent("div").find_parent("div").find_all("li") if s.find(id=hid) else [])]
    nut = None
    nh = s.find(id="nutrition")
    if nh:
        tbl = nh.find_parent("div").find_parent("div").find("table")
        if tbl:
            nut = parse_nutrition(tbl)
    extra = []
    for t in s.find_all("table"):
        if nh and t is (nh.find_parent("div").find_parent("div").find("table")):
            continue
        pt = parse_nutrition(t)
        if pt:
            extra.append(pt)
    desc_h = s.find(id="description")
    page = {
        "record_type": "page", "source": SRC, "source_url": url, "fetched_on": datetime.date.today().isoformat(),
        "sku": prod.get("sku"), "name": prod.get("name"), "brand": (prod.get("brand") or {}).get("name"),
        "description": prod.get("description"), "flavours": li("flavour"), "sizes": li("size"),
        "ingredients": section_text(s, "ingredients"), "allergens": section_text(s, "allergen-advice"),
        "suitable_for": section_text(s, "suitable-for"), "usage": section_text(s, "when-and-how-to-use"),
        "nutrition": nut, "extra_tables": extra,
        "nutrition_flags": [] if nut else ["no_nutrition_table"],
        "nutrition_note": "page shows one nutrition table; flavour-specific values not exposed" if nut else None,
    }
    offers = []
    for o in prod.get("offers", []) if isinstance(prod.get("offers"), list) else [prod.get("offers") or {}]:
        sk = o.get("sku") or ""
        offers.append({
            "record_type": "offer", "source": SRC, "source_url": url, "page_url": url, "fetched_on": page["fetched_on"],
            "name": prod.get("name"), "brand": page["brand"], "sku": sk, "ean": o.get("gtin") or None,
            "price_eur": o.get("price"), "availability": (o.get("availability") or "").rsplit("/", 1)[-1],
            "sku_parts": sk.split("-")[2:] if sk.count("-") >= 2 else [], "nutrition": nut,
            "nutrition_flags": page["nutrition_flags"] + (["nutrition_page_level_not_flavour_verified"] if nut else []),
        })
    return page, offers


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    log(f"START {SRC}")
    r = get(BASE + "/robots.txt")
    rob = Robots(r.text if r and r.status_code == 200 else "")
    r = get(BASE + "/eu/products-index.json")
    urls = [BASE + d["path"] for d in r.json()["data"]] if r and r.status_code == 200 else []
    urls = [u for u in urls if rob.allowed(u)]
    log(f"product pages: {len(urls)}")
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
                    log("too many failures, stopping")
                    break
                continue
            if r.status_code != 200:
                log(f"SKIP {r.status_code} {u}")
                continue
            fails = 0
            try:
                page, offers = parse_page(u, r.content)
            except Exception as e:
                log(f"PARSE-ERR {u} {e!r}")
                continue
            if not page:
                log(f"NO-PRODUCT {u}")
                continue
            for rec in offers + [page]:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            if i % 25 == 0:
                log(f"progress {i}/{len(todo)} requests={nreq}")
    log(f"END requests={nreq}")


if __name__ == "__main__":
    main()
