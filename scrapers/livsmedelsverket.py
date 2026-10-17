"""Livsmedelsverket (Swedish food composition DB) via official open API. CC BY. 1 req/s, resume-safe."""
import requests, json, time, os, datetime, sys
ROOT = r"C:/Users/Admin/Documents/Claude/zz-Misc/macro-library"
OUT = f"{ROOT}/data/raw/livsmedelsverket/products.jsonl"
LOG = f"{ROOT}/logs/livsmedelsverket.log"
BASE = "https://dataportal.livsmedelsverket.se/livsmedel/api/v1"
UA = "macro-library-personal/1.0 (single-user personal research; github.com/Maxaubert)"
s = requests.Session(); s.headers["User-Agent"] = UA
n_req = 0; last = 0
def log(m):
    with open(LOG, "a", encoding="utf-8") as f: f.write(f"{datetime.datetime.now().isoformat(timespec='seconds')} {m}\n")
    print(m, flush=True)
def get(url, **p):
    global n_req, last
    for attempt in range(6):
        w = 1.05 - (time.time() - last)
        if w > 0: time.sleep(w)
        last = time.time(); n_req += 1
        try:
            r = s.get(url, params=p, timeout=60)
        except Exception as e:
            log(f"err {url} {e}"); time.sleep(2 ** attempt); continue
        if r.status_code == 200: return r.json()
        log(f"HTTP {r.status_code} {url}")
        if r.status_code in (403, 401): raise SystemExit("blocked")
        time.sleep(2 ** attempt * 2)
    return None
done = set()
if os.path.exists(OUT):
    for l in open(OUT, encoding="utf-8"):
        try: done.add(json.loads(l)["source_id"])
        except Exception: pass
log(f"start; already have {len(done)}")
foods = []; off = 0
while True:
    d = get(f"{BASE}/livsmedel", offset=off, limit=500, sprak=1)
    if not d: break
    foods += d["livsmedel"]; off += 500
    if off >= d["_meta"]["totalRecords"]: break
log(f"listed {len(foods)} foods")
with open(OUT, "a", encoding="utf-8") as out:
    for i, f in enumerate(foods):
        sid = str(f["nummer"])
        if sid in done: continue
        nv = get(f"{BASE}/livsmedel/{sid}/naringsvarden", sprak=1)
        if nv is None: log(f"skip {sid}"); continue
        nut = {}
        for x in nv:
            nut[x["euroFIRkod"] or x["namn"]] = {"label": x["namn"], "value": x.get("varde"), "unit": x.get("enhet"),
                "basis_g": x.get("viktGram"), "basis": x.get("matrisenhet"), "value_type": x.get("vardetyp")}
        rec = {"source": "livsmedelsverket", "source_id": sid, "name": f["namn"], "name_scientific": f.get("vetenskapligtNamn"),
               "food_type": f.get("livsmedelsTyp"), "project": f.get("projekt"), "brand": None, "ean": None, "pack_size": None,
               "per": "100 g edible portion (basis_g per nutrient)", "nutrients": nut,
               "source_url": f"{BASE}/livsmedel/{sid}/naringsvarden?sprak=1", "fetched_on": datetime.date.today().isoformat(),
               "license": "CC BY (Livsmedelsverket)"}
        out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush()
        if i % 200 == 0: log(f"{i}/{len(foods)} req={n_req}")
log(f"done req={n_req}")
