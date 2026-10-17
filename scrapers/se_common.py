"""Shared helpers for the Swedish shop scrapers (sweden-shops, second pass).

- Fetcher: polite client (wildcard-aware robots.txt, <=1 req/s/host, honest UA, backoff, stops on blocks).
- parse_nutrition_table(): turns an HTML table (list of rows of cell texts) into the same
  nutrition structure the myprotein/bulk raw files use:
    {title, flavour_label, serving_label, serving_size{raw,value,unit}, per_100{}, per_serving{},
     raw_columns, raw_rows, flags}
  per_100 / per_serving keys: energy_kj, energy_kcal (plain numbers), fat, saturated_fat, carbs, sugars, fibre,
  protein, salt, ... and x_<slug> for everything else; each value {raw, value, unit, label[, less_than]}.
  Raw labels are kept exactly as the shop prints them (Swedish).
"""
import datetime
import json
import os
import re
import sys
import time
import unicodedata
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UA = "macro-library-personal/1.0 (single-user personal research; github.com/Maxaubert)"


def today():
    return datetime.date.today().isoformat()


class Logger:
    def __init__(self, source):
        os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
        self.path = os.path.join(ROOT, "logs", f"{source}.log")

    def __call__(self, msg):
        line = f"{datetime.datetime.now().isoformat(timespec='seconds')} {msg}"
        try:
            print(line, flush=True)
        except Exception:
            pass
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


class Blocked(Exception):
    pass


def _decode(r):
    b = r.content
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        pass
    m = re.search(rb'charset=["\']?([A-Za-z0-9_-]+)', b[:3000]) or re.search(r"charset=([A-Za-z0-9_-]+)", r.headers.get("content-type", "").encode())
    enc = m.group(1).decode() if m else "cp1252"
    try:
        return b.decode(enc, "replace")
    except LookupError:
        return b.decode("cp1252", "replace")


class Fetcher:
    def __init__(self, source, base, log, lang="sv-SE,sv;q=0.9,en;q=0.5"):
        self.source, self.base, self.log = source, base.rstrip("/"), log
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept-Language": lang})
        self.last = 0.0
        self.delay = 1.1
        self.requests_made = 0
        self.blocks = 0
        self.consec = 0
        self.rules = []  # (is_allow, regex)
        self._load_robots()

    def _load_robots(self):
        try:
            self._wait()
            r = self.s.get(self.base + "/robots.txt", timeout=30)
            self.requests_made += 1
            self.last = time.time()
        except Exception as e:
            self.log(f"robots fetch failed ({e}); treating as no restrictions")
            return
        if r.status_code in (401, 403):
            self.rules.append((False, re.compile("^/")))
            self.log("robots 401/403: treating everything as disallowed")
            return
        if r.status_code != 200 or "html" in r.headers.get("content-type", "").lower():
            self.log(f"robots.txt status {r.status_code}: no rules")
            return
        group_agents, rules_for = [], []
        in_rules = False
        for ln in r.text.splitlines():
            ln = ln.split("#")[0].strip()
            if not ln or ":" not in ln:
                continue
            k, _, v = ln.partition(":")
            k, v = k.strip().lower(), v.strip()
            if k == "user-agent":
                if in_rules:
                    group_agents, in_rules = [], False
                group_agents.append(v.lower())
            else:
                in_rules = True
                applies = any(a == "*" or "macro-library" in a for a in group_agents)
                if k in ("disallow", "allow") and applies and v:
                    pat = re.escape(v).replace(r"\*", ".*").replace(r"\$", "$")
                    rules_for.append((k == "allow", re.compile("^" + pat), len(v)))
                elif k == "crawl-delay" and applies:
                    try:
                        self.delay = max(self.delay, float(v))
                        self.log(f"crawl-delay {v}s honoured")
                    except ValueError:
                        pass
        self.rules = rules_for
        self.log(f"robots: {len(self.rules)} rules, delay {self.delay}s")

    def allowed(self, url):
        p = urlparse(url)
        path = p.path + (("?" + p.query) if p.query else "")
        best = None
        for rule in self.rules:
            if len(rule) == 3 and rule[1].search(path):
                if best is None or rule[2] > best[2] or (rule[2] == best[2] and rule[0]):
                    best = rule
            elif len(rule) == 2 and rule[1].search(path):
                best = (False, None, 9999)
        return True if best is None else best[0]

    def _wait(self):
        d = self.delay - (time.time() - self.last)
        if d > 0:
            time.sleep(d)

    def get(self, url, tries=4, json_mode=False, ok404=True):
        """Returns text (or parsed JSON) or None (404 / robots / non-fatal). Raises Blocked on bot walls."""
        if not self.allowed(url):
            self.log(f"ROBOTS-DISALLOWED skip {url}")
            return None
        wait = 3
        for _ in range(tries):
            self._wait()
            self.last = time.time()
            self.requests_made += 1
            try:
                r = self.s.get(url, timeout=45)
            except requests.RequestException as e:
                self.consec += 1
                self.log(f"ERR {url}: {type(e).__name__} {str(e)[:100]}")
                if self.consec >= 10:
                    raise Blocked("10 consecutive network failures")
                time.sleep(wait); wait *= 2
                continue
            if r.status_code == 200:
                self.consec = 0
                self.blocks = 0
                txt = _decode(r)
                if len(txt) < 25000 and re.search(r"(Just a moment\.\.\.|cf-challenge|captcha|Attention Required|Access Denied)", txt[:4000], re.I):
                    self.log(f"BOT-CHALLENGE at {url}; not bypassing")
                    raise Blocked(f"bot challenge at {url}")
                if json_mode:
                    try:
                        return json.loads(txt)
                    except ValueError:
                        self.log(f"bad JSON at {url}")
                        return None
                return txt
            if r.status_code in (404, 410):
                self.consec = 0
                return None
            if r.status_code in (401, 403, 429) or r.status_code >= 500:
                self.blocks += 1
                self.log(f"HTTP {r.status_code} {url} (backoff {wait}s, blocks={self.blocks})")
                if self.blocks >= 8:
                    raise Blocked(f"HTTP {r.status_code} repeated")
                time.sleep(wait); wait = min(wait * 2, 120)
                continue
            self.log(f"HTTP {r.status_code} {url}")
            return None
        return None


