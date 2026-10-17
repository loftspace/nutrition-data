#!/usr/bin/env python3
"""NorgesGruppen (Meny, Spar, Joker, Kiwi) product + nutrition harvester.

API: https://platform-rest-prod.ngdata.no/api/products/{chainId}/{gln}/  (the API the sites' own JS uses;
no key needed; host serves no robots.txt (404); sites' robots.txt allow /varer/).
Phases:
  harvest : per chain, per top-level category facet, paginate search with fieldset=maximal (includes nutrition)
  enrich  : per EAN (food with nutrition) GET single-product endpoint for brand, ingredients, etc.
  build   : write data/raw/norgesgruppen/products.jsonl (one line per EAN, chains merged)
Rules: 1 req/s, honest UA, no images stored, resume-safe.
"""
import json, os, sys, time, re, datetime, urllib.request, urllib.parse, urllib.error

ROOT = r"C:/Users/Admin/Documents/Claude/zz-Misc/macro-library"
OUT = f"{ROOT}/data/raw/norgesgruppen"
LOG = f"{ROOT}/logs/norgesgruppen.log"
UA = "macro-library-personal/1.0 (single-user personal research; github.com/Maxaubert)"
API = "https://platform-rest-prod.ngdata.no/api/products"
CHAINS = {"meny": (1300, "meny.no"), "spar": (1210, "spar.no"), "joker": (1220, "joker.no"), "kiwi": (1100, "kiwi.no")}
os.makedirs(OUT, exist_ok=True)
os.makedirs(os.path.dirname(LOG), exist_ok=True)
STATE = {"req": 0, "last": 0.0}
TODAY = datetime.date.today().isoformat()


def log(msg):
    line = f"{datetime.datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf8") as f:
        f.write(line + "\n")


def get(url, params=None):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    delay = 5
    for attempt in range(7 if True else 1):
        wait = 1.05 - (time.time() - STATE["last"])
        if wait > 0:
            time.sleep(wait)
        STATE["last"] = time.time()
        STATE["req"] += 1
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf8"))
        except urllib.error.HTTPError as e:
            if e.code in (403, 401):
                log(f"BLOCKED {e.code} {url}")
                raise SystemExit("blocked")
            if e.code in (404, 400):
                log(f"HTTP {e.code} (no retry) {url}")
                return None
            log(f"HTTP {e.code} {url} retry in {delay}s")
        except Exception as e:
            log(f"ERR {e!r} {url} retry in {delay}s")
        time.sleep(delay)
        delay = min(delay * 2, 300)
    log(f"GIVING UP {url}")
    return None


def strip(src):
    d = dict(src)
    for k in ("imagePath", "imageGtin"):
        d.pop(k, None)  # no images
    return d


def harvest(chain):
    cid, _ = CHAINS[chain]
    path = f"{OUT}/harvest_{chain}.jsonl"
    done_f = f"{OUT}/harvest_{chain}.done.json"
    done = json.load(open(done_f)) if os.path.exists(done_f) else {}
    base = f"{API}/{cid}/0"
    first = get(base, {"page_size": 1, "fieldset": "maximal", "full_response": "true", "facets": "Category"})
    if not first or not first.get("hits"):
        log(f"{chain}: empty response, skipping chain")
        return
    total = first["hits"]["total"]
    cats = [(b["key"], b["doc_count"]) for b in first["aggregations"]["Categories"]["buckets"]]
    log(f"{chain}: total={total} categories={len(cats)}")
    for cat, cnt in cats:
        if done.get(cat) == "complete":
            continue
        if cnt > 10000:
            log(f"WARN {chain}/{cat} has {cnt} > 10000 window, needs sub-facets")
        got, page = 0, 1
        with open(path, "a", encoding="utf8") as f:
            while True:
                d = get(base, {"page_size": 500, "page": page, "fieldset": "maximal", "full_response": "true",
                               "facet": f"Categories:{cat}", "sort": "ean.raw"})
                if not d or "hits" not in d:
                    log(f"{chain}/{cat} page {page} failed")
                    break
                hits = d["hits"]["hits"]
                for h in hits:
                    f.write(json.dumps(strip(h["_source"]), ensure_ascii=False) + "\n")
                got += len(hits)
                if len(hits) < 500:
                    break
                page += 1
        log(f"{chain}/{cat}: expected {cnt} got {got} (req so far {STATE['req']})")
        if got >= cnt * 0.99:
            done[cat] = "complete"
            json.dump(done, open(done_f, "w"))


def has_nutrition(rec):
    return any((n.get("amount") or 0) for n in (rec.get("nutritionalContent") or []))


