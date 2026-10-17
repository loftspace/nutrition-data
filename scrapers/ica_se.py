#!/usr/bin/env python
"""ICA.se product pages (server-rendered, listed in the site's own product sitemaps).
Usage: python ica_se.py [max_pages] [max_hours]"""
import re, sys, os, html, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nordic import *
import common

BASE = "https://www.ica.se"
PRIORITY = re.compile(r"protein|proteinbar|skyr|kvarg|yoghurt|yogurt|mjolk|mjölk|ost-|-ost|bar-|-bar-|snack|chips|choklad|musli|müsli|granola|havre|kex|nötter|notter|jordnöt|energi|dryck|kyckling|fil-|kesella|cottage|ägg|agg-", re.I)


def discover(cl, log):
    idx = cl.get(BASE + "/produkt/sitemaps/")
    urls = []
    for sm in sitemap_locs(idx or ""):
        if "/products/" in sm:
            t = cl.get(sm)
            if t:
                urls += sitemap_locs(t)
    urls = list(dict.fromkeys(u for u in urls if "/produkt/" in u))
    pri = [u for u in urls if PRIORITY.search(u)]
    rest = [u for u in urls if not PRIORITY.search(u)]
    log(f"sitemap product urls {len(urls)} (priority {len(pri)})")
    return pri + rest


def scrape(cl, url):
    t = cl.get(url)
    if not t:
        return None
    prods = jsonld(t, "Product")
    p = prods[0] if prods else {}
    crumbs = [one(x) for x in re.findall(r'<a[^>]*class="breadcrumbs__link"[^>]*>(.*?)</a>', t, re.S)]
    crumbs = [c for c in dict.fromkeys(crumbs) if c and c not in ("Start", "Produkter")]
    tables = []
    text_block = False
    m = re.search(r'accordion__label__title__text__title">Näringsvärde</span>(.*?)(?=accordion__label__title__text__title">|$)', t, re.S)
    if m:
        seg = m.group(1)
        tm = re.search(r"<table.*?</table>", seg, re.S)
        if tm:
            tb = tm.group(0)
            head = re.search(r"<tr><th[^>]*>(.*?)</th><th[^>]*>(.*?)</th>", tb, re.S)
            header = one(head.group(2)) if head else ""
            rows = []
            for tr in re.findall(r"<tr>(.*?)</tr>", tb, re.S):
                tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
                if len(tds) >= 2:
                    rows.append((one(tds[0]), one(tds[1])))
            tables.append((header, rows))
        else:
            pm = re.search(r'product-accordions__text[^>]*>(.*?)</div>', seg, re.S)
            if pm:
                txt = one(pm.group(1))
                rows = []
                for lab, val in re.findall(r"([A-Za-zÅÄÖåäöéÉ][A-Za-zÅÄÖåäöéÉ ()/-]*?)\s+([<>]?\d[\d.,]*\s*(?:kJ|kcal|g|mg|µg|ug|mcg|IU|%)(?![A-Za-z]))", txt):
                    rows.append((lab.strip(), val.strip()))
                if rows:
                    text_block = True
                    tables.append(("Näringsvärde (free-text block from supplier, basis not stated)", rows))
    ing = None
    m = re.search(r'accordion__label__title__text__title">Ingredienser</span>.*?product-accordions__content[^>]*>(.*?)</div>', t, re.S)
    if m:
        ing = one(m.group(1)) or None
    pd = re.search(r'"productData":\{"consumerItemId":"(\d+)","displayName":"([^"]*)"', t)
    vol = re.search(r'"volume":"([^"]+)"', t)
    rec_n = tables_to_record(tables, numfix=sv_numbers)
    if not tables and not p:
        return None
    ean = common.norm_ean(p.get("gtin"))
    if ean and len(ean) == 14 and ean.startswith("0"):
        ean = ean[1:]
    b = p.get("brand")
    off = p.get("offers") or {}
    if isinstance(off, list):
        off = off[0] if off else {}
    # header like '100 Gram' / '100 Milliliter' => per_100 (classify_header knows 'gram' / 'ml'); also accept 'milliliter'
    for tb in (rec_n.get("nutrition") or {}).get("tables", []):
        if tb["basis"] == "unknown" and re.match(r"\s*100\s*(milliliter|gram|g|ml)", tb["header"], re.I):
            tb["basis"] = "per_100"
    if rec_n["nutrition"] and rec_n["nutrition_flag"] == "basis_unverified_assumed_per_100":
        for tb in rec_n["nutrition"]["tables"]:
            if tb["basis"] == "per_100":
                rec_n["nutrition_per100"] = tb["values"]
                rec_n["nutrition_flag"] = None
                break
    rec = {"name": html.unescape(p.get("name") or (pd.group(2) if pd else "")), "brand": b.get("name") if isinstance(b, dict) else b,
           "ean": ean, "ica_id": pd.group(1) if pd else None, "pack_size_raw": vol.group(1) if vol else None,
           "price_sek": off.get("price"), "categories": crumbs, "ingredients": ing,
           "nutrition_basis_header": tables[0][0] if tables else None, "nutrition_from_text_block": text_block}
    rec.update(rec_n)
    return rec


def refetch():
    """Re-fetch records saved earlier with no_nutrition_table (the first parser missed the free-text block layout)."""
    log = common.Logger("ica-se")
    cl = common.Client("ica-se", log)
    path = common.out_paths("ica-se")
    recs = [json.loads(l) for l in open(path, encoding="utf8")]
    todo = [i for i, r in enumerate(recs) if r.get("nutrition_flag") == "no_nutrition_table" and not r.get("refetched")]
    log(f"REFETCH {len(todo)} of {len(recs)} records")
    fixed = 0
    try:
        for n, i in enumerate(todo, 1):
            u = recs[i]["source_url"]
            new = scrape(cl, u)
            recs[i]["refetched"] = True
            if new and new.get("nutrition"):
                new.update({"source": "ica-se", "source_url": u, "fetched_on": common.today(), "refetched": True})
                recs[i] = new
                fixed += 1
            if n % 200 == 0:
                tmp = path + ".tmp"
                with open(tmp, "w", encoding="utf8") as f:
                    for r in recs:
                        f.write(json.dumps(r, ensure_ascii=False) + chr(10))
                os.replace(tmp, path)
                log(f"refetch progress {n}/{len(todo)} fixed={fixed}")
    except common.Blocked as e:
        log(f"BLOCKED: {e}")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + chr(10))
    os.replace(tmp, path)
    log(f"END refetch fixed={fixed} of {len(todo)} requests={cl.requests_made}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--refetch":
        refetch()
        sys.exit(0)
    mp = int(sys.argv[1]) if len(sys.argv) > 1 else None
    hrs = float(sys.argv[2]) if len(sys.argv) > 2 else None
    log = common.Logger("ica-se")
    cl = common.Client("ica-se", log)
    urls = discover(cl, log)
    if mp:
        urls = urls[:mp]
    run_big("ica-se", urls, scrape, max_seconds=hrs * 3600 if hrs else None)
