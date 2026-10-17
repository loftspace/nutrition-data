"""Shared helpers for the 'new Norwegian shop' scrapers (second pass): polite client, wildcard robots, nutrition table parsing
into the proteinfabrikken record shape (nutrition: per_100 / per_serving / raw_rows / raw_columns)."""
import os, re, sys, json, time, datetime, html as H
import requests
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UA = "macro-library-personal/1.0 (single-user personal research; github.com/Maxaubert)"
TODAY = datetime.date.today().isoformat()
NUM = re.compile(r"^\s*(<|>|ca\.?|~)?\s*(\d+(?:[  .,]\d+)*)\s*(kj|kcal|mg|µg|μg|ug|mcg|g|ml|iu|ie|%|cfu|mikrogram|l)?(?![a-zA-Zæøå])", re.I)


def tonum(s):
    s = s.replace("\xa0", "").replace(" ", "").replace(" ", "")
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", s):
        return float(re.sub(r"[.,]", "", s))
    return float(s.replace(",", "."))


UNIT_MAP = {"kj": "kJ", "μg": "µg", "ug": "µg", "mcg": "µg", "mikrogram": "µg", "iu": "IU", "ie": "IU"}


def parse_value(raw):
    raw = (raw or "").replace("\xa0", " ").strip()
    if not raw or raw in ("-", "–", "—"):
        return None
    if raw.lower() in ("spor", "tr", "trace", "spor av"):
        return {"raw": raw, "value": 0.0, "unit": None, "trace": True}
    m = NUM.search(raw)
    if not m:
        return {"raw": raw, "value": None, "unit": None}
    unit = (m.group(3) or "").strip() or None
    if unit:
        unit = UNIT_MAP.get(unit.lower(), unit.lower())
    try:
        d = {"raw": raw, "value": tonum(m.group(2)), "unit": unit}
    except ValueError:
        return {"raw": raw, "value": None, "unit": None}
    if m.group(1) and "<" in m.group(1):
        d["less_than"] = True
    pct = re.search(r"(\d+(?:[.,]\d+)?)\s*%", raw[m.end():])
    if pct and unit != "%":
        d["pct_ri"] = tonum(pct.group(1))
    return d


def parse_energy(raw):
    out = {}
    for m in re.finditer(r"(\d+(?:[  ]\d{3})*(?:[.,]\d+)?)\s*(kJ|kcal)", (raw or "").replace("\xa0", " "), re.I):
        out[m.group(2).lower()] = tonum(m.group(1))
    return out


CANON = [
    (r"^energi|^energy|^kalorier", "energy"), (r"^fett$|^fedt$|^fat$|^fett totalt|^total fat", "fat"), (r"(?<![um])(?:mettet|mettede)|mættet|mættede|saturat|mättat", "saturated_fat"),
    (r"enumett|monounsat", "monounsaturated_fat"), (r"flerumett|polyunsat", "polyunsaturated_fat"),
    (r"^karbohydrat|^carbohydrate|^kolhydrat", "carbs"), (r"sukker|sugars|socker", "sugars"), (r"polyol", "polyols"), (r"stivelse|starch", "starch"),
    (r"kostfiber|fiber|fibre", "fibre"), (r"^protein", "protein"), (r"^salt", "salt"), (r"^natrium|^sodium", "sodium"),
]


def canon(label):
    l = label.lower().strip(" -–:*")
    l = re.sub(r",\s*(g|mg|µg|kcal|kj)\s*$", "", l)
    l = re.sub(r"\s*\((g|mg|µg)\)\s*$", "", l)
    for rx, k in CANON:
        if re.search(rx, l):
            if k == "fat" and l not in ("fett", "fedt", "fat", "total fat") and not l.startswith("fett totalt"):
                continue
            return k
    return None


def slugkey(label):
    return "x_" + re.sub(r"[^a-z0-9æøåäö]+", "_", label.lower().strip(" -–:*")).strip("_")


def clean(s):
    return re.sub(r"\s+", " ", H.unescape(s or "").replace("\xa0", " ")).strip()


def table_rows(t):
    rows = []
    for tr in t.find_all("tr"):
        cells = [clean(c.get_text(" ", strip=True)) for c in tr.find_all(["td", "th"])]
        if any(cells):
            rows.append(cells)
    return rows


def _is_header(cells):
    """header-like row: no cell (after the label) is a pure amount such as '1,5 g' or '1488 kJ'."""
    vals = [c for c in cells[1:] if c]
    if not vals:
        return True
    if re.match(r"^\s*(innhold|n[æe]ringsinnhold|n[æe]ringsdeklarasjon|n[æe]ringsverdi|n[æe]ringsinformasjon|nutritional|n[äa]rings|per\b|pr\.?\s|en daglig dose|daglig dose|dagsdose|dosering|mengde|vitaminer|mineraler|serveringsst|nutrition|amount|ingredien)", cells[0], re.I):
        return True
    if not cells[0].strip():
        return True
    for c in vals:
        if not re.search(r"\bper\b|\bpr\.", c, re.I) and re.search(r"\d[\d.,]*\s*(?:kj|kcal)\b", c, re.I):
            return False
        if re.fullmatch(r"[<>~]?\s*\d+(?:[.,\s]\d+)*\s*(kj|kcal|mg|µg|μg|ug|g|ml|iu|ie|%)?(\s*/\s*\d+(?:[.,]\d+)?\s*kcal)?\s*\**", c, re.I) or re.search(r"\d+\s*kj\s*/\s*\d+", c, re.I):
            return False
    return True


