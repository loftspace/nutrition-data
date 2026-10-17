#!/usr/bin/env python3
"""Proteinfabrikken.no scraper (Salesforce Commerce Cloud). Rules: see ../README.md.

Source: sitemap_index.xml -> sitemap_N.xml -> product pages (*.html). Each page is server
rendered HTML with schema.org microdata (sku, gtin13, price, weight) and nutrition tables
(one per flavour, per 100 g and per serving) in the description tab.
Output: data/raw/proteinfabrikken/products.jsonl (one product per sitemap URL), resume-safe.
Usage: proteinfabrikken.py [--limit N] [--out PATH] [--urls-file F]
"""
import argparse, difflib, gzip, json, os, re, sys, time, datetime, html as htmlmod
import requests
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = "proteinfabrikken"
BASE = "https://www.proteinfabrikken.no"
UA = "macro-library-personal/1.0 (single-user personal research; github.com/Maxaubert)"
OUT_DIR = os.path.join(ROOT, "data", "raw", SRC)
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


# ---------------- robots ----------------
class Robots:
    def __init__(self, text):
        self.rules = []  # disallow patterns for User-agent: *
        grp = False
        for raw in text.splitlines():
            ln = raw.split("#")[0].strip()
            if not ln or ":" not in ln:
                continue
            k, v = ln.split(":", 1)
            k, v = k.strip().lower(), v.strip()
            if k == "user-agent":
                grp = (v == "*") if not (grp is None) else grp
                self._cur = v
                grp = v == "*"
            elif grp and k == "disallow" and v:
                self.rules.append(self._rx(v))

    @staticmethod
    def _rx(p):
        end = p.endswith("$")
        p = p.rstrip("$")
        return re.compile("^" + ".*".join(re.escape(x) for x in p.split("*")) + ("$" if end else ""))

    def allowed(self, url):
        path = url.split(".no", 1)[-1] or "/"
        return not any(r.match(path) for r in self.rules)


def get(url, binary=False):
    """Rate-limited GET with backoff. Returns response or None."""
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
        if r.status_code == 200:
            return r
        if r.status_code in (404, 410):
            return r
        log(f"HTTP {r.status_code} {url} attempt {attempt}")
        if r.status_code in (403, 429, 503):
            time.sleep(2 ** attempt * 10)
        else:
            time.sleep(2 ** attempt * 2)
    return None


# ---------------- parsing ----------------
NUM = re.compile(r"(<|<=|≤|ca\.?|~)?\s*(\d+(?:[  ]\d{3})*(?:[.,]\d+)?|\d*[.,]\d+)\s*([^\d\s/|][^/|]*)?", re.I)


def tonum(s):
    return float(s.replace(" ", "").replace(" ", "").replace(",", "."))


def parse_value(raw):
    """'6,3 g' -> {raw,value,unit,less_than}. '1 649 kJ / 394 kcal' -> list handled by caller."""
    raw = raw.replace(" ", " ").strip()
    if not raw or raw in ("-", "–"):
        return None
    if raw.lower() in ("spor", "tr", "trace"):
        return {"raw": raw, "value": 0.0, "unit": None, "trace": True}
    m = NUM.search(raw)
    if not m:
        return {"raw": raw, "value": None, "unit": None}
    d = {"raw": raw, "value": tonum(m.group(2)), "unit": (m.group(3) or "").strip() or None}
    if m.group(1) and "<" in m.group(1):
        d["less_than"] = True
    return d


def parse_energy(raw):
    out = {}
    for m in re.finditer(r"(\d+(?:[  ]\d{3})*(?:[.,]\d+)?)\s*(kJ|kcal)", raw.replace(" ", " "), re.I):
        out[m.group(2).lower()] = tonum(m.group(1))
    return out


CANON = [
    (r"^energi", "energy"), (r"^fett$|^fett totalt", "fat"), (r"mettet fett|mettede", "saturated_fat"),
    (r"enumettet", "monounsaturated_fat"), (r"flerumettet", "polyunsaturated_fat"),
    (r"^karbohydrat", "carbs"), (r"sukker", "sugars"), (r"polyol", "polyols"), (r"stivelse", "starch"),
    (r"kostfiber|fiber", "fibre"), (r"^protein", "protein"), (r"^salt", "salt"), (r"^natrium", "sodium"),
]