# ------------------------------------------------------------------ output helpers
def out_path(source):
    d = os.path.join(ROOT, "data", "raw", source)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "products.jsonl")


def load_done(path):
    done = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                    done.add(r.get("page_url") or r["source_url"])
                except Exception:
                    pass
    return done


def append(path, rec):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def run_crawl(source, urls, scrape, fetcher, log, limit=None):
    """scrape(fetcher, url) -> list of records (possibly empty). Resume-safe by page url."""
    path = out_path(source)
    done = load_done(path)
    todo = [u for u in urls if u not in done]
    if limit:
        todo = todo[:limit]
    log(f"{len(urls)} urls, {len(done)} done, {len(todo)} to fetch")
    n_pages = n_recs = 0
    try:
        for i, u in enumerate(todo, 1):
            try:
                recs = scrape(fetcher, u)
            except Blocked:
                raise
            except Exception as e:
                log(f"PARSE-ERR {u}: {type(e).__name__} {e}")
                continue
            if not recs:
                # remember pages with nothing to save so resume does not refetch? (not stored; cheap)
                continue
            for rec in recs:
                rec.setdefault("source", source)
                rec["page_url"] = rec.get("page_url") or u
                rec.setdefault("source_url", u)
                rec["fetched_on"] = today()
                rec.setdefault("country", "SE")
                append(path, rec)
                n_recs += 1
            n_pages += 1
            if i % 50 == 0:
                log(f"progress {i}/{len(todo)} pages_saved={n_pages} records={n_recs} requests={fetcher.requests_made}")
    except Blocked as e:
        log(f"BLOCKED: {e}")
    log(f"END {source} pages={n_pages} records={n_recs} requests={fetcher.requests_made}")
    return n_pages, n_recs


# ------------------------------------------------------------------ text helpers
def norm_ws(s):
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ").replace("​", "")).strip()


def fold(s):
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def soup(h):
    try:
        return BeautifulSoup(h, "lxml")
    except Exception:
        return BeautifulSoup(h, "html.parser")


