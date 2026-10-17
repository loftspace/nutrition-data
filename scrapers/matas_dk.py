#!/usr/bin/env python
"""Matas.dk food / supplement products. Product sitemap (80k urls, mostly cosmetics) is filtered by slug
keywords (supplements, protein, bars, health food brands); each page's embedded ProductPage model carries a
Nutrients tab. Only pages with a nutrition table are saved. Usage: python matas_dk.py [max_pages] [max_hours]"""
import re, sys, os, json, html
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nordic import *
import common

BASE = "https://www.matas.dk"
SUP = re.compile(r"protein|whey|kreatin|creatine|vitamin|omega|magnesium|collagen|kollagen|elektrolyt|workout|aminosyre|bcaa|probiot|fiskeolie|gainer|nutramino|barebells|nupo|foodspring|bodylab|star-nutrition|healthwell|solgar|linuspro|naturesource|nutri|zink|jern", re.I)
KW = re.compile(r"protein|whey|kreatin|creatine|vitamin|kosttilskud|omega|magnesium|collagen|kollagen|elektrolyt|pre-?workout|aminosyre|bcaa|eaa-|-bar-|-bar$|shake|probiot|-jern-|-zink-|fiskeolie|gainer|musli|granola|havre|cacao|kakao|nutramino|barebells|nupo|foodspring|bodylab|star-nutrition|healthwell|solgar|linuspro|naturesource|urtekram|pukka|nu3|more-nutrition|ostrovit|optimum|myprotein|nano-?supps|nordic-?naturals|new-?nordic|biosym|pharma-?nord|burgerstein|nødde|mandel|peanut|jordnød|honning|sirup|sukkerfri|snack|chips|-te-|kaffe|drik|smoothie|energy|sportsern|måltid|maaltid|glutenfri|grød|vegansk|nutri|zink|jern|d3|b12|c-vitamin|multi", re.I)


NEG = re.compile(r"serum|shampoo|conditioner|creme|cream|parfum|perfume|mascara|lipstick|lip-|eyeshadow|foundation|cosmetics|revlon|nilens|hair|haar|tandpasta|deodorant|lotion|maske|mask-|sunscreen|solcreme|brush|shaker|nail|neglelak|concealer|facial|ansigt|body-wash|shower|sæbe|soap|spray|gel$|-gel-|olie-til|massage|bluse|jakke|sok|bamse|legetoej", re.I)


def discover(cl, log):
    idx = cl.get(BASE + "/sitemap")
    urls = []
    for sm in sitemap_locs(idx or ""):
        if sm.rstrip("/").endswith("/product"):
            sub = cl.get(sm)
            for s2 in sitemap_locs(sub or ""):
                t = cl.get(s2)
                if t:
                    urls += sitemap_locs(t)
    urls = list(dict.fromkeys(urls))
    kw = [u for u in urls if KW.search(u[len(BASE):]) and not NEG.search(u[len(BASE):])]
    sup = [u for u in kw if SUP.search(u[len(BASE):])]
    rest = [u for u in kw if u not in set(sup)]
    log(f"sitemap product urls {len(urls)}; keyword candidates {len(kw)} (supplement-first {len(sup)})")
    return sup + rest


def model_of(t):
    i = t.find("Components.ProductPage, ")
    if i < 0:
        return None
    try:
        return json.JSONDecoder().raw_decode(t[i + len("Components.ProductPage, "):])[0]["model"]
    except Exception:
        return None


def rows_to_tables(rows):
    tables, head, cur = [], "", []
    for r in rows:
        vals = [c.get("value") for c in r]
        if len(r) == 1 or (len(r) >= 1 and r[0].get("colspan", 1) >= 2):
            if cur:
                tables.append((head, cur))
            head, cur = one(vals[0] or ""), []
        elif len(vals) >= 2:
            cur.append((one(vals[0] or ""), one(vals[1] or "")))
    if cur:
        tables.append((head, cur))
    return tables


