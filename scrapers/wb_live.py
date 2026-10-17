#!/usr/bin/env python3
"""Check whether candidate product URLs are still live on the shop (HEAD, no body, robots honoured, 1 req/s per host).
Writes data/raw/<shop>-discontinued/live_status.jsonl: {url, live_status, http, final_url}. Resume-safe.
Usage: wb_live.py <shop>"""
import sys, os, json, re, time, requests, datetime
from urllib.parse import urlsplit, urljoin
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UA = "macro-library-personal/1.0 (single-user personal research; github.com/Maxaubert)"
shop = sys.argv[1]
HOST = {"bodystore": "https://www.bodystore.no", "proteinfabrikken": "https://www.proteinfabrikken.no", "myprotein": "https://www.myprotein.no", "bulk": "https://www.bulk.com", "bodylab-no": "https://www.bodylab.no", "life-no": "https://www.life.no"}[shop]
D = f"{ROOT}/data/raw/{shop}-discontinued"
LOG = f"{ROOT}/logs/{shop}-discontinued.log"
S = requests.Session(); S.headers.update({"User-Agent": UA, "Accept-Language": "nb-NO,nb;q=0.9"})
last = 0.0; nreq = 0
def log(m):
    line = f"{datetime.datetime.now().isoformat(timespec='seconds')} [live] {m}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf8") as f: f.write(line + "\n")
def req(method, url):
    global last, nreq
    d = 5
    for a in range(5):
        w = 1.1 - (time.time() - last)
        if w > 0: time.sleep(w)
        last = time.time(); nreq += 1
        try:
            return S.request(method, url, timeout=40, allow_redirects=False)
        except Exception as e:
            log(f"ERR {url} {type(e).__name__}"); time.sleep(d); d *= 2
    return None
# robots (wildcard aware, group *)
rules = []
r = req("GET", HOST + "/robots.txt")
grp = False
if r is not None and r.status_code == 200:
    for ln in r.text.splitlines():
        ln = ln.split("#")[0].strip()
        if ":" not in ln: continue
        k, v = [x.strip() for x in ln.split(":", 1)]
        if k.lower() == "user-agent": grp = (v == "*")
        elif k.lower() == "disallow" and grp and v:
            end = v.endswith("$"); v = v.rstrip("$")
            rules.append(re.compile("^" + ".*".join(re.escape(x) for x in v.split("*")) + ("$" if end else "")))
log(f"robots rules {len(rules)}")
def allowed(u):
    p = urlsplit(u); path = p.path + ("?" + p.query if p.query else "")
    return not any(x.match(path) for x in rules)
def ident(u):
    m = re.search(r"/(\d{7,9})(?:/|\.html|$)", u)
    if m: return m.group(1)
    return u.rstrip("/").rsplit("/", 1)[-1].replace(".html", "").lower()
def check(url):
    cur = url
    for hop in range(4):
        if not allowed(cur): return {"live_status": "robots_disallowed", "http": None, "final_url": cur}
        r = req("HEAD", cur)
        if r is None: return {"live_status": "error", "http": None, "final_url": cur}
        if r.status_code in (405, 501):
            r = req("GET", cur)
            if r is None: return {"live_status": "error", "http": None, "final_url": cur}
        sc = r.status_code
        if sc in (301, 302, 303, 307, 308):
            loc = urljoin(cur, r.headers.get("Location", ""))
            if urlsplit(loc).netloc != urlsplit(HOST).netloc: return {"live_status": "gone", "http": sc, "final_url": loc, "note": "redirect_offsite"}
            cur = loc; continue
        if sc == 200:
            same = ident(url).lower() in cur.lower() or ident(cur).lower() == ident(url).lower()
            return {"live_status": "live" if same else "gone", "http": 200, "final_url": cur, **({} if same else {"note": "redirected_to_other_page"})}
        if sc in (404, 410): return {"live_status": "gone", "http": sc, "final_url": cur}
        if sc in (403, 429, 503): return {"live_status": "blocked_unknown", "http": sc, "final_url": cur}
        return {"live_status": "error", "http": sc, "final_url": cur}
    return {"live_status": "gone", "http": 3, "final_url": cur, "note": "redirect_loop"}
cands = json.load(open(D + "/candidates.json", encoding="utf8"))
out = D + "/live_status.jsonl"
done = set()
if os.path.exists(out):
    for l in open(out, encoding="utf8"):
        try: done.add(json.loads(l)["url"])
        except Exception: pass
todo = [c for c in cands if c["url"] not in done]
log(f"START live check todo={len(todo)}")
blocked = 0
with open(out, "a", encoding="utf8") as f:
    for i, c in enumerate(todo, 1):
        res = check(c["url"] if shop != "myprotein" or c["url"].endswith(".html") else c["url"].rstrip("/") + "/")
        res["url"] = c["url"]; res["checked_on"] = datetime.date.today().isoformat()
        f.write(json.dumps(res) + "\n"); f.flush()
        blocked = blocked + 1 if res["live_status"] == "blocked_unknown" else 0
        if blocked >= 5: log("STOP: repeated 403/429/503"); break
        if i % 100 == 0: log(f"live progress {i}/{len(todo)} reqs={nreq}")
log(f"END live check reqs={nreq}")
