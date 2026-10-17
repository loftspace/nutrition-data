"""Shared helpers for macro-library scrapers (polite client, resume, nutrient parsing)."""
import json
import os
import re
import sys
import time
import datetime
import unicodedata
import urllib.robotparser
from urllib.parse import urlparse

import requests

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UA = "macro-library-personal/1.0 (single-user personal research; github.com/Maxaubert)"
MIN_INTERVAL = 1.05  # seconds between requests to one host (rule: max 1 req/s/host)


class Logger:
    def __init__(self, source):
        os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
        self.path = os.path.join(ROOT, "logs", f"{source}.log")

    def __call__(self, msg):
        line = f"{datetime.datetime.now().isoformat(timespec='seconds')} {msg}"
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        print(line, flush=True)


class Blocked(Exception):
    pass


class Client:
    def __init__(self, source, log):
        self.log = log
        self.source = source
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept-Language": "nb-NO,nb;q=0.9"})
        self.last = {}
        self.robots = {}
        self.delays = {}
        self.requests_made = 0
        self.consec_fail = 0
        self.blocks = 0

    def _rp(self, url):
        p = urlparse(url)
        host = p.netloc
        if host in self.robots:
            return self.robots[host]
        rp = urllib.robotparser.RobotFileParser()
        try:
            self._wait(host)
            r = self.s.get(f"{p.scheme}://{host}/robots.txt", timeout=30)
            self.requests_made += 1
            self.last[host] = time.time()
            ct = r.headers.get("content-type", "")
            if r.status_code == 200 and "html" not in ct.lower():
                rp.parse(r.content.decode("utf-8", "replace").splitlines())
            elif r.status_code in (401, 403):
                rp.disallow_all = True
            else:
                rp.parse([])  # no robots.txt: allow all
        except Exception as e:  # unreachable robots => treat as allow but log
            self.log(f"robots fetch failed for {host}: {e}")
            rp.parse([])
        try:
            cd = rp.crawl_delay(UA) or rp.crawl_delay('*')
            if cd:
                self.delays[host] = max(MIN_INTERVAL, float(cd))
                self.log(f'crawl-delay {cd}s honoured for {host}')
        except Exception:
            pass
        self.robots[host] = rp
        return rp

    def allowed(self, url):
        return self._rp(url).can_fetch(UA, url) or self._rp(url).can_fetch("*", url)

    def _wait(self, host):
        d = self.delays.get(host, MIN_INTERVAL) - (time.time() - self.last.get(host, 0))
        if d > 0:
            time.sleep(d)

    def get(self, url, binary=False, retries=4):
        """GET honouring robots + rate limit. Returns text (utf-8) or None on 404.
        Raises Blocked after repeated failures / 403 / challenge."""
        if not self.allowed(url):
            self.log(f"ROBOTS-DISALLOWED skip {url}")
            return None
        host = urlparse(url).netloc
        delay = 5
        for attempt in range(retries):
            self._wait(host)
            try:
                r = self.s.get(url, timeout=40)
            except Exception as e:
                self.last[host] = time.time()
                self.requests_made += 1
                self.consec_fail += 1
                self.log(f"ERR {url}: {type(e).__name__} {str(e)[:120]}")
                if self.consec_fail >= 8:
                    raise Blocked(f"8 consecutive failures at {url}")
                time.sleep(delay)
                delay *= 2
                continue
            self.last[host] = time.time()
            self.requests_made += 1
            if r.status_code == 200:
                self.consec_fail = 0
                txt = r.content.decode("utf-8", "replace")
                if re.search(r"(captcha|cf-challenge|Just a moment\.\.\.|Access Denied)", txt[:3000], re.I) and len(txt) < 20000:
                    self.blocks += 1
                    self.log(f"BOT-CHALLENGE suspected at {url}; not bypassing")
                    raise Blocked(f"bot challenge at {url}")
                return txt
            if r.status_code in (404, 410):
                self.consec_fail = 0
                return None
            if r.status_code in (401, 403):
                self.blocks += 1
                self.log(f"HTTP {r.status_code} at {url}")
                if self.blocks >= 3:
                    raise Blocked(f"HTTP {r.status_code} repeated")
                return None
            self.consec_fail += 1
            self.log(f"HTTP {r.status_code} at {url}; backoff {delay}s")
            if self.consec_fail >= 8:
                raise Blocked(f"repeated HTTP {r.status_code}")
            time.sleep(delay)
            delay *= 2
        return None