def table_to_rows(tbl):
    rows = []
    for tr in tbl.find_all("tr"):
        cells = []
        for c in tr.find_all(["td", "th"], recursive=False) or tr.find_all(["td", "th"]):
            t = norm_ws(c.get_text(" ", strip=True))
            try:
                cs = int(c.get("colspan", 1))
            except ValueError:
                cs = 1
            cells.extend([t] * max(1, min(cs, 8)))
        if any(cells):
            rows.append(cells)
    return rows


def ean_ok(s):
    d = re.sub(r"\D", "", str(s or ""))
    if len(d) == 14 and d.startswith("0"):
        d = d[1:]
    return d if len(d) in (8, 12, 13, 14) else None


# ------------------------------------------------------------------ nutrition parsing
UNIT_RE = r"(kj|kcal|mg|µg|μg|mcg|ug|g|ml|iu|ie|%)"
CELL_RE = re.compile(r"^\s*(?P<q><|>|~|ca\.?|≈)?\s*(?P<num>\d+(?:[.,]\d+)?)\s*(?P<unit>" + UNIT_RE[1:-1] + r")?\s*\**\s*$", re.I)
ENERGY_BOTH = re.compile(r"(\d+(?:[.,]\d+)?)\s*kj", re.I)
ENERGY_KCAL = re.compile(r"(\d+(?:[.,]\d+)?)\s*kcal", re.I)


def fnum(s):
    return float(s.replace(",", ".").replace(" ", ""))


def norm_unit(u):
    if not u:
        return None
    u = u.lower()
    return {"μg": "µg", "mcg": "µg", "ug": "µg", "kj": "kJ", "ie": "IU", "iu": "IU"}.get(u, u)


def parse_cell(t):
    """'<0,5 g' -> {raw,value,unit,less_than}; returns None when no number. Unit may be None."""
    t = norm_ws(t)
    if not t or t in ("-", "–", "—", "*", "n/a", "N/A"):
        return None
    t2 = re.sub(r"\(.*?\)", "", t)  # drop '(15 %)' style tails for number parsing
    m = re.search(r"(?P<q><|>|~|ca\.?\s*|≈)?\s*(?P<num>\d+(?:[.,]\d+)?)\s*(?P<unit>mikrogram|milligram|gram|kj|kcal|mg|µg|μg|mcg|ug|g|ml|iu|ie|%)?", t2, re.I)
    if not m:
        return None
    unit = m.group("unit")
    if unit:
        ul = unit.lower()
        unit = {"gram": "g", "milligram": "mg", "mikrogram": "µg"}.get(ul, ul)
    out = {"raw": t, "value": fnum(m.group("num")), "unit": norm_unit(unit)}
    if m.group("q") and m.group("q").strip().startswith("<"):
        out["less_than"] = True
    return out


def is_value_cell(t):
    t = norm_ws(t)
    if not t:
        return False
    t = re.sub(r"\(.*?\)", "", t).strip()
    if ENERGY_BOTH.search(t) or ENERGY_KCAL.search(t):
        return True
    return bool(CELL_RE.match(t))


def strip_lead(label):
    l = norm_ws(label).lower()
    l = re.sub(r"^[\s\-–—•·*]+", "", l)
    l = re.sub(r"^(varav|därav|derav|hvorav|of which|whereof)\s+", "", l)
    l = re.sub(r"\s*[:：]\s*$", "", l)
    return l.strip(" *")