def load_harvest():
    recs = {}
    for chain in CHAINS:
        p = f"{OUT}/harvest_{chain}.jsonl"
        if not os.path.exists(p):
            continue
        for line in open(p, encoding="utf8"):
            r = json.loads(line)
            e = r.get("ean")
            if not e:
                continue
            ent = recs.setdefault(e, {"rec": r, "chains": {}})
            ent["chains"][chain] = r.get("slugifiedUrl")
            if chain == "meny":
                ent["rec"] = r
    return recs


def enrich(limit=None):
    path = f"{OUT}/single.jsonl"
    have = set()
    if os.path.exists(path):
        for line in open(path, encoding="utf8"):
            try:
                have.add(json.loads(line)["ean"])
            except Exception:
                pass
    recs = load_harvest()
    todo = [e for e, v in recs.items() if has_nutrition(v["rec"]) and e not in have]
    log(f"enrich: {len(todo)} to fetch ({len(have)} done)")
    with open(path, "a", encoding="utf8") as f:
        for i, e in enumerate(todo[:limit]):
            d = get(f"{API}/1300/0/{e}")
            if d is None:
                # try spar for products not sold at Meny
                d = get(f"{API}/1210/0/{e}")
            if d:
                f.write(json.dumps(strip(d), ensure_ascii=False) + "\n")
                f.flush()
            if i % 200 == 0:
                log(f"enrich {i}/{len(todo)}")


def num(x):
    return x if isinstance(x, (int, float)) else None


def norm_unit(u):
    if u is None:
        return None
    u = str(u).replace("\ufffd", "µ")
    return {"µmg": "µg", "umg": "µg", "ug": "µg"}.get(u, u)


def build():
    recs = load_harvest()
    single = {}
    p = f"{OUT}/single.jsonl"
    if os.path.exists(p):
        for line in open(p, encoding="utf8"):
            try:
                r = json.loads(line)
                single[r["ean"]] = r
            except Exception:
                pass
    brands = {}
    bp = f"{OUT}/brands.jsonl"
    if os.path.exists(bp):
        for line in open(bp, encoding='utf8'):
            b = json.loads(line)
            if b.get('brand'):
                brands[b['ean']] = b['brand']
    n = 0
    with open(f"{OUT}/products.jsonl", "w", encoding="utf8") as out:
        for ean, v in recs.items():
            r = dict(v["rec"])
            s = single.get(ean, {})
            r.update({k: val for k, val in s.items() if val not in (None, "", [])})
            nc = r.get("nutritionalContent") or []
            vm = r.get("vitaminsMinerals") or []
            ok = has_nutrition(r)
            per100 = None
            if ok:
                per100 = {}
                for item in nc + vm:
                    per100[item["name"]] = {"label": item.get("displayName"), "amount": num(item.get("amount")),
                                            "unit": norm_unit(item.get("unit"))}
            urls = {c: f"https://{CHAINS[c][1]}/varer{slug}" for c, slug in v["chains"].items() if slug}
            rec = {
                "source": "norgesgruppen",
                "chains": sorted(v["chains"]),
                "source_url": next(iter(urls.values()), None),
                "source_urls": urls,
                "fetched_on": TODAY,
                "ean": ean,
                "name": r.get("title"),
                "brand": r.get("brand") or brands.get(ean),
                "vendor": r.get("vendor"),
                "pack_size": r.get("packageSize") or r.get("subtitle"),
                "subtitle": r.get("subtitle"),
                "category": r.get("categoryName"),
                "measurement": {"value": r.get("measurementValue"), "type": r.get("measurementType")},
                "ingredients": r.get("ingredients"),
                "allergens": [a["name"] for a in (r.get("allergens") or []) if a.get("code") not in (None, "FRI")],
                "country_of_origin": r.get("countryOfOrigin"),
                "organic": r.get("organic"),
                "price_nok": r.get("price"),
                "nutrition_basis": "per 100 g (or 100 ml for liquids) as labelled; source gives no explicit basis field",
                "nutrition": per100,
                "nutrition_raw": {"nutritionalContent": nc, "vitaminsMinerals": vm,
                                  "guidelineDailyAmount": r.get("guidelineDailyAmount")} if ok else None,
                "nutrition_flag": None if ok else "no_nutrition_data_all_zero_or_missing",
                "enriched": ean in single,
            }
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    log(f"build: wrote {n} products")


if __name__ == "__main__":
    cmd = sys.argv[1]
    log(f"START {cmd} {sys.argv[2:]}")
    if cmd == "harvest":
        for c in (sys.argv[2:] or CHAINS):
            harvest(c)
    elif cmd == "enrich":
        enrich(int(sys.argv[2]) if len(sys.argv) > 2 else None)
    elif cmd == "build":
        build()
    log(f"END {cmd} requests={STATE['req']}")
