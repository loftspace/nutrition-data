#!/usr/bin/env python3
"""Merge archive snapshot records with live-status checks for one <shop>-discontinued folder.
Reads  data/raw/<shop>-discontinued/archive_raw.jsonl (or products.jsonl on first run, which is then renamed archive_raw.jsonl)
       data/raw/<shop>-discontinued/live_status.jsonl
Writes products.jsonl (final: parsed products with page_status live/gone, discontinued flag, archive_timestamp, flags)
       unparsed.jsonl (snapshots without product data), summary.json.
Usage: wb_finalize.py <shop>"""
import sys, os, json, collections, datetime
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
shop = sys.argv[1]
D = f"{ROOT}/data/raw/{shop}-discontinued"
raw = D + "/archive_raw.jsonl"
cur = D + "/products.jsonl"
if os.path.exists(raw):
    # fetcher may have appended more to products.jsonl since last finalize: merge both
    src = [raw]
    if os.path.exists(cur):
        src.append(cur)
else:
    src = [cur]
rows = []
for p in src:
    for l in open(p, encoding="utf8"):
        try:
            rows.append(json.loads(l))
        except Exception:
            pass
if not os.path.exists(raw):
    os.replace(cur, raw)
else:
    # rewrite raw as the union (dedup exact duplicates by json string)
    seen = set(); out = []
    for r in rows:
        k = json.dumps(r, sort_keys=True, ensure_ascii=False)
        if k not in seen:
            seen.add(k); out.append(r)
    with open(raw, "w", encoding="utf8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    rows = out
live = {}
lp = D + "/live_status.jsonl"
if os.path.exists(lp):
    for l in open(lp, encoding="utf8"):
        try:
            j = json.loads(l); live[j["url"]] = j
        except Exception:
            pass
OKS = ("ok", "live_ok")
ok_keys = {r["page_key"] for r in rows if r.get("archive_fetch") in OKS}
live_ok_keys = {r["page_key"] for r in rows if r.get("archive_fetch") == "live_ok"}
final, unparsed = [], []
for r in rows:
    pk = r.get("page_key")
    if r.get("archive_fetch") == "ok" and pk in live_ok_keys:
        continue  # the live page was scraped directly; prefer it over the snapshot
    if r.get("archive_fetch") not in OKS:
        if pk not in ok_keys:
            unparsed.append(r)
        continue
    ls = live.get(pk)
    status = ls["live_status"] if ls else "unknown_not_checked"
    r["page_status"] = status
    r["live_http"] = ls.get("http") if ls else None
    r["live_checked_on"] = ls.get("checked_on") if ls else None
    r["discontinued"] = (status == "gone")
    flags = r.get("nutrition_flags")
    if not isinstance(flags, list):
        flags = []
    if "flavour_nutrition_shared_assumed" not in flags:
        flags.append("flavour_nutrition_shared_assumed")
    if status == "live":
        flags.append("live_but_hidden_from_shop_listing_or_sitemap")
    elif status == "gone":
        flags.append("page_gone_nutrition_from_internet_archive_snapshot")
    r["nutrition_flags"] = flags
    r["source"] = shop + "-discontinued"
    final.append(r)
with open(cur, "w", encoding="utf8") as f:
    for r in final:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
with open(D + "/unparsed.jsonl", "w", encoding="utf8") as f:
    seen = set()
    for r in unparsed:
        if r["page_key"] in seen:
            continue
        seen.add(r["page_key"]); f.write(json.dumps(r, ensure_ascii=False) + "\n")


def has_nut(r):
    n = r.get("nutrition")
    if isinstance(n, dict):
        return bool(n.get("per_100") or n.get("per_serving") or n.get("tables") or n.get("raw_rows"))
    return bool(n)


pages = {r["page_key"] for r in final}
summ = {"shop": shop, "generated": datetime.datetime.now().isoformat(timespec="seconds"), "records": len(final), "pages_with_product_data": len(pages),
        "pages_unparsed": len(seen), "status_counts_pages": dict(collections.Counter({r["page_key"]: r["page_status"] for r in final}.values())),
        "records_with_nutrition": sum(1 for r in final if has_nut(r)), "records_with_ean": sum(1 for r in final if r.get("ean")),
        "discontinued_records": sum(1 for r in final if r["discontinued"])}
json.dump(summ, open(D + "/summary.json", "w"), indent=1)
print(json.dumps(summ, indent=1))