def canon_key(label):
    l = strip_lead(label)
    if re.match(r"^(energi|energy)\s*\(\s*kj\s*\)", l):
        return "energy_kj"
    if re.match(r"^(energi|energy)\s*\(\s*kcal\s*\)", l):
        return "energy_kcal"
    l0 = re.sub(r"\s*\((g|mg|µg|ug|kcal|kj|ml)\)\s*", " ", l).strip()
    l0 = re.sub(r"[/\s]+$", "", l0)
    if re.search(r"\bkcal\b|kalorier|kilokalori", l0) and not re.search(r"\bkj\b|kilojoule", l0) and re.match(r"^(energi|energy|kcal|kalorier|kilokalorier)", l0):
        return "energy_kcal"
    if re.match(r"^(kj|kilojoule)\b", l0) or re.match(r"^energi\s*\(?\s*kj\b", l0):
        return "energy_kj"
    if re.match(r"^(kcal|kalorier|kilokalorier)\b", l0):
        return "energy_kcal"
    if re.match(r"^(energi|energy|energiinneh)", l0):
        return "energy"
    if re.search(r"enkelomättat|enumättat|enkelomattat|enumettet|monoumättat|mono-unsat|monounsat", l0):
        return "monounsaturated_fat"
    if re.search(r"fleromättat|fleromattat|flerumettet|polyumättat|poly-unsat|polyunsat", l0):
        return "polyunsaturated_fat"
    if re.match(r"^(mättat|mättade|mattat|mattade|saturat)", l0) or re.search(r"mättat fett|mättade fettsyror|saturated fat|saturates", l0):
        return "saturated_fat"
    if re.match(r"^trans", l0):
        return "trans_fat"
    if re.search(r"polyol|sockeralkohol", l0):
        return "polyols"
    if re.match(r"^(sockerarter|socker|sugars?)\b", l0):
        return "sugars"
    if re.match(r"^(stärkelse|starch)", l0):
        return "starch"
    if re.match(r"^(kostfiber|kostfibrer|fiber|fibrer|fibre|dietary fib)", l0):
        return "fibre"
    if re.match(r"^(kolhydrat|kolhydrater|carbohydrate|carbs|kolhydrater totalt|total carbohydrate)", l0):
        return "carbs"
    if re.match(r"^(fett|total fett|totalt fett|fat|total fat)( totalt| total)?$", l0):
        return "fat"
    if re.match(r"^(protein|proteiner|protein totalt)$", l0):
        return "protein"
    if re.match(r"^(salt|salt \(nacl\))$", l0):
        return "salt"
    if re.match(r"^(natrium|sodium)", l0):
        return "sodium"
    if re.match(r"^kolesterol|^cholesterol", l0):
        return "cholesterol"
    s = fold(l0).replace(" ", "_")
    return "x_" + (s or "unknown")


def _macro_default_unit(key):
    return key in ("fat", "saturated_fat", "monounsaturated_fat", "polyunsaturated_fat", "trans_fat", "carbs", "sugars",
                   "polyols", "starch", "fibre", "protein", "salt")


def _classify_col(h):
    h = (h or "").lower()
    if not h.strip():
        return "blank"
    if re.search(r"%|\bri\b|\bri\*|nrv|\bdri\b|dri\*|referens|\brda\b|\brs\b|\bbidrag|\bprocent|\bav rdi|\brdi\b", h):
        return "pct"
    if re.search(r"tillagad|färdig\w*|serving drink|prepared|blandad|som dryck|med \d+\s*ml|med mjölk|with milk|zubereitet|ready to drink|as served", h):
        return "prepared"
    if re.search(r"100\s*(g|ml|gram)|\bper 100\b|/100", h):
        return "per_100"
    if re.search(r"portion|serving|\bdos\b|dagsdos|dag(lig)?\s*dos|per\s+\d|^\s*\d+(?:[.,]\d+)?\s*(g|ml|kapsl\w*|tablett\w*|st\b|stk|skopor?|scoops?|bar|burk|flaska|tuggis\w*|gummies|kaps)\b|per\s+(st|stk|kapsel|tablett|skopa|bar|burk|flaska|dag)|\bst\b|kapsl|tablett|skopa|scoop|1 \w+", h):
        return "per_serving"
    return "other"


def _serving_size(label):
    if not label:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(g|ml)\b", label, re.I)
    if m:
        return {"raw": norm_ws(m.group(0)), "value": fnum(m.group(1)), "unit": m.group(2).lower()}
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*([A-Za-zåäöÅÄÖ]+)", label)
    if m:
        return {"raw": norm_ws(m.group(0)), "value": fnum(m.group(1)), "unit": m.group(2).lower()}
    return None


def _put(d, key, ent):
    k = key
    i = 2
    while k in d:
        k = f"{key}_{i}"
        i += 1
    d[k] = ent