def structure_rows(rows):
    """rows: list of cell lists (leading rows may be headers). Column kinds from header cells:
    '100 g'/'100 ml' -> per_100; '%'/ADT/DRI/NRV -> pct_ri; anything else -> per_serving. Nothing is converted."""
    if not rows:
        return None
    ncol = max(len(r) for r in rows)
    kinds, labels, body = {}, {}, []
    hdr_done = False
    for r in rows:
        cells = r + [""] * (ncol - len(r))
        if not hdr_done and _is_header(cells):
            for j, c in enumerate(cells[1:], 1):
                if not c:
                    continue
                if re.search(r"100\s*(g|ml)", c, re.I):
                    kinds[j] = "per_100"; labels[j] = c
                elif re.search(r"%|adt|\bdri\b|\bri\b|nrv|\brk\b|referanse", c, re.I) and not re.search(r"\d+\s*(g|ml|kaps|tabl|stk)", c, re.I):
                    kinds[j] = "pct_ri"; labels[j] = c
                elif kinds.get(j) in (None, "per_serving"):
                    kinds[j] = "per_serving"; labels[j] = c if not labels.get(j) else labels[j] + " " + c
            if not any(cells[1:]) and 1 not in kinds:
                if re.search(r"100\s*(g|ml)", cells[0], re.I):
                    kinds[1] = "per_100"; labels[1] = cells[0]
                elif re.search(r"(pr\.?|per)\s*\w+", cells[0], re.I) and re.search(r"\d", cells[0]):
                    kinds[1] = "per_serving"; labels[1] = cells[0]
            continue
        hdr_done = True
        body.append(cells)
    if not body:
        return None
    for j in range(1, ncol):
        kinds.setdefault(j, "per_serving")
    per100, perserv, raw_rows, pct = {}, {}, [], {}
    for cells in body:
        lab = cells[0]
        if not lab or not any(cells[1:]):
            continue
        raw_rows.append(cells)
        key = canon(lab) or slugkey(lab)
        for j in range(1, ncol):
            raw = cells[j]
            if not raw:
                continue
            kind = kinds.get(j)
            if kind == "pct_ri":
                pv = parse_value(raw)
                if pv and pv.get("value") is not None:
                    pct.setdefault(key, pv["value"])
                continue
            tgt = per100 if kind == "per_100" else perserv
            if key == "energy":
                e = parse_energy(raw)
                if e:
                    tgt["energy_kj"] = e.get("kj"); tgt["energy_kcal"] = e.get("kcal"); tgt["_raw_energy"] = raw
                continue
            pv = parse_value(raw)
            if pv and pv.get("value") is None:
                continue
            if pv:
                pv["label"] = lab
                if pv.get("value") is not None and pv.get("unit") is None and not pv.get("trace"):
                    ml = re.search(r"\((mg|µg|μg|g|ml|iu|ie)\)", lab, re.I)
                    if ml:
                        pv["unit"] = UNIT_MAP.get(ml.group(1).lower(), ml.group(1).lower()); pv["unit_from_label"] = True
                    elif key in ("fat", "saturated_fat", "carbs", "sugars", "protein", "fibre", "salt", "polyols", "starch"):
                        pv["unit"] = "g"; pv["unit_inferred"] = True
                tgt.setdefault(key, pv)
    serv_label = next((labels[j] for j in sorted(labels) if kinds.get(j) == "per_serving"), None)
    return {"per_100": per100, "per_serving": perserv, "serving_label": serv_label,
            "serving_size": parse_value(serv_label) if serv_label else None,
            "pct_ri": pct, "raw_rows": raw_rows, "raw_columns": [labels.get(j) for j in sorted(labels)],
            "basis_not_stated": not labels}


def merge_nutrition(parts):
    parts = [p for p in parts if p]
    if not parts:
        return None
    base = parts[0]
    for p in parts[1:]:
        for k in ("per_100", "per_serving", "pct_ri"):
            for kk, v in p[k].items():
                base[k].setdefault(kk, v)
        base["raw_rows"] += p["raw_rows"]
    return base


