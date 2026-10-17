#!/usr/bin/env python
"""Lifebutiken.se (Life, Nordic health-food chain, Swedish web shop). Rules: ../README.md.
URLs: googlesitemap.axd?SitemapType=products (allowed by robots.txt). Categories kept: mat-dryck, kosttillskott, traning (halsa/skonhet/hem-livsstil are mostly non-food and skipped).
Per page: JSON-LD Product (name, brand, gtin, price SEK), breadcrumb path, and the free-text product specification
('Ingredienser ... Naringsvarde per 100 g: Energi: 2484kJ / 599 kcal<br>Fett: 49,2g ...') parsed into label/value rows.
Nutrition is only parsed when the text states its basis (per 100 g / per portion); otherwise raw lines are kept with a flag.
Usage: python life_se.py [--limit N] [--debug URL]
"""
import json
import re
import sys

from se_common import *

SOURCE = "life-se"
BASE = "https://www.lifebutiken.se"
KEEP = ("mat-dryck", "kosttillskott", "traning")


def discover(f, log):
    urls = []
    for page in range(1, 20):
        x = f.get(f"{BASE}/googlesitemap.axd?SitemapType=products&page={page}")
        locs = re.findall(r"<loc>([^<]+)</loc>", x or "")
        if not locs:
            break
        urls += [l.replace("&amp;", "&") for l in locs]
        log(f"sitemap page {page}: {len(locs)}")
        if len(locs) < 1000:
            break
    keep = [u for u in dict.fromkeys(urls) if u.split("/")[3:4] and u.split("/")[3] in KEEP and not looks_nonfood(u.rsplit("/", 1)[1].replace("-", " "))]
    log(f"product urls total={len(urls)} kept={len(keep)}")
    return keep


def find_spec_lines(s):
    """Return list of lines of the paragraph that holds 'Ingredienser' / 'Naringsvarde' (br -> newline)."""
    best = None
    for st in s.find_all(string=re.compile(r"Ingredienser|N.ringsv.rd|N.ringsinneh")):
        p = st.find_parent("p") or st.find_parent("div")
        if p is None:
            continue
        txt = p.get_text(" ")
        for br in p.find_all("br"):
            br.replace_with("\n")
        raw = p.get_text(" ")
        lines = [norm_ws(x) for x in raw.split("\n")]
        lines = [x for x in lines if x]
        if best is None or len(lines) > len(best):
            best = lines
    return best or []


def parse_text_nutrition(lines):
    head_i = None
    for i, l in enumerate(lines):
        if re.search(r"n[äa]ringsv[äa]rd|n[äa]ringsinneh|n[äa]ringsdeklaration|inneh[åa]ll per|per 100", l, re.I) and not re.match(r"(?i)ingredienser", l):
            head_i = i
            break
    if head_i is None:
        return None, []
    head = lines[head_i]
    rows = [["Näringsvärde", head]]
    raw_lines = [head]
    tail = lines[head_i + 1:]
    first_inline = re.split(r":\s*", head, maxsplit=1)
    for l in tail:
        if re.match(r"(?i)(allergi|ursprung|f[oö]rvar|ingredienser|anv[aä]nd|rekommend|tillverk|inneh[aå]ller spår|bäst)", l):
            break
        m = re.match(r"^(.*?)\s*[:\-]\s*(<?\s*\d.*)$", l)
        if not m:
            m = re.match(r"^([A-Za-zÀ-ÿ\- ]+?)\s+(<?\d[\d.,]*\s*(?:g|mg|kj|kcal|µg|mcg)\b.*)$", l, re.I)
        if m:
            rows.append([m.group(1).strip(), m.group(2).strip()])
            raw_lines.append(l)
        else:
            break
    return rows, raw_lines


def scrape(f, url):
    h = f.get(url)
    if not h:
        return []
    s = soup(h)
    prod = None
    for t in s.find_all("script", type="application/ld+json"):
        try:
            d = json.loads(t.string or "", strict=False)
        except ValueError:
            continue
        for x in (d if isinstance(d, list) else [d]):
            if isinstance(x, dict) and x.get("@type") == "Product":
                if prod is None:
                    prod = dict(x)
                else:
                    for k, v in x.items():
                        if prod.get(k) in (None, "", []) and v not in (None, "", []):
                            prod[k] = v
    if not prod:
        return []
    name = norm_ws(prod.get("name"))
    if not name or looks_nonfood(name):
        return []
    brand = prod.get("brand")
    brand = brand.get("name") if isinstance(brand, dict) else brand
    off = prod.get("offers") or {}
    if isinstance(off, list):
        off = off[0] if off else {}
    price = None
    try:
        price = float(off.get("price")) if off.get("price") not in (None, "") else None
    except (TypeError, ValueError):
        pass
    ean = ean_ok(prod.get("gtin13") or prod.get("gtin") or prod.get("gtin14") or prod.get("gtin12") or prod.get("gtin8")
                 or off.get("gtin13") or off.get("gtin"))
    lines = find_spec_lines(s)
    rows, raw_lines = parse_text_nutrition(lines)
    flags = []
    nut = None
    tables = []
    html_tables = []
    for tb in s.find_all("table"):
        if re.search(r"(?i)inneh.ll\s*per|n.ringsv.rd|n.ringsinneh|energi|kcal|per dagsdos", tb.get_text(" ")):
            html_tables.extend(parse_table_el(tb))
    if html_tables:
        tables = html_tables
        nut, f2 = pick_primary(tables)
        flags += f2
        if len(tables) > 1:
            flags.append("multiple_tables_first_used")
    elif rows and len(rows) > 1:
        tables = parse_nutrition_table(rows)
        if tables:
            nut = tables[0]
        else:
            flags.append("nutrition_text_basis_unclear_not_parsed")
    else:
        flags.append("no_nutrition_text")
    if html_tables:
        rows = None
    ing = None
    for i, l in enumerate(lines):
        m = re.match(r"(?i)ingredienser?\s*:?\s*(.*)$", l)
        if m:
            ing = m.group(1).strip()[:4000] or (lines[i + 1].strip()[:4000] if i + 1 < len(lines) else None)
            break
    cats = [p.replace("-", " ") for p in url.split("/")[3:-1]]
    rec = base_record(SOURCE, url, name=name, brand=norm_ws(brand) if brand else None, sku=prod.get("sku"), ean=ean, price_sek=price,
                      categories=cats, pack_size_text=pack_from_name(name), description=norm_ws(soup(prod.get("description") or "").get_text(" "))[:1500] or None,
                      ingredients=ing, nutrition=nut, nutrition_flags=flags)
    rec["nutrition_text_lines"] = raw_lines if rows else None
    rec["extra_tables"] = [t for t in tables if t is not nut][:6]
    return [rec]


if __name__ == "__main__":
    log = Logger(SOURCE)
    f = Fetcher(SOURCE, BASE, log)
    if "--debug" in sys.argv:
        u = sys.argv[sys.argv.index("--debug") + 1]
        for r in scrape(f, u):
            print(json.dumps(r, ensure_ascii=False, indent=1)[:3500])
        sys.exit(0)
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    log(f"START {SOURCE}")
    urls = discover(f, log)
    run_crawl(SOURCE, urls, scrape, f, log, limit=limit)