def canon(label):
    l = label.lower().strip(" -–:")
    if "umettet" in l and "mono" not in l and "fler" not in l and "enu" not in l:
        pass
    for rx, k in CANON:
        if re.search(rx, l):
            # "- hvorav mettet fett" must not map to fat
            if k == "fat" and l != "fett" and not l.startswith("fett totalt"):
                continue
            return k
    return None


def norm(s):
    return re.sub(r"[^a-z0-9æøåäö]", "", s.lower())


def _parse_table_std(t):
    rows = []
    for tr in t.find_all("tr"):
        cells = [re.sub(r"\s+", " ", c.get_text(" ", strip=True).replace(" ", " ")).strip() for c in tr.find_all(["td", "th"])]
        if any(cells):
            rows.append(cells)
    if len(rows) < 2:
        return None
    head = rows[0]
    first = head[0]
    if ":" in first:
        title, label = (x.strip() for x in first.split(":", 1))
        label = label or None
    else:
        title, label = first.strip(), None
    if label is None and len(head) > 1 and not re.match(r"per\b", head[1], re.I):
        label = head[1]
        cols = [c for c in head[2:] if c]
    else:
        cols = [c for c in head[1:] if c]
    return {"title": title, "label": label, "columns": cols, "rows": rows[1:]}


def _cells(t):
    rows = []
    for tr in t.find_all("tr"):
        cells = [re.sub(r"\s+", " ", c.get_text(" ", strip=True).replace(" ", " ")).strip() for c in tr.find_all(["td", "th"])]
        if any(cells):
            rows.append(cells)
    return rows


def parse_tables(t):
    """Standard (flavour in header, 'Per 100 g' columns) or transposed (flavours as columns) tables."""
    rows = _cells(t)
    if len(rows) < 2:
        return []
    head = rows[0]
    has_per = any(re.match(r"per", c, re.I) for c in head[1:]) or ":" in head[0]
    body_is_nut = any(re.match(r"(energi|protein|fett|kalorier)", r[0], re.I) for r in rows[1:])
    if has_per or not body_is_nut:
        x = _parse_table_std(t)
        return [x] if x else []
    # transposed: header = [basis text, flavour1, flavour2, ...]
    flavs = [c for c in head[1:]]
    m = re.search(r"per\s*(\d+\s*(?:g|ml))", head[0], re.I)
    flags = []
    if m:
        basis = "Per " + m.group(1)
    else:
        basis, flags = "Per 100 g", ["basis_not_stated_assumed_per_100g"]
    out = []
    for j, fl in enumerate(flavs):
        body = [[r[0], r[1 + j]] for r in rows[1:] if len(r) == len(flavs) + 1]
        if not body:
            continue
        out.append({"title": "Innhold", "label": htmlmod.unescape(fl).strip(), "columns": [basis], "rows": body,
                    "transposed": True, "table_flags": flags,
                    "skipped_rows": [r for r in rows[1:] if len(r) != len(flavs) + 1]})
    return out


def structure(tab):
    """Turn a parsed table into per100g / per_serving dicts."""
    cols = tab["columns"]
    idx100 = idxs = None
    serving_label = None
    for i, c in enumerate(cols):
        if re.match(r"per\s*100\s*(g|ml)", c, re.I):
            idx100 = i
        elif re.match(r"per\b", c, re.I) and idxs is None:
            idxs, serving_label = i, c
    per100, perserv, raw_rows = {}, {}, []
    for r in tab["rows"]:
        lab = r[0]
        vals = r[1:]
        if len(vals) == 0:
            continue
        raw_rows.append(r)
        key = canon(lab) or ("x_" + re.sub(r"[^a-z0-9]+", "_", lab.lower().strip(" -–:")).strip("_"))
        for idx, tgt in ((idx100, per100), (idxs, perserv)):
            if idx is None or idx >= len(vals):
                continue
            raw = vals[idx]
            if key == "energy":
                e = parse_energy(raw)
                if e:
                    tgt["energy_kj"] = e.get("kj")
                    tgt["energy_kcal"] = e.get("kcal")
                    tgt["_raw_energy"] = raw
                continue
            pv = parse_value(raw)
            if pv:
                pv["label"] = lab
                tgt[key] = pv
    return {"per_100": per100, "per_serving": perserv, "serving_label": serving_label,
            "serving_size": (parse_value(serving_label.split(None, 1)[1]) if serving_label and len(serving_label.split(None, 1)) > 1 else None),
            "raw_rows": raw_rows, "raw_columns": cols, "table_flags": tab.get("table_flags", []),
            "skipped_rows": tab.get("skipped_rows", [])}


