"""Kassalapp second pass: category-prioritised, EAN-deduplicated queue. Reuses kassalapp.Mcp. Append only."""
import json, os, re, sys, time, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kassalapp as K

FOOD1 = re.compile(r"protein|whey|kasein|casein|kreatin|creatine|bcaa|gainer|pre-?workout|elektrolytt|isolat|kollagen|collagen|bar-|-bar\b|proteinbar|shake|drink|supplement|vitamin|omega|tran|mineral|magnesium|sink|jern|kosttilskudd|pulver|"
    r"melk|yoghurt|yogurt|skyr|kesam|cottage|rømme|rogn|ost-|-ost\b|ost\b|smør|egg|"
    r"brød|loff|knekkebrød|rundstykke|baguette|tortilla|lefse|"
    r"kylling|kalkun|svin|storfe|okse|lam-|kjøttdeig|kjøttboll|skinke|bacon|pølse|salami|pålegg|biff|filet|karbonade|"
    r"laks|torsk|sei-|makrell|sild|tunfisk|reker|fiskekake|fiskepinne|fiskeboll|ørret|"
    r"müsli|musli|granola|havre|frokostblanding|corn-?flakes|grøt|cruesli|pannekake|"
    r"chips|nøtter|mandler|peanøtt|peanut|cashew|smoothie|snack|sjokolade|kjeks|riskake|popcorn|dadler|tørket", re.I)
def prio(url):
    s = url.split("/vare/")[-1]
    if K.FIRST.search(s): return 0
    if K.NONFOOD.search(s): return 3
    if FOOD1.search(s): return 1
    return 2

def main():
    deadline = time.time() + float(sys.argv[1]) * 3600 if len(sys.argv) > 1 else 1e18
    os.makedirs(K.OUT, exist_ok=True)
    done_ids, done_ean = set(), set()
    for p in (K.PROD, K.FAIL):
        if os.path.exists(p):
            for l in open(p, encoding="utf-8"):
                try:
                    d = json.loads(l); done_ids.add(d["product_id"])
                    if d.get("ean"): done_ean.add(d["ean"])
                except Exception: pass
    seen = set(); todo = []
    for pid, ean, url in K.load_urls():
        if pid in done_ids: continue
        if ean and (ean in done_ean or ean in seen): continue
        if ean: seen.add(ean)
        todo.append((prio(url), pid, ean, url))
    todo.sort(key=lambda t: (t[0], t[1]))
    from collections import Counter
    K.log(f"PRIO start: todo={len(todo)} by prio={dict(Counter(t[0] for t in todo))} done={len(done_ids)}")
    m = K.Mcp(); today = datetime.date.today().isoformat(); n = ok = 0
    pf = open(K.PROD, "a", encoding="utf-8"); ff = open(K.FAIL, "a", encoding="utf-8")
    for pr, pid, ean, url in todo:
        if time.time() > deadline: break
        if pr == 3: break  # skip obvious non-food entirely
        d, err = m.call("get_product", {"product_id": pid})
        if d is None:
            ff.write(json.dumps({"product_id": pid, "url": url, "error": err}, ensure_ascii=False) + "\n"); ff.flush()
        else:
            nut = K.parse_nutrition(d.get("nutrition"))
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
            pf.write(json.dumps(rec, ensure_ascii=False) + "\n"); pf.flush(); ok += 1
        n += 1
        if n % 200 == 0:
            K.log(f"PRIO progress {n}/{len(todo)} ok={ok} prio={pr} calls={m.calls}")
    K.log(f"PRIO end: processed={n} ok={ok} calls={m.calls}")

if __name__ == "__main__": main()
