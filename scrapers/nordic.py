"""Helpers for the Danish/Swedish shop scrapers (second pass). Reuses common.py."""
import re, html, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
from common import make_table, build_values, per100_from_tables


_ORIG_CANON = common.canon_key
_ORIG_CLASS = common.classify_header
_SUBS = [("enkeltumættede", "enumettede"), ("enkelomättat", "enumettede"), ("fleromättat", "flerumettede"),
         ("flerumættede", "flerumettede"), ("mættede", "mettede"), ("mættet", "mettet"), ("mättat", "mettet"),
         ("mättade", "mettede"), ("kulhydrat", "karbohydrat"), ("kolhydrat", "karbohydrat"), ("fedt", "fett"),
         ("sukkerarter", "sukker"), ("sockerarter", "sukker"), ("socker", "sukker"), ("fedtsyrer", "fettsyrer")]


def _canon(label):
    l = label.lower().replace("\xa0", " ").strip()
    l = re.sub(r"^[\s\-–—•·]+", "", l)
    l = re.sub(r"^(varav|heraf|hvoraf|därav)\s+", "", l)
    l = re.sub(r"^of which\s+", "", l)
    en = {"fat": "fett", "saturates": "mettede", "saturated fat": "mettede", "carbohydrate": "karbohydrat", "carbohydrates": "karbohydrat",
          "sugars": "sukker", "polyols": "polyol", "fibre": "kostfiber", "fiber": "kostfiber", "energy": "energi",
          "mono-unsaturates": "enumettede", "monounsaturates": "enumettede", "polyunsaturates": "flerumettede"}
    l = en.get(l, l)
    for a, b in _SUBS:
        l = l.replace(a, b)
    return _ORIG_CANON(l)


def _classify(h):
    r = _ORIG_CLASS(h)
    if r == "unknown" and re.search(r"dosis|dagsdos|daglig|kapsel|tablet|portion|serv|scoop|\bpr\.? ?(stk|bar|pose|drik)|\bper\b", (h or "").lower()):
        return "per_serving"
    return r


common.canon_key = _canon
common.classify_header = _classify


def clean(s):
    s = re.sub(r"<(br|/p|/li|/tr)[^>]*>", "\n", s or "", flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s).replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\s*\n\s*", "\n", s).strip()


def one(s):
    return re.sub(r"\s+", " ", clean(s)).strip()


def da_numbers(v):
    """Danish thousands dot: '1.746 kJ' -> '1746 kJ'; '1.000 mg' -> '1000 mg'."""
    if v is None:
        return v
    return re.sub(r"(?<![\d,])(\d{1,3})((?:\.\d{3})+)(?!\d)(?!,)", lambda m: m.group(1) + m.group(2).replace(".", ""), v)


def sv_numbers(v):
    """Swedish thousands space: '1 543 kJ' -> '1543 kJ' (only before kJ)."""
    return re.sub(r"(\d) (\d{3})(?=\s*kj)", r"\1\2", v or "", flags=re.I)


def ident(v):
    return v


def tables_to_record(tables, numfix=da_numbers):
    """tables: [(header, [(label, value), ...])]."""
    out = []
    for h, rows in tables:
        rr = []
        for a, b in rows:
            if b is None:
                continue
            a = re.sub(r"^[\s\-–—•·]+", "", a).strip()
            rr.append((a, numfix(b)))
        if rr:
            out.append(make_table(h, rr))
    if not out:
        return {"nutrition": None, "nutrition_per100": None, "nutrition_flag": "no_nutrition_table"}
    p100 = None
    flag = None
    for t in out:
        if t["basis"] == "per_100":
            p100 = t["values"]
            break
    if p100 is None:
        unk = [t for t in out if t["basis"] == "unknown"]
        if unk:
            p100 = unk[0]["values"]
            flag = "basis_unverified_assumed_per_100"
        else:
            flag = "no_per_100_table_only_" + "_".join(sorted({t["basis"] for t in out}))
    return {"nutrition": {"tables": out}, "nutrition_per100": p100, "nutrition_flag": flag}


def sitemap_locs(text):
    return re.findall(r"<loc>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</loc>", text)


def jsonld(t, typ=None):
    res = []
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', t, re.S):
        try:
            d = json.loads(m.group(1))
        except Exception:
            continue
        for x in (d if isinstance(d, list) else [d]):
            if isinstance(x, dict) and (typ is None or x.get("@type") == typ or (isinstance(x.get("@type"), list) and typ in x["@type"])):
                res.append(x)
    return res


def run_big(source, urls, scrape, max_seconds=None, host_log=None):
    """Like common.run_main but with a 'seen' file (pages fetched but deliberately not saved, e.g. non-food), time cap."""
    import time
    log = common.Logger(source)
    path = common.out_paths(source)
    seen_path = os.path.join(os.path.dirname(path), "seen.txt")
    cl = common.Client(source, log)
    done = common.load_done(path)
    seen = set(open(seen_path, encoding="utf8").read().split("\n")) if os.path.exists(seen_path) else set()
    todo = [u for u in urls if u not in done and u not in seen]
    log(f"START {source}: {len(urls)} candidate urls, {len(done)} saved, {len(seen)} seen-skipped, {len(todo)} to fetch")
    t0 = time.time()
    n_new = n_skip = 0
    try:
        for i, u in enumerate(todo, 1):
            if max_seconds and time.time() - t0 > max_seconds:
                log(f"TIME CAP reached after {i-1} pages")
                break
            try:
                rec = scrape(cl, u)
            except common.Blocked:
                raise
            except Exception as e:
                log(f"PARSE-ERR {u}: {type(e).__name__} {e}")
                continue
            if rec is False:      # transient failure: neither saved nor remembered as skipped
                continue
            if rec is None:
                n_skip += 1
                with open(seen_path, "a", encoding="utf8") as f:
                    f.write(u + "\n")
                continue
            rec.setdefault("source", source)
            rec["source_url"] = u
            rec["fetched_on"] = common.today()
            common.append(path, rec)
            n_new += 1
            if i % 100 == 0:
                log(f"progress {i}/{len(todo)} saved_new={n_new} skipped={n_skip} requests={cl.requests_made}")
    except common.Blocked as e:
        log(f"BLOCKED: {e}")
    log(f"END {source} new={n_new} skipped={n_skip} requests={cl.requests_made}")
    return n_new


def get_soft(cl, url):
    """GET that treats any non-200 (e.g. 204 'no content') as None without back-off; still robots + rate limited."""
    import time
    from urllib.parse import urlparse
    if not cl.allowed(url):
        return None
    host = urlparse(url).netloc
    cl._wait(host)
    try:
        r = cl.s.get(url, timeout=40)
    except Exception:
        r = None
    cl.last[host] = time.time()
    cl.requests_made += 1
    if r is not None and r.status_code == 200:
        return r.content.decode("utf-8", "replace")
    return None