def match_table(tabs, name):
    """Pick the table whose flavour label matches the variant name. Returns (tab, method)."""
    if len(tabs) == 1:
        return tabs[0], "single"
    nn = norm(name)
    best, bscore, bmeth = None, 0, None
    for t in tabs:
        lab = norm(t["label"] or "")
        if not lab:
            continue
        if nn.endswith(lab):
            s, m = 1.0 + len(lab) / 100, "exact_suffix"
        elif lab in nn:
            s, m = 0.95 + len(lab) / 1000, "contains"
        else:
            s, m = difflib.SequenceMatcher(None, lab, nn[-len(lab):]).ratio() * 0.9, "fuzzy"
        if s > bscore:
            best, bscore, bmeth = t, s, m
    # a longer label that also is a fuzzy near-match must not lose to a short exact one: check ties
    if best and bmeth == "fuzzy" and bscore < 0.8:
        return None, "ambiguous"
    if best and bmeth in ("exact_suffix", "contains"):
        # guard: another label that fuzzily matches better with a longer span (Mocka vs Mocca)
        for t in tabs:
            lab = norm(t["label"] or "")
            if lab and len(lab) > len(norm(best["label"] or "")) and difflib.SequenceMatcher(None, lab, nn[-len(lab):]).ratio() >= 0.85:
                return t, "fuzzy_longer"
    return best, bmeth


def parse_pack(name, weight):
    pk = {}
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l)\b", name, re.I)
    if m:
        pk["size_text"] = m.group(0)
        pk["size_value"] = tonum(m.group(1))
        pk["size_unit"] = m.group(2).lower()
    m = re.search(r"(\d+)\s*[xX]\s", name)
    if m:
        pk["multipack"] = int(m.group(1))
    if weight:
        pk["shipping_weight_kg"] = weight
    return pk