def _fill_row(target, label, cell, flags, row_hint=None):
    """Put one parsed row cell into target dict (per_100 or per_serving)."""
    key = canon_key(label)
    if key in ("energy", "energy_kj", "energy_kcal"):
        kj = ENERGY_BOTH.search(cell)
        kc = ENERGY_KCAL.search(cell)
        got = False
        if kj and "energy_kj" not in target:
            target["energy_kj"] = fnum(kj.group(1)); got = True
        if kc and "energy_kcal" not in target:
            target["energy_kcal"] = fnum(kc.group(1)); got = True
        if got:
            return
        c = parse_cell(cell)
        if not c:
            return
        if c["unit"] == "kJ" and "energy_kj" not in target:
            target["energy_kj"] = c["value"]
        elif c["unit"] == "kcal" and "energy_kcal" not in target:
            target["energy_kcal"] = c["value"]
        elif key == "energy_kcal" and c["unit"] is None and "energy_kcal" not in target:
            target["energy_kcal"] = c["value"]
        elif key == "energy_kj" and c["unit"] is None and "energy_kj" not in target:
            target["energy_kj"] = c["value"]
        elif key == "energy":
            flags.append("energy_unit_unclear_not_parsed")
        return
    c = parse_cell(cell)
    if not c:
        return
    unit = c["unit"]
    if unit is None:
        m = re.search(r"\((g|mg|µg|μg|mcg|ug)\)", label, re.I)
        if m:
            unit = norm_unit(m.group(1))
        elif _macro_default_unit(key):
            unit = "g"
            c["unit_inferred"] = True
        else:
            flags.append("unit_missing_for_" + key)
            return
    c["unit"] = unit
    c["label"] = label
    _put(target, key, c)


