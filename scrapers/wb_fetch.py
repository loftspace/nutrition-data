#!/usr/bin/env python3
"""Fetch Internet Archive snapshots (id_ form, raw original HTML) for candidate product pages and parse them with the
shop's existing parser. 1 request/second to web.archive.org, honest UA, resume-safe, text only.
Usage: wb_fetch.py <shop> [--limit N] [--test] [--offset N]"""
import sys, os, json, time, re, datetime, requests, importlib
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
UA = "macro-library-personal/1.0 (single-user personal research; github.com/Maxaubert)"
shop = sys.argv[1]
limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
test = "--test" in sys.argv
D = f"{ROOT}/data/raw/{shop}-discontinued"
OUT = D + ("/test.jsonl" if test else "/products.jsonl")
LOG = f"{ROOT}/logs/{shop}-discontinued.log"
S = requests.Session(); S.headers["User-Agent"] = UA
last = 0.0; nreq = 0
def log(m):
    line = f"{datetime.datetime.now().isoformat(timespec='seconds')} {m}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf8") as f: f.write(line + "\n")

def wb_get(url, ts):
    global last, nreq
    wu = f"https://web.archive.org/web/{ts}id_/{url}"
    delay = 5
    for a in range(5):
        w = float(os.environ.get("WB_DELAY", "1.6")) - (time.time() - last)
        if w > 0: time.sleep(w)
        last = time.time(); nreq += 1
        try:
            r = S.get(wu, timeout=60, allow_redirects=True)
        except Exception as e:
            log(f"ERR {url} {type(e).__name__}"); time.sleep(delay); delay *= 2; continue
        if r.status_code == 200:
            return r.content, r.url
        if r.status_code in (404, 410): return None, r.url
        log(f"HTTP {r.status_code} {url}")
        time.sleep(delay); delay *= 2
        if r.status_code == 429: delay = max(delay, 60)
    return None, None

mod = {"bodystore": "bodystore", "proteinfabrikken": "proteinfabrikken", "myprotein": "myprotein", "bulk": "bulk", "bodylab-no": "bodylab_no", "life-no": "life_no"}[shop]
P = importlib.import_module(mod)

def parse(url, body, cand):
    if shop == "bodystore":
        return [P.parse_product(body.decode("utf-8", "replace"), url, "archive")]
    if shop == "proteinfabrikken":
        return [P.parse_product(url, body)]
    if shop == "myprotein":
        page, vs = P.parse_page(url, body)
        if page:
            return [page] + vs
        import myprotein_old
        return myprotein_old.parse_old(url, body)
    if shop == "bulk":
        page, offs = P.parse_page(url, body)
        return ([page] if page else []) + offs if page else []
    if shop == "bodylab-no":
        rec, _vl = P.parse(url, body.decode("utf-8", "replace"))
        return [rec] if rec else []
    if shop == "life-no":
        rec = P.parse(url, body.decode("utf-8", "replace"))
        return [rec] if rec else []

REFETCH = "--refetch-latest" in sys.argv

def cdx_latest(url):
    """newest 200 html capture timestamp of this exact url (CDX collapse in the first pass kept the oldest)."""
    global last, nreq
    for a in range(4):
        w = float(os.environ.get("WB_DELAY", "1.6")) - (time.time() - last)
        if w > 0: time.sleep(w)
        last = time.time(); nreq += 1
        try:
            r = S.get("https://web.archive.org/cdx/search/cdx", params={"url": url, "output": "txt", "fl": "timestamp", "filter": ["statuscode:200", "mimetype:text/html"], "limit": "-1"}, timeout=90)
            if r.status_code == 200:
                t = r.text.strip().splitlines()[-1].strip() if r.text.strip() else ""
                return t if re.fullmatch(r"\d{14}", t) else None
        except Exception:
            pass
        time.sleep(5 * (a + 1))
    return None

def main():
    cands = json.load(open(D + "/candidates.json", encoding="utf8"))
    done = set(); attempted = set()
    if os.path.exists(OUT) and not test:
        for l in open(OUT, encoding="utf8"):
            try:
                j = json.loads(l); attempted.add(j["page_key"])
                if j.get("archive_fetch") == "ok" or j.get("refetched"): done.add(j["page_key"])
            except Exception: pass
    if REFETCH:
        todo = [c for c in cands if c["url"] in attempted and c["url"] not in done]
    else:
        done = attempted
        todo = [c for c in cands if c["url"] not in done]
    if "--offset" in sys.argv: todo = todo[int(sys.argv[sys.argv.index("--offset") + 1]):]
    if limit: todo = todo[:limit]
    log(f"START {shop} candidates={len(cands)} done={len(done)} todo={len(todo)}")
    n = 0; miss = 0; skipped_live = 0
    live_state = {}; live_loaded = 0
    def live_of(u):
        nonlocal live_loaded
        if live_loaded % 200 == 0:
            try:
                for l in open(D + "/live_status.jsonl", encoding="utf8"):
                    try:
                        j = json.loads(l); live_state[j["url"]] = j["live_status"]
                    except Exception: pass
            except FileNotFoundError: pass
        live_loaded += 1
        return live_state.get(u)
    with open(OUT, "w" if test else "a", encoding="utf8") as f:
        for i, c in enumerate(todo, 1):
            if not REFETCH and not test and live_of(c["url"]) == "live":
                skipped_live += 1   # live pages are scraped from the shop itself by live_fetch.py (fresher than a snapshot)
                continue
            if REFETCH:
                nts = cdx_latest(c.get("fetch_url") or c["url"])
                if nts and nts != c["ts"]:
                    c = dict(c, ts=nts)   # newer capture; otherwise re-parse the same snapshot with the current parsers
            body, final = wb_get(c.get("fetch_url") or c["url"], c["ts"])
            if body is None:
                miss += 1
                f.write(json.dumps({"page_key": c["url"], "source": shop + "-discontinued", "source_url": c["url"], "archive_timestamp": c["ts"], "archive_fetch": "failed"}) + "\n"); f.flush()
                continue
            txt = body[:200000]
            try:
                recs = parse(c["url"], body, c)
            except Exception as e:
                log(f"PARSE-ERR {c['url']} {type(e).__name__} {e}"); recs = []
            if not recs:
                tm = re.search(rb"<title>(.*?)</title>", body[:20000], re.S | re.I)
                title = tm.group(1).decode("utf-8", "replace").strip() if tm else None
                f.write(json.dumps({"page_key": c["url"], "source": shop + "-discontinued", "source_url": c["url"], "archive_timestamp": c["ts"], "archive_fetch": "ok_no_product",
                                    "title": title, "snapshot_bytes": len(body), "flags": ["snapshot_has_no_product_data" + ("_js_shell" if len(body) < 15000 else "")]}, ensure_ascii=False) + "\n"); f.flush()
                continue
            for r in recs:
                r["page_key"] = c["url"]
                r["source"] = shop + "-discontinued"
                r["source_url"] = c["url"] if r.get("source_url") in (None, c["url"]) or True else r["source_url"]
                r["archive_url"] = f"https://web.archive.org/web/{c['ts']}/{c.get('fetch_url') or c['url']}"
                r["archive_timestamp"] = c["ts"]
                r["fetched_on"] = datetime.date.today().isoformat()
                r["archive_fetch"] = "ok"
                if REFETCH: r["refetched"] = True
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush(); n += 1
            if i % 50 == 0: log(f"progress {i}/{len(todo)} saved_pages={n} miss={miss} reqs={nreq}")
    log(f"END {shop} pages={n} miss={miss} skipped_live={skipped_live} reqs={nreq}")
main()