def parse_product(url, body):
    h = body.decode("utf-8", "replace")
    s = BeautifulSoup(h, "lxml")
    h1 = s.find("h1")
    name = htmlmod.unescape(h1.get_text(" ", strip=True)) if h1 else None
    ean = re.search(r'ean-code">(\d+)', h)
    gtin = re.search(r'itemprop="gtin13" content="(\d+)"', h)
    sku = re.search(r"SKU\s*#\s*([A-Za-z0-9]+)", h)
    meta = lambda k: (re.search(r'itemprop="%s"\s+content="([^"]*)"' % k, h) or [None, None])[1]
    # price / weight / category of the selected variant: the offer whose url matches the page
    price = meta("price")
    weight = meta("weight")
    cat = meta("category")
    bc = [x.get("name") for x in (json.loads(m) if False else [])]
    crumbs = []
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', h, re.S):
        try:
            j = json.loads(m.group(1))
        except Exception:
            continue
        if isinstance(j, dict) and j.get("@type") == "BreadcrumbList":
            crumbs = [i["name"] for i in j["itemListElement"]]
    desc = s.select_one(".product-short-description")
    ing = None
    m = re.search(r"Ingredienser(?: og allergener)?:?\s*(?:</strong>)?(.*?)(?:<strong>\s*(?:Bruksanvisning|Anbefalt|Oppbevaring|Allergen)|</div>)", h, re.S)
    if m:
        ing = re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<[^>]+>", " ", m.group(1)))).strip()
    tabs, seen_sig = [], set()
    for x in s.find_all("table"):
        for tb in parse_tables(x):
            if re.match(r"innehåll|näringsvärde", tb["title"], re.I):
                continue  # Swedish duplicate of the Norwegian table
            sig = (norm(tb["label"] or ""), tuple(tuple(r) for r in tb["rows"]))
            if sig in seen_sig:
                continue
            seen_sig.add(sig)
            tabs.append(tb)
    groups = {}
    for t in tabs:
        groups.setdefault(t["title"], []).append(t)
    rec = {
        "source": SRC, "source_url": url, "fetched_on": datetime.date.today().isoformat(),
        "name": name, "brand": meta("manufacturer") or "Proteinfabrikken", "sku": sku.group(1) if sku else None,
        "ean": (ean or gtin).group(1) if (ean or gtin) else None,
        "is_variant_group_page": bool(re.search(r"/[A-Za-z0-9]*R\.html$", url)),
        "category": cat, "breadcrumbs": crumbs, "price_nok": float(price) if price else None,
        "pack": parse_pack(name or "", float(weight) if weight else None),
        "description": desc.get_text(" ", strip=True) if desc else None,
        "ingredients_all_flavours": ing,
        "nutrition": None, "nutrition_flags": [], "extra_tables": [],
    }
    nut_title = next((k for k, ts in groups.items() if any(any(re.match(r"(energi|protein|kalori)", r[0], re.I) for r in tb["rows"]) for tb in ts)), None)
    for title, ts in groups.items():
        picked, meth = match_table(ts, name or "")
        if picked is None:
            if title == nut_title:
                rec["nutrition_flags"].append("flavour_table_ambiguous")
                rec["nutrition_candidates"] = [{"label": t["label"], **structure(t)} for t in ts]
            continue
        st = structure(picked)
        st["flavour_label"] = picked["label"]
        st["match_method"] = meth
        if title == nut_title:
            rec["nutrition"] = st
            if meth in ("fuzzy", "fuzzy_longer"):
                rec["nutrition_flags"].append("flavour_match_fuzzy")
        else:
            st["title"] = title
            rec["extra_tables"].append(st)
    if rec["nutrition"] is None and "flavour_table_ambiguous" not in rec["nutrition_flags"]:
        rec["nutrition_flags"].append("no_nutrition_table")
        # nutrition might live only as image
        if re.search(r"n[æe]ringsinnhold|n.ringsdeklarasjon", h, re.I):
            rec["nutrition_flags"].append("nutrition_mentioned_but_no_table_maybe_image")
    return rec


# ---------------- sitemap ----------------
def sitemap_urls(rob):
    r = get(BASE + "/sitemap_index.xml")
    if not r or r.status_code != 200:
        log("sitemap index failed")
        return []
    subs = re.findall(r"<loc>([^<]+)</loc>", r.text)
    urls = []
    for sm in subs:
        rr = get(sm)
        if rr and rr.status_code == 200:
            urls += re.findall(r"<loc>([^<]+)</loc>", rr.text)
    urls = [u for u in dict.fromkeys(urls) if u.endswith(".html")]
    return [u for u in urls if rob.allowed(u)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=os.path.join(OUT_DIR, "products.jsonl"))
    ap.add_argument("--random", action="store_true")
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    log(f"START {SRC} out={a.out}")
    r = get(BASE + "/robots.txt")
    rob = Robots(r.text if r and r.status_code == 200 else "")
    log(f"robots: {len(rob.rules)} disallow rules for *")
    urls = sitemap_urls(rob)
    log(f"sitemap: {len(urls)} product urls allowed")
    done = set()
    if os.path.exists(a.out):
        for ln in open(a.out, encoding="utf-8"):
            try:
                done.add(json.loads(ln)["source_url"])
            except Exception:
                pass
    todo = [u for u in urls if u not in done]
    if a.random:
        import random
        random.seed(1)
        random.shuffle(todo)
    if a.limit:
        todo = todo[: a.limit]
    log(f"todo {len(todo)} (already {len(done)})")
    fails = 0
    with open(a.out, "a", encoding="utf-8") as f:
        for i, u in enumerate(todo, 1):
            r = get(u)
            if r is None:
                fails += 1
                log(f"FAIL {u}")
                if fails >= 8:
                    log("too many consecutive failures, stopping source")
                    break
                continue
            if r.status_code != 200:
                log(f"SKIP status {r.status_code} {u}")
                continue
            fails = 0
            try:
                rec = parse_product(u, r.content)
            except Exception as e:
                log(f"PARSE-ERR {u} {e!r}")
                continue
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            if i % 100 == 0:
                log(f"progress {i}/{len(todo)} requests={nreq}")
    log(f"END requests={nreq}")


if __name__ == "__main__":
    main()