def parse_nutrition_table(rows, title=None, default_basis=None):
    """rows: list of rows of cell strings (first rows may be headers).
    Returns list of nutrition dicts (several when columns are flavours), or [] if no nutrient rows."""
    rows = [r for r in rows if any(norm_ws(c) for c in r)]
    if len(rows) < 2:
        return []
    # find first data row
    first = None
    for i, r in enumerate(rows):
        vals = [c for c in r[1:] if norm_ws(c)]
        lab = r[0]
        nutrient_label = canon_key(lab) not in ("x_unknown",) and not canon_key(lab).startswith("x_") or re.match(
            r"^(energi|kcal|kj|fett|protein|kolhydrat|salt)", strip_lead(lab))
        if vals and all(is_value_cell(c) for c in vals):
            hdr_like = (not nutrient_label) and i < len(rows) - 1 and bool(re.search(r"inneh[åa]ll|n[äa]rings|per|nutrition|deklaration|värde|mängd|amount", lab, re.I))                 and all(re.fullmatch(r"(per\s*)?\d+(?:[.,]\d+)?\s*(g|ml|gram)?", norm_ws(c), re.I) for c in vals)
            if hdr_like:
                continue
            first = i
            break
        if nutrient_label and vals and any(parse_cell(c) for c in vals):
            first = i
            break
    if first is None:
        return []
    hdr_rows = rows[:first]
    body = rows[first:]
    ncol = max(len(r) for r in rows)
    topleft = " ".join(norm_ws(r[0]) for r in hdr_rows if r and norm_ws(r[0])) if hdr_rows else ""
    # per-column header text
    colh = []
    row_titles = []
    use_hdr = []
    for r in hdr_rows:
        vs = [norm_ws(c) for c in r[1:] if norm_ws(c)]
        if len(vs) >= 2 and len(set(vs)) == 1 and _classify_col(vs[0]) == "other":
            row_titles.append(vs[0])
        else:
            use_hdr.append(r)
    if row_titles and not title:
        title = row_titles[0]
    for j in range(ncol):
        parts = []
        for r in use_hdr:
            if j < len(r) and norm_ws(r[j]) and (j > 0):
                t = norm_ws(r[j])
                if t not in parts:
                    parts.append(t)
        colh.append(" | ".join(parts))
    out_title = title
    # title row (all non-empty value headers identical in one header row, no basis words)
    cls = [_classify_col(colh[j]) if j > 0 else "label" for j in range(ncol)]
    tl_cls = _classify_col(topleft)
    # drop columns with no numeric data at all in body
    def has_data(j):
        return any(j < len(r) and norm_ws(r[j]) and parse_cell(r[j]) for r in body)
    value_cols = [j for j in range(1, ncol) if has_data(j)]
    if not value_cols:
        return []
    # decide per column basis
    basis = {}
    for j in value_cols:
        c = cls[j]
        if c == "pct":
            continue
        if c in ("per_100", "per_serving", "prepared"):
            basis[j] = c
        elif c in ("other", "blank"):
            basis[j] = None
    flavour_cols = False
    if all(basis.get(j) is None for j in value_cols if j in basis) and basis:
        # no column carries its own basis: use top-left cell
        if tl_cls in ("per_100", "per_serving"):
            if len([j for j in basis]) >= 2 and all(cls[j] == "other" for j in basis) and tl_cls == "per_100":
                flavour_cols = True
            for j in basis:
                basis[j] = tl_cls
        else:
            for j in basis:
                basis[j] = default_basis
    elif any(v is None for v in basis.values()):
        # mixed: unnamed columns inherit top-left if it says something
        for j, v in list(basis.items()):
            if v is None and tl_cls in ("per_100", "per_serving"):
                basis[j] = tl_cls
    flags = []
    results = []
    serving_label = None
    serving_cols = [j for j in value_cols if basis.get(j) == "per_serving"]
    if serving_cols:
        serving_label = colh[serving_cols[0]] if colh[serving_cols[0]] else topleft
        if not _serving_size(serving_label) and topleft:
            sz = _serving_size(topleft)
            if sz:
                serving_label = (serving_label + " " + topleft).strip()
    if flavour_cols:
        groups = [([j], colh[j]) for j in basis]
    else:
        groups = [([j for j in basis], None)]
    raw_rows = [list(map(norm_ws, r)) for r in rows]
    for cols, flav in groups:
        p100, pserv, pprep = {}, {}, {}
        fl = list(flags)
        for r in body:
            lab = norm_ws(r[0]) if r else ""
            if not lab:
                continue
            for j in cols:
                if j >= len(r) or not norm_ws(r[j]):
                    continue
                tgt = p100 if basis.get(j) == "per_100" else pserv if basis.get(j) == "per_serving" else pprep if basis.get(j) == "prepared" else None
                if tgt is None:
                    continue
                _fill_row(tgt, lab, r[j], fl)
        if not p100 and not pserv and not pprep:
            continue
        nd = {
            "flavour_label": flav or out_title,
            "title": norm_ws(topleft) or None,
            "serving_label": norm_ws(serving_label) if serving_label else None,
            "serving_size": _serving_size(serving_label),
            "per_100": p100,
            "per_serving": pserv,
            "per_100_prepared": pprep,
            "raw_columns": [norm_ws(topleft)] + [colh[j] for j in range(1, ncol)],
            "raw_rows": raw_rows,
            "flags": sorted(set(fl)),
        }
        if not any(basis.get(j) for j in cols):
            nd["flags"].append("basis_unclear")
        results.append(nd)
    return results


def has_macros(nd):
    p = nd.get("per_100") or {}
    s = nd.get("per_serving") or {}
    return bool(p.get("energy_kcal") is not None or p.get("protein") or s.get("energy_kcal") is not None or s.get("protein") or p or s)


def pick_primary(tables, flavour=None):
    """Choose one nutrition dict for a record; returns (nutrition, flags)."""
    flags = []
    if not tables:
        return None, ["no_nutrition_table"]
    cand = [t for t in tables if t.get("per_100")] or tables
    pick = None
    if flavour:
        f = fold(flavour)
        for t in cand:
            tf = fold(t.get("flavour_label") or "")
            if tf and (tf == f or tf in f or f in tf):
                pick = t
                flags.append("flavour_nutrition_matched")
                break
    if pick is None:
        pick = cand[0]
        if len(tables) > 1:
            flags.append("flavour_nutrition_shared_assumed")
    if not pick.get("per_100"):
        flags.append("per100_missing_serving_only")
    return pick, flags


PACK_RE = re.compile(r"(\d+\s*[x×]\s*)?\d+(?:[.,]\d+)?\s*(kg|g|ml|cl|dl|l|st|kapslar|tabletter|kaps|tabs|caps|servings|portioner)\b", re.I)