def out_paths(source):
    d = os.path.join(ROOT, "data", "raw", source)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "products.jsonl")


def load_done(path):
    done = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["source_url"])
                except Exception:
                    pass
    return done


def append(path, rec):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def today():
    return datetime.date.today().isoformat()


# ---------------------------------------------------------------- nutrient parsing
_NUM = r"(?P<num>\d+(?:[.,]\d+)?(?:[eE]-?\d+)?)"
_UNIT = r"(?P<unit>kj|kcal|mg|µg|μg|mcg|ug|g|ml|l|%|iu|ie)"
VAL_RE = re.compile(rf"(?P<q><|>|ca\.?|~|≈)?\s*{_NUM}\s*{_UNIT}?\b", re.I)


def to_float(s):
    return float(s.replace(",", "."))


def parse_amount(s, default_unit=None):
    """'0,6 g' -> {'value':0.6,'unit':'g'}; '<0,5 g' -> {'value':0.5,'unit':'g','qualifier':'<'};
    '254 kJ (60 kcal)' -> first amount only (use parse_energy for both)."""
    if s is None:
        return None
    s = str(s).replace("\xa0", " ").strip()
    if not s or re.fullmatch(r"[-–—\s]*(g|mg|kcal|kj)?", s, re.I):
        return None
    m = VAL_RE.search(s)
    if not m:
        return None
    unit = m.group("unit")
    if unit:
        unit = {"kj": "kJ", "μg": "µg", "mcg": "µg", "ug": "µg", "iu": "IU", "ie": "IU"}.get(unit.lower(), unit.lower())
    else:
        unit = default_unit
    out = {"value": to_float(m.group("num")), "unit": unit}
    if m.group("q"):
        out["qualifier"] = "<" if m.group("q") == "<" else m.group("q")
    pct = re.search(r"\(\s*(\d+(?:[.,]\d+)?)\s*%", s)
    if pct:
        out["pct_ri"] = to_float(pct.group(1))
    return out


def parse_energy(s):
    """Return dict with energy_kj / energy_kcal parsed from a string holding either or both."""
    res = {}
    if not s:
        return res
    s = str(s).replace("\xa0", " ")
    k = re.search(r"(\d+(?:[.,]\d+)?)\s*kj", s, re.I)
    c = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:kcal|calories|kalorier)", s, re.I)
    if k:
        res["energy_kj"] = {"value": to_float(k.group(1)), "unit": "kJ"}
    if c:
        res["energy_kcal"] = {"value": to_float(c.group(1)), "unit": "kcal"}
    return res


def slug(s):
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch) or ch in "")
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


CANON = [
    (r"^energi\s*k?j$|^energi.*\bkj\b|^kilojoule", "energy_kj"),
    (r"^energi\s*kcal|^kalorier|^kcal|^energi.*kcal", "energy_kcal"),
    (r"^energi$|^energy$|^energiinnhold", "energy"),
    (r"^enumettede?|^enumettet|^mono", "monounsaturated_fat"),
    (r"^flerumettede?|^flerumettet|^poly.*umettet", "polyunsaturated_fat"),
    (r"^mettede?|^mettet|^hvorav mettede?", "saturated_fat"),
    (r"^transfett|^trans", "trans_fat"),
    (r"^fett", "fat"),
    (r"^karbohydrat", "carbs"),
    (r"^sukker|^hvorav sukker|^derav sukker", "sugars"),
    (r"^polyol|^sukkeralkohol", "polyols"),
    (r"^stivelse", "starch"),
    (r"^kostfiber|^fiber|^fibre|^kostfibre", "fibre"),
    (r"^protein", "protein"),
    (r"^salt", "salt"),
    (r"^natrium|^sodium", "sodium"),
    (r"^kolesterol", "cholesterol"),
]


def canon_key(label):
    l = label.lower().replace("\xa0", " ").strip()
    l = re.sub(r"^[\s\-–—•·]+", "", l)
    l = re.sub(r"^(hvorav|derav|herav)\s+", "", l)
    l = re.sub(r"\s*[:：]\s*$", "", l)
    l = l.strip()
    for pat, key in CANON:
        if re.search(pat, l):
            return key
    return "x_" + slug(l)