class Client:
    def __init__(self, source, host, delay=1.1, accept_lang="nb-NO,nb;q=0.9"):
        self.source = source; self.host = host.rstrip("/"); self.delay = delay
        self.s = requests.Session(); self.s.headers.update({"User-Agent": UA, "Accept-Language": accept_lang})
        self.last = 0.0; self.n = 0; self.rules = []; self.blocks = 0
        self.logp = f"{ROOT}/logs/{source}.log"
        os.makedirs(os.path.dirname(self.logp), exist_ok=True)
        r = self._raw(self.host + "/robots.txt")
        grp = False
        if r is not None and r.status_code == 200 and "<html" not in r.text[:500].lower():
            for ln in r.text.splitlines():
                ln = ln.split("#")[0].strip()
                if ":" not in ln:
                    continue
                k, v = [x.strip() for x in ln.split(":", 1)]
                if k.lower() == "user-agent":
                    grp = (v == "*")
                elif grp and k.lower() == "disallow" and v:
                    end = v.endswith("$"); v = v.rstrip("$")
                    self.rules.append(re.compile("^" + ".*".join(re.escape(x) for x in v.split("*")) + ("$" if end else "")))
                elif grp and k.lower() == "crawl-delay":
                    try:
                        self.delay = max(self.delay, float(v))
                    except Exception:
                        pass
        self.log(f"START {source}; robots: {len(self.rules)} disallow rules, delay {self.delay}s")

    def log(self, m):
        line = f"{datetime.datetime.now().isoformat(timespec='seconds')} {m}"
        print(line, flush=True)
        with open(self.logp, "a", encoding="utf8") as f:
            f.write(line + "\n")

    def allowed(self, url):
        from urllib.parse import urlsplit
        p = urlsplit(url); path = p.path + ("?" + p.query if p.query else "")
        return not any(x.match(path) for x in self.rules)

    def _raw(self, url, **kw):
        w = self.delay - (time.time() - self.last)
        if w > 0:
            time.sleep(w)
        self.last = time.time(); self.n += 1
        try:
            return self.s.get(url, timeout=45, **kw)
        except Exception as e:
            self.log(f"ERR {url} {type(e).__name__}")
            return None

    def get(self, url, tries=4):
        if not self.allowed(url):
            self.log(f"ROBOTS-DISALLOWED {url}")
            return None
        d = 5
        for a in range(tries):
            r = self._raw(url)
            if r is None:
                time.sleep(d); d *= 2
                continue
            if r.status_code == 200:
                self.blocks = 0
                return r
            if r.status_code in (404, 410):
                self.log(f"{r.status_code} {url}")
                return None
            self.blocks += 1
            self.log(f"HTTP {r.status_code} {url} try {a+1}")
            if r.status_code in (401, 403, 429) and self.blocks >= 4:
                self.log("STOP: repeated blocks, not bypassing")
                raise SystemExit(2)
            time.sleep(d); d *= 2
        return None


def load_done(path, key="source_url"):
    done = set()
    if os.path.exists(path):
        for l in open(path, encoding="utf8"):
            try:
                done.add(json.loads(l)[key])
            except Exception:
                pass
    return done


_ROW = re.compile(
    r"[\s,;:|]*(?P<label>[-–•]?\s*[A-Za-zÆØÅæøåöä][A-Za-zÆØÅæøåöä()/. \-]{0,60}?)"
    r"\s*[:\t ]?\s*(?P<val>[<>]?\s*\d[\d.,]*\s*(?:[kK][jJ]\s*/\s*\d+\s*[kK][cC]al|[kK][jJ]|[kK][cC]al|mg|µg|μg|g|ml)(?![a-zæøå]))")
_HDR = re.compile(r"(?:n[æe]ringsinnhold|n[æe]ringsdeklarasjon|n[æe]ringsverdi|n[æe]ringsinformasjon|nutrition(?: facts)?)\s*(?:pr\.?|per)?\s*(?P<b1>100\s*(?:g|ml)(?:\s*/\s*ml)?|\d+\s*(?:g|ml))?"
                  r"|(?:^|[\s.])(?:pr\.?|per)\s*(?P<b2>100\s*(?:g|ml)|\d+\s*(?:g|ml))\s*:", re.I)


def parse_inline_nutrition(text, basis_default="100 g"):
    """Parse nutrition written as running text / glued lines, e.g. 'Naeringsinnhold pr 100gEnergi1771kJ/423kcalFett39,1 g- hvorav mettet20,9 g...'
    or 'Pr 100g: Energi 746 kJ / 179 kcal, Fett 2,2 g, ...'. Needs a header phrase naming the basis; stops at the first non-row text."""
    text = (text or "").replace("\xa0", " ")
    for hm in _HDR.finditer(text):
        basis = (hm.group("b1") or hm.group("b2") or "").strip()
        if not basis:
            continue
        pos = hm.end()
        rows = [["Innhold pr.", basis.replace("/ml", "")]]
        while True:
            mm = _ROW.match(text, pos)
            if not mm:
                break
            lab = mm.group("label").strip()
            if len(lab.split()) > 7 or re.search(r"sp[oø]r|ingredien|bruk|oppbevar", lab, re.I):
                break
            rows.append([lab, mm.group("val").strip()])
            pos = mm.end()
        if len(rows) > 3 and any(re.match(r"energi|kalori", r[0], re.I) or re.match(r"protein|fett", r[0], re.I) for r in rows[1:]):
            return structure_rows(rows)
    return None
