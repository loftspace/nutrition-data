"""Kassalapp scraper via public keyless MCP endpoint (https://kassal.app/mcp).
Discovery: product sitemaps (robots allows all) -> EAN list. Detail: get_product(ean).
Resume-safe: skips EANs already in products.jsonl or failed.jsonl. ~30 calls/min.
"""
import json, os, re, sys, time, glob, datetime, requests

BASE = r"C:/Users/Admin/Documents/Claude/zz-Misc/macro-library"
OUT = f"{BASE}/data/raw/kassalapp"
SM = f"{OUT}/sitemaps"
PROD = f"{OUT}/products.jsonl"
FAIL = f"{OUT}/failed.jsonl"
LOG = f"{BASE}/logs/kassalapp.log"
UA = "macro-library-personal/1.0 (single-user personal research; github.com/Maxaubert)"
INTERVAL = 2.1  # s between MCP calls (~28/min)
MAX_BYTES = 8 * 1024**3

def log(m):
    line = f"{datetime.datetime.now().isoformat(timespec='seconds')} {m}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def load_urls():
    urls = []
    for p in sorted(glob.glob(f"{SM}/sitemap-products-*.xml")):
        urls += re.findall(r"<loc>([^<]+)</loc>", open(p, encoding="utf-8").read())
    out = []
    for u in urls:
        m = re.search(r"/vare/(\d+)-.*?-?(\d{8,14})$", u)
        if m:
            out.append((int(m.group(1)), m.group(2), u))
        else:
            m = re.search(r"/vare/(\d+)", u)
            if m: out.append((int(m.group(1)), None, u))
    return out

NONFOOD = re.compile(r"vaskemiddel|oppvask|bleie|bleier|servietter|shampo|balsam|tannkrem|tannb|deodorant|sapp?e|dusj|hudkrem|ansiktskrem|maskara|neglelakk|batteri|lyspære|pære|stearin|lys-|toalettpapir|tørkepapir|søppelpose|bakepapir|aluminiumsfolie|frysepose|rengjøring|kloss|hundemat|kattemat|kattesand|hundegodbit|barnemat-bleie|sokker|strømpe|truse|leke-|tusj|blyant|gavepapir|ballong|blomst|plante|kjæledyr|sminke|parfyme|barberhøvel|høvel|tamponger|bind-|kondom|vitamin-d-spray|sengetøy|håndkle|krus|kopp|glass-|tallerken|bestikk|grill-?kull|tenner|fyrstikk|vaskeklut|svamp|hansker|mopp|klut|gulvsåpe|toalettrens|avkalker|vindusvask|tøymyker|kluter", re.I)
FIRST = re.compile(r"protein|whey|kasein|casein|kreatin|bcaa|vekt-?gain|mass-?gainer|pre-?workout|electrolyte|isolat|gainer|proteinbar|proteinpulver|collagen|kollagen", re.I)
def prio(url):
    if FIRST.search(url): return 0
    if NONFOOD.search(url): return 2
    return 1

class Mcp:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Content-Type": "application/json",
                               "Accept": "application/json, text/event-stream"})
        self.id = 0; self.last = 0; self.calls = 0; self.init()
    def post(self, body):
        wait = INTERVAL - (time.time() - self.last)
        if wait > 0: time.sleep(wait)
        self.last = time.time(); self.calls += 1
        return self.s.post("https://kassal.app/mcp", json=body, timeout=60)
    def init(self):
        self.s.headers.pop("MCP-Session-Id", None)
        r = self.post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "macro-library", "version": "1.0"}}})
        sid = r.headers.get("MCP-Session-Id")
        if sid: self.s.headers["MCP-Session-Id"] = sid
        self.post({"jsonrpc": "2.0", "method": "notifications/initialized"})
    def call(self, name, args):
        backoff = 10
        for attempt in range(8):
            self.id += 1
            try:
                r = self.post({"jsonrpc": "2.0", "id": self.id + 1, "method": "tools/call",
                               "params": {"name": name, "arguments": args}})
            except requests.RequestException as e:
                log(f"net error {e}; sleep {backoff}"); time.sleep(backoff); backoff = min(backoff * 2, 600); continue
            if r.status_code == 429 or r.status_code >= 500:
                log(f"HTTP {r.status_code}; sleep {backoff}"); time.sleep(backoff); backoff = min(backoff * 2, 600); continue
            if r.status_code in (400, 404) :
                self.init(); continue
            if r.status_code in (401, 403):
                log(f"BLOCKED HTTP {r.status_code}; stopping"); sys.exit(2)
            try:
                res = r.json()
            except ValueError:
                self.init(); continue
            if "error" in res:
                log(f"rpc error {res['error']}"); self.init(); continue
            c = res["result"]["content"][0]["text"]
            if res["result"].get("isError"):
                return None, c
            return json.loads(c), None
        log("giving up after retries; stopping"); sys.exit(3)

def parse_nutrition(items):
    """Kassalapp nutrition list is per 100 g/ml. Keep raw labels plus numeric values."""
    if not items: return None
    n = {"raw": items, "per_100g": {}}
    for it in items:
        n["per_100g"][it.get("name")] = {"amount": it.get("amount"), "unit": it.get("unit")}
    return n

def main():
    os.makedirs(OUT, exist_ok=True)
    done = set()
    for p in (PROD, FAIL):
        if os.path.exists(p):
            for l in open(p, encoding="utf-8"):
                try: done.add(json.loads(l)["product_id"])
                except Exception: pass
    items = load_urls()
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    todo = [i for i in items if i[0] not in done]
    todo.sort(key=lambda i: prio(i[2]))
    if limit: todo = todo[:limit]
    log(f"start: sitemap urls={len(items)} done={len(done)} todo={len(todo)}")
    m = Mcp(); today = datetime.date.today().isoformat(); n = 0
    pf = open(PROD, "a", encoding="utf-8"); ff = open(FAIL, "a", encoding="utf-8")
    for pid, ean, url in todo:
        d, err = m.call("get_product", {"product_id": pid})
        if d is None:
            ff.write(json.dumps({"product_id": pid, "url": url, "error": err}, ensure_ascii=False) + "\n"); ff.flush()
        else:
            nut = parse_nutrition(d.get("nutrition"))
            rec = {"source": "kassalapp", "source_url": url, "fetched_on": today,
                   "product_id": d.get("product_id"), "ean": d.get("ean"), "name": d.get("name"),
                   "brand": d.get("brand"), "vendor": d.get("vendor"), "category": d.get("category"),
                   "weight": d.get("weight"), "weight_unit": d.get("weight_unit"),
                   "description": d.get("description"), "ingredients": d.get("ingredients"),
                   "allergens": d.get("allergens"), "labels": d.get("labels"),
                   "nutrition": nut, "nutrition_basis": "per 100 g/ml (Kassalapp standard)",
                   "nutrition_missing": nut is None,
                   "stores": sorted({o.get("store") for o in d.get("offers", []) if o.get("store")}),
                   "offers": [{k: o.get(k) for k in ("store", "store_code", "price", "unit_price", "checked_at", "is_fresh", "merchant_url")} for o in d.get("offers", [])]}
            pf.write(json.dumps(rec, ensure_ascii=False) + "\n"); pf.flush()
        n += 1
        if n % 200 == 0:
            log(f"progress {n}/{len(todo)} calls={m.calls}")
            if os.path.getsize(PROD) > MAX_BYTES: log("size cap"); break
    log(f"end: processed={n} calls={m.calls}")

if __name__ == "__main__":
    main()