def pack_from_name(name):
    m = PACK_RE.search(name or "")
    return norm_ws(m.group(0)) if m else None


FOOD_BAD = re.compile(r"\b(shaker|shakers|vattenflaska|flaska|gymbag|väska|vaska|handskar|linne|tröja|troja|byxor|shorts|tights|keps|mössa|strumpor|handduk|rem\b|bälte|balte|dragrem|hopprep|massage|foam roller|lyftarskor|gymsko|hantel|skivstång|kettlebell|gummiband|träningsband|yogamatta|matta|ryggsäck|ryggsack|t-shirt|hoodie|jacka|sports-bh|bh\b|sko\b|skor\b|knäskydd|knaskydd|handledsstöd|stöd\b|tejp|presentkort|gift card)\b", re.I)


def looks_nonfood(name):
    return bool(FOOD_BAD.search(name or ""))


def base_record(source, url, **kw):
    r = {
        "record_type": "variant",
        "source": source,
        "source_url": url,
        "page_url": url,
        "country": "SE",
        "currency": "SEK",
        "name": None, "brand": None, "sku": None, "ean": None, "flavour": None,
        "price_sek": None, "categories": [], "pack_size_text": None,
        "description": None, "ingredients": None, "allergens_text": None,
        "nutrition": None, "nutrition_flags": [], "extra_tables": [],
    }
    r.update(kw)
    return r


def table_to_rows_br(tbl, collapse_digit_spaces=False):
    """Like table_to_rows but keeps <br> line breaks and expands rows whose label and value cells hold the same number of lines
    (e.g. 'Fett<br>-varav mattat fett' | '5,8 g<br>1,8 g' -> two rows). Returns list of rows of strings."""
    rows = []
    for tr in tbl.find_all("tr"):
        cells = []
        for c in tr.find_all(["td", "th"], recursive=False) or tr.find_all(["td", "th"]):
            for br in c.find_all("br"):
                br.replace_with("\n")
            for sup in c.find_all("sup"):
                sup.replace_with(" ")
            raw = c.get_text(" ")
            lines = [norm_ws(x) for x in raw.split("\n")]
            lines = [x for x in lines if x]
            if collapse_digit_spaces:
                lines = [re.sub(r"(?<=\d) (?=\d)", "", x) for x in lines]
            try:
                cs = int(c.get("colspan", 1))
            except ValueError:
                cs = 1
            cells.extend([lines] * max(1, min(cs, 8)))
        if not any(cells):
            continue
        nl = [len(c) for c in cells if len(c) > 0]
        if cells and len(cells[0]) > 1 and all(len(c) == len(cells[0]) for c in cells[1:] if len(c) > 0) and len(nl) > 1:
            for i in range(len(cells[0])):
                rows.append([c[i] if i < len(c) else "" for c in cells])
        else:
            rows.append([" ".join(c) for c in cells])
    return rows


def context_basis(tb, maxchars=260):
    """Basis ('per_100' / 'per_serving' / None) stated in the text just before a table, e.g. 'Naringsinnehall per 100 gram:'."""
    parts = []
    n = 0
    for st in tb.find_all_previous(string=True, limit=12):
        t = norm_ws(str(st))
        if not t:
            continue
        parts.append(t)
        n += len(t)
        if n > maxchars:
            break
    txt = " ".join(reversed(parts))[-maxchars:].lower()
    best, pos = None, -1
    for m in re.finditer(r"per\s*100\s*(?:g|ml|gram|milliliter)\b|100\s*(?:g|ml|gram)\b", txt):
        if m.start() > pos:
            best, pos = "per_100", m.start()
    for m in re.finditer(r"per\s*(?:portion|port\b|dagsdos|dos\b|serving|kapsel|tablett|skopa|scoop|bar\b)", txt):
        if m.start() > pos:
            best, pos = "per_serving", m.start()
    return best


def parse_table_el(tb, title=None, rows=None):
    """parse_nutrition_table for a BeautifulSoup <table>, using the text before it to decide the basis when the table itself does not say."""
    rows = rows if rows is not None else table_to_rows(tb)
    return parse_nutrition_table(rows, title=title, default_basis=context_basis(tb))