def scrape(cl, url):
    t = cl.get(url)
    if not t:
        return None
    m = model_of(t)
    if not m:
        return None
    pi = m["productInformation"]
    tabs = {tb.get("type"): tb for tb in pi.get("productTabs", [])}
    tables = []
    nt = tabs.get("Nutrients")
    if nt and nt.get("content") and nt["content"].get("rows"):
        tables = rows_to_tables(nt["content"]["rows"])
    dt = tabs.get("Dosage")
    if dt and dt.get("content", {}).get("productTabTableModels"):
        for mdl in dt["content"]["productTabTableModels"]:
            hd = mdl.get("tableHeaders") or []
            rows = []
            for r in mdl.get("rows", []):
                vals = [one(c.get("value") or "") for c in r]
                if len(vals) >= 2:
                    rows.append((vals[0], vals[1]))
            if rows:
                tables.append(((hd[0] + ": " + hd[1]) if len(hd) > 1 else (hd[0] if hd else "Indhold pr. daglig dosis"), rows))
    desc_html = ""
    d = tabs.get("Description")
    if d and d.get("content", {}).get("blockList"):
        desc_html = " ".join(b.get("content") or "" for b in d["content"]["blockList"].get("blocks", []))
    if not tables and "<table" in desc_html:
        for tm in re.finditer(r"<table.*?</table>", desc_html, re.S):
            rows = [[one(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S)] for tr in re.findall(r"<tr.*?</tr>", tm.group(0), re.S)]
            if len(rows) > 1 and len(rows[0]) >= 2:
                hdr = " ".join(rows[0][1:2])
                tables.append((hdr, [(r[0], r[1]) for r in rows[1:] if len(r) >= 2]))
        src_note = "nutrition parsed from description html table"
    if not tables:
        return None
    ing = None
    it = tabs.get("Ingredients")
    if it:
        ing = " ".join(one(b.get("content") or "") for b in it["content"].get("blocks", [])) or None
    spec = {}
    st = tabs.get("Details")
    if st and st.get("content", {}).get("rows"):
        for r in st["content"]["rows"]:
            if len(r) >= 2:
                spec[one(r[0].get("value") or "")] = one(r[1].get("value") or "")
    sd = (m.get("serializedStructuredData") or [{}])[0]
    ean = common.norm_ean(sd.get("gtin13") or sd.get("gtin") or (sd.get("hasVariant") or [{}])[0].get("gtin13") if isinstance(sd.get("hasVariant"), list) else sd.get("gtin13") or sd.get("gtin"))
    if not ean:
        mm = re.search(r'"gtin13":"(\d+)"', t)
        ean = common.norm_ean(mm.group(1)) if mm else None
    brand = (pi.get("brand") or {}).get("name")
    nm = " ".join(l["value"] for l in pi.get("name", {}).get("lines", []) if l.get("type") == "Name")
    price = (pi.get("priceInfo") or {})
    rec = {"name": nm, "brand": brand, "ean": ean, "matas_product_id": pi.get("productId"), "sku": sd.get("sku"),
           "product_group": pi.get("primaryProductGroup"), "pack_size_raw": spec.get("Indhold"), "unit_price_text": spec.get("Enhedspris"),
           "category": spec.get("Kategori"), "ingredients": ing, "description": one(desc_html)[:600], "spec": spec}
    rec.update(tables_to_record(tables))
    return rec


if __name__ == "__main__":
    mp = int(sys.argv[1]) if len(sys.argv) > 1 else None
    hrs = float(sys.argv[2]) if len(sys.argv) > 2 else None
    log = common.Logger("matas-dk")
    cl = common.Client("matas-dk", log)
    urls = discover(cl, log)
    if mp:
        urls = urls[:mp]
    run_big("matas-dk", urls, scrape, max_seconds=hrs * 3600 if hrs else None)
