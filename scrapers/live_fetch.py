#!/usr/bin/env python3
"""Scrape the LIVE shop page for candidates whose live check said 'live' (products that exist on the shop but were not in the
sitemap / category listing used by the first-pass scraper = hidden products). Same parser as the archive path.
Respects robots.txt (wildcards) and 1 req/s. Appends records with archive_fetch='live_ok' to <shop>-discontinued/products.jsonl.
Usage: live_fetch.py <shop> [--limit N]"""
import sys, os, json, re, time, datetime, importlib
import requests
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import nogen as N
shop = sys.argv[1]
limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
D = f"{ROOT}/data/raw/{shop}-discontinued"
HOST = {"bodystore": "https://www.bodystore.no", "proteinfabrikken": "https://www.proteinfabrikken.no", "myprotein": "https://www.myprotein.no", "bulk": "https://www.bulk.com", "bodylab-no": "https://www.bodylab.no", "life-no": "https://www.life.no"}[shop]
mod = {"bodystore": "bodystore", "proteinfabrikken": "proteinfabrikken", "myprotein": "myprotein", "bulk": "bulk", "bodylab-no": "bodylab_no", "life-no": "life_no"}[shop]
P = importlib.import_module(mod)
cl = N.Client(shop + "-discontinued", HOST)


def parse(url, body):
    if shop == "bodystore":
        return [P.parse_product(body.decode("utf-8", "replace"), url, "live-hidden")]
    if shop == "proteinfabrikken":
        return [P.parse_product(url, body)]
    if shop in ("myprotein", "bulk"):
        page, vs = P.parse_page(url, body)
        return ([page] if page else []) + vs if page else []
    if shop == "bodylab-no":
        rec, _ = P.parse(url, body.decode("utf-8", "replace"))
        return [rec] if rec else []
    if shop == "life-no":
        rec = P.parse(url, body.decode("utf-8", "replace"))
        return [rec] if rec else []


cands = {c["url"]: c for c in json.load(open(D + "/candidates.json", encoding="utf8"))}
live = []
for l in open(D + "/live_status.jsonl", encoding="utf8"):
    j = json.loads(l)
    if j["live_status"] == "live":
        live.append(j)
out = D + "/products.jsonl"
done = set()
for p in (out, D + "/archive_raw.jsonl"):
    if os.path.exists(p):
        for l in open(p, encoding="utf8"):
            try:
                r = json.loads(l)
                if r.get("archive_fetch") == "live_ok":
                    done.add(r["page_key"])
            except Exception:
                pass
todo = [j for j in live if j["url"] not in done]
if limit:
    todo = todo[:limit]
cl.log(f"[live_fetch] {len(live)} live candidates, {len(todo)} to fetch")
n = 0
with open(out, "a", encoding="utf8") as f:
    for i, j in enumerate(todo, 1):
        url = j["url"]
        fu = j.get("final_url") or url
        r = cl.get(fu)
        if not r:
            continue
        try:
            recs = parse(url, r.content)
        except Exception as e:
            cl.log(f"PARSE-ERR {url} {type(e).__name__} {e}")
            continue
        if not recs:
            f.write(json.dumps({"page_key": url, "source": shop + "-discontinued", "source_url": url, "archive_fetch": "live_no_product", "fetched_on": N.TODAY}) + chr(10)); f.flush()
            continue
        for rec in recs:
            rec["page_key"] = url
            rec["source"] = shop + "-discontinued"
            rec["source_url"] = url
            rec["fetched_on"] = N.TODAY
            rec["archive_timestamp"] = None
            rec["archive_fetch"] = "live_ok"
            f.write(json.dumps(rec, ensure_ascii=False) + chr(10))
        f.flush(); n += 1
        if i % 50 == 0:
            cl.log(f"[live_fetch] progress {i}/{len(todo)} saved_pages={n} reqs={cl.n}")
cl.log(f"[live_fetch] END saved_pages={n} reqs={cl.n}")