def build_values(rows):
    """rows: list of (label, value_string). Returns dict key->amount dict. Raw label kept in 'label'."""
    vals = {}
    for label, v in rows:
        if v is None:
            continue
        key = canon_key(label)
        if key in ("energy", "energy_kj", "energy_kcal"):
            e = parse_energy(v)
            if not e:
                a = parse_amount(v)
                if a and a["unit"] in ("kJ", "kcal"):
                    e = {("energy_kj" if a["unit"] == "kJ" else "energy_kcal"): a}
                elif a and a["unit"] is None:
                    a["unit"] = "kcal" if key == "energy_kcal" else "kJ"
                    a["unit_inferred"] = True
                    e = {("energy_kcal" if a["unit"] == "kcal" else "energy_kj"): a}
            for k2, a in e.items():
                a["label"] = label
                vals.setdefault(k2, a)
            continue
        a = parse_amount(v)
        if a is None:
            continue
        a["label"] = label
        if a["unit"] is None:
            a["unit"] = "g"
            a["unit_inferred"] = True
        if key in vals:
            key = key + "_2"
        vals[key] = a
    return vals


def classify_header(h):
    h = (h or "").lower()
    if re.search(r"porsjon|serving|per stk|per pk|stykk|pr\. ?porsjon", h):
        return "per_serving"
    if re.search(r"tilbered|ferdig|zubered|etter|prepared|cooked|kokt|blandet", h):
        return "prepared"
    if re.search(r"100\s*(g|gram|ml)|per 100|pr\.? ?100", h):
        return "per_100"
    return "unknown"


def per100_from_tables(tables):
    """Pick the per-100 table; fall back to an 'unknown' one (sources usually print per 100 g first)."""
    for t in tables:
        if t["basis"] == "per_100":
            return t["values"]
    for t in tables:
        if t["basis"] == "unknown":
            return t["values"]
    return None


def make_table(header, rows):
    return {"header": header, "basis": classify_header(header), "raw": [[a, b] for a, b in rows], "values": build_values(rows)}


def kcal_check(rec):
    """Quick sanity flag: kcal present and plausible."""
    p = rec.get("nutrition_per100") or {}
    k = p.get("energy_kcal")
    return bool(k and 0 <= k["value"] <= 950)


def norm_ean(s):
    if not s:
        return None
    d = re.sub(r"\D", "", str(s))
    return d if len(d) in (8, 12, 13, 14) else None


def pack_size(text):
    """Extract a pack size such as '400 g', '1,5 l', '4x125g' from a string."""
    if not text:
        return None
    m = re.search(r"(\d+\s*[x×]\s*)?\d+(?:[.,]\d+)?\s*(kg|g|ml|cl|dl|l|liter|stk)\b", text, re.I)
    return m.group(0) if m else None


def run_main(source, discover, scrape, limit=None):
    """discover(client, log) -> list of urls; scrape(client, url) -> record dict or None."""
    log = Logger(source)
    path = out_paths(source)
    cl = Client(source, log)
    log(f"START {source}")
    n_new = 0
    try:
        urls = discover(cl, log)
        if limit:
            urls = urls[:limit]
        done = load_done(path)
        todo = [u for u in urls if u not in done]
        log(f"discovered {len(urls)} urls, {len(done)} already saved, {len(todo)} to fetch")
        for i, u in enumerate(todo, 1):
            try:
                rec = scrape(cl, u)
            except Blocked:
                raise
            except Exception as e:
                log(f"PARSE-ERR {u}: {type(e).__name__} {e}")
                continue
            if rec is None:
                continue
            rec.setdefault("source", source)
            rec["source_url"] = u
            rec["fetched_on"] = today()
            append(path, rec)
            n_new += 1
            if i % 25 == 0:
                log(f"progress {i}/{len(todo)} saved_new={n_new} requests={cl.requests_made}")
    except Blocked as e:
        log(f"BLOCKED: {e}")
    log(f"END {source} new={n_new} requests={cl.requests_made}")
    return n_new, cl.requests_made
