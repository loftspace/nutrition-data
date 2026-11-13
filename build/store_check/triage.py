"""Turn workflow results into nutrition-data/data/checked.json.

Only fixes a second agent confirmed are used (with its corrected values). Store-brand folds are checked here
in code against the live database (kcal, protein, fat within 15% or 0.5). Everything left out is written
to triage_report.json with the reason.

Usage: python -I triage.py <journal.jsonl> [<journal.jsonl> ...] --store <store_brand_verdicts.json> --out <checked.json>
"""
import json, os, re, sqlite3, sys, collections
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
db = sqlite3.connect(os.environ["MAKRO_DB"])
NUT = ("kcal", "protein_g", "fat_g", "sat_fat_g", "carbs_g", "sugars_g", "fibre_g", "salt_g")
ALIAS = {"kcal": "kcal", "energy_kcal": "kcal", "kalorier": "kcal", "protein": "protein_g", "protein_g": "protein_g",
         "fat": "fat_g", "fat_g": "fat_g", "fett": "fat_g", "sat_fat": "sat_fat_g", "sat_fat_g": "sat_fat_g",
         "saturated_fat_g": "sat_fat_g", "mettet_fett": "sat_fat_g", "carbs": "carbs_g", "carbs_g": "carbs_g",
         "carbohydrates_g": "carbs_g", "karbohydrater": "carbs_g", "sugars": "sugars_g", "sugars_g": "sugars_g",
         "sugar_g": "sugars_g", "sukkerarter": "sugars_g", "fibre": "fibre_g", "fibre_g": "fibre_g", "fiber_g": "fibre_g",
         "kostfiber": "fibre_g", "salt": "salt_g", "salt_g": "salt_g"}
CATS = {"dairy_eggs", "meat_fish", "bread_cereal_grain", "fruit_vegetables", "drinks", "snacks_sweets",
        "ready_meals_sauces", "protein_drink_or_dessert", "other_food", "protein_bar", "protein_powder", "energy_gel_sports_drink"}
SIZE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(kg|g|l|ltr|liter|dl|cl|ml)\s*$", re.I)
UNIT_OUT = {"kg": "kg", "g": "g", "l": "L", "ltr": "L", "liter": "L", "dl": "dl", "cl": "cl", "ml": "ml"}
FACT = {"kg": 1000, "g": 1, "l": 1000, "ltr": 1000, "liter": 1000, "dl": 100, "cl": 10, "ml": 1}

report = collections.defaultdict(list)


def row(i):
    r = db.execute("select id,name,brand,kcal,protein_g,fat_g,carbs_g,salt_g,per_100_unit,verified,source from products where id=?", (i,)).fetchone()
    return dict(zip(("id", "name", "brand", "kcal", "protein_g", "fat_g", "carbs_g", "salt_g", "unit", "verified", "source"), r)) if r else None


def num(v):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        m = re.match(r"^\s*(\d+(?:[.,]\d+)?)", v)
        return float(m.group(1).replace(",", ".")) if m else None
    return None


def nutrients(d, keep_null=False):
    """keep_null: an explicit null from a checker means the label does not give the value (unknown)."""
    out = {}
    for k, v in (d or {}).items():
        k2 = ALIAS.get(str(k).lower().strip())
        n = num(v) if not isinstance(v, dict) else None
        if k2 and n is not None:
            out[k2] = n
        elif k2 and v is None and keep_null:
            out[k2] = None
    return out


def sizes(lst, unit):
    out, seen = [], set()
    for s in lst or []:
        m = SIZE.match(str(s))
        if not m:
            continue
        u = m.group(2).lower()
        fam = "g" if u in ("kg", "g") else "ml"
        if unit and fam != unit:
            continue
        amt = float(m.group(1).replace(",", ".")) * FACT[u]
        if amt in seen or amt <= 0:
            continue
        seen.add(amt)
        out.append((amt, f"{m.group(1).replace('.', ',')} {UNIT_OUT[u]}"))
    return [t for _, t in sorted(out)][:6]


def close(a, b, rel=0.15, absol=0.5):
    if a is None or b is None:
        return False
    return abs(a - b) <= max(absol, rel * max(abs(a), abs(b)))


def source_of(url):
    h = urlparse(url or "").netloc.lower()
    for key, slug in (("meny", "norgesgruppen"), ("spar", "norgesgruppen"), ("joker", "norgesgruppen"), ("ngdata", "norgesgruppen"),
                      ("oda.com", "oda"), ("coop.no", "coop-no"), ("rema.no", "rema-no"), ("kassal", "kassalapp")):
        if key in h:
            return slug
    return None


args = sys.argv[1:]
store = args[args.index("--store") + 1]
out_path = args[args.index("--out") + 1]
journals = [a for a in args[:args.index("--store")]]

results = []
for jp in journals:
    for line in open(jp, encoding="utf-8"):
        e = json.loads(line)
        if e.get("type") == "result" and isinstance(e.get("result"), dict):
            results.append(e["result"])
sweeps = [r for r in results if "products" in r]
# Pair verify results with sweeps: the workflow's final return holds both, but the journal has them apart.
# Rebuild the fix list the same way the workflow did and match by group order of appearance.
verifies = [r for r in results if "checked" in r]

fixes_all = []  # (group, fix dict, verdict)
final_path = os.environ.get("FINAL")
if final_path:
    final = json.load(open(final_path, encoding="utf-8"))["result"]
    for g in final["swept"]:
        verdicts = {v["index"]: v for v in (g.get("verdicts") or [])}
        label = {(p.get("name"), p.get("brand")): p for p in g["sweep"]["products"]}
        for i, f in enumerate(g.get("fixes") or []):
            prod = label.get((f.get("product"), f.get("brand"))) or {}
            f = dict(f, label=prod.get("per100"))
            fixes_all.append((g["group"], f, verdicts.get(i)))
    # Round-2 re-checks (Sonnet): {"group","fix","verdict"} lines, same shape.
    for extra in os.environ.get("RECHECK", "").split(os.pathsep):
        if extra and os.path.exists(extra):
            for line in open(extra, encoding="utf-8"):
                e = json.loads(line)
                fixes_all.append((e["group"], e["fix"], e["verdict"]))
        sweeps_g = g["sweep"]
else:
    raise SystemExit("set FINAL to the workflow output file")

fixes, folds, adds, drops = {}, {}, {}, {}
common = {}


def merge_fix(i, key, val, why):
    f = fixes.setdefault(i, {"id": i})
    if key == "nutrients":
        cur = f.setdefault("nutrients", {})
        for k, v in val.items():
            if k in cur and cur[k] != v and (cur[k] is None or v is None or not close(cur[k], v, 0.02, 0.05)):
                report["conflict"].append({"id": i, "field": k, "a": cur[k], "b": v})
                cur.pop(k)
                continue
            cur[k] = v
    elif key in f and f[key] != val:
        report["conflict"].append({"id": i, "field": key, "a": f[key], "b": val})
    else:
        f[key] = val
    f.setdefault("source_url", why)


for group, f, v in fixes_all:
    kind = f.get("kind")
    if not v or not v.get("confirmed"):
        report["not_confirmed"].append({"group": group, "kind": kind, "product": f.get("product"), "why": (v or {}).get("reason")})
        continue
    fields = dict(f.get("fields") or {})
    if v.get("corrected_fields"):
        fields.update(v["corrected_fields"])
    i = f.get("db_id") or ""
    r = row(i) if i else None
    url = f.get("source_url") or ""
    if kind == "numbers":
        if not r:
            report["gone"].append(f); continue
        n = nutrients(fields, keep_null=True)
        if not n or not url:
            report["empty"].append(f); continue
        # Take the whole label, so a row never mixes two labels (macros from one, kcal from another).
        full = nutrients(f.get("label"))
        full.update(n)
        n = full
        if n.get("kcal") is None and any(k in n for k in ("protein_g", "fat_g", "carbs_g")):
            report["label_without_kcal"].append({"id": i, "n": n}); continue
        if all(n.get(k) is not None for k in ("kcal", "protein_g", "fat_g", "carbs_g")):
            calc = 4 * n["protein_g"] + 4 * n["carbs_g"] + 9 * n["fat_g"]
            if abs(calc - n["kcal"]) > max(20, 0.15 * n["kcal"]):
                report["label_does_not_add_up"].append({"id": i, "n": n}); continue
        if r["verified"] and r["source"] not in ("norgesgruppen", "kassalapp", "openfoodfacts", "openfoodfacts-nordic-global"):
            # A brand's own page against a shop page: keep it for a person to look at.
            report["brand_row_numbers"].append({"id": i, "name": r["name"], "ours": {k: r.get(k) for k in n}, "shop": n, "url": url})
            continue
        merge_fix(i, "nutrients", n, url)
    elif kind == "sizes":
        if not r:
            report["gone"].append(f); continue
        have = [x.strip() for x in (db.execute("select pack_size from products where id=?", (i,)).fetchone()[0] or "").split(", ")]
        s = sizes(list(fields.get("sizes") or f.get("sizes") or []) + have, r["unit"])
        if s and s != sizes(have, r["unit"]):
            merge_fix(i, "sizes", s, url or "store listing")
    elif kind == "rename":
        if r and fields.get("name"):
            merge_fix(i, "name", str(fields["name"]).strip(), url or "store listing")
    elif kind == "category":
        c = fields.get("category")
        if r and c in CATS:
            merge_fix(i, "category", c, url or "store listing")
    elif kind in ("merge_duplicates", "fold_store_generic"):
        if not r:
            report["gone"].append(f); continue
        for o in f.get("other_ids") or []:
            ro = row(o)
            if not ro or o == i:
                continue
            if all(close(ro[k], r[k]) for k in ("kcal", "protein_g", "fat_g")):
                folds[o] = {"id": o, "into": i, "why": f"{kind}: {ro['name']} -> {r['name']}"}
            else:
                report["fold_numbers_apart"].append({"id": o, "into": i, "a": ro["name"], "b": r["name"]})
    elif kind == "add_product":
        n = nutrients(f.get("per100") or fields.get("per100") or fields)
        eans = [e for e in (f.get("eans") or []) if re.fullmatch(r"\d{8,14}", str(e))]
        src = source_of(url)
        if any(n.get(k) is None for k in ("kcal", "protein_g", "fat_g", "carbs_g")) or not eans or not src:
            report["add_incomplete"].append({"product": f.get("product"), "eans": eans, "src": src, "n": n}); continue
        taken = [e for e in eans if db.execute("select 1 from product_eans where ean=?", (e.zfill(13) if len(e) < 13 else e,)).fetchone()]
        if taken:
            report["add_barcode_exists"].append({"product": f.get("product"), "eans": taken}); continue
        unit = "ml" if any(re.search(r"(ml|cl|dl|\bl\b|liter)", str(s), re.I) for s in f.get("sizes") or []) else "g"
        aid = f"store:{eans[0]}"
        adds[aid] = {"id": aid, "name": f.get("product"), "brand": f.get("brand"), "category": fields.get("category") if fields.get("category") in CATS else "other_food",
                     "unit": unit, "sizes": sizes(f.get("sizes"), unit), "eans": eans, "source": src,
                     "nutrients": {k: n.get(k) for k in NUT if n.get(k) is not None}, "source_url": url}

# Common: from every sweep (no verify needed: a rating, not a number).
TIER = {5: 3, 4: 2, 3: 1}
for g in final["swept"]:
    for p in g["sweep"]["products"]:
        t = TIER.get(p.get("commonness"))
        if not t:
            continue
        for i in p.get("db_ids") or []:
            if row(i):
                common[i] = max(common.get(i, 0), t)

# Duplicate groups (round 2, Sonnet), guarded in code: same product numbers within 10%.
dpath = os.environ.get("DUPS")
if dpath:
    for g in json.load(open(dpath, encoding="utf-8")):
        k = row(g["keep_id"])
        for o in g["fold_ids"]:
            ro = row(o)
            if not k or not ro or o == k["id"]:
                continue
            if all(close(ro[x], k[x], 0.10) for x in ("kcal", "protein_g", "fat_g", "carbs_g")):
                folds.setdefault(o, {"id": o, "into": k["id"], "why": f"duplicate: {ro['name']} -> {k['name']}"})
            else:
                report["dup_numbers_apart"].append({"id": o, "into": k["id"]})

# Store-brand folds and drops (checked here in code).
for v in json.load(open(store, encoding="utf-8")):
    if v["verdict"] == "fold":
        a, b = row(v["id"]), row(v.get("into_id") or "")
        if a and b and all(close(a[k], b[k]) for k in ("kcal", "protein_g", "fat_g")):
            folds.setdefault(v["id"], {"id": v["id"], "into": b["id"], "why": f"store label: {a['name']} -> {b['name']}"})
        else:
            report["store_fold_rejected"].append(v)
    elif v["verdict"] == "drop_junk" and row(v["id"]):
        drops[v["id"]] = {"id": v["id"], "why": v["reason"]}

# Fold chains: point at the final row; drop cycles and folds into dropped rows.
for o in list(folds):
    seen, t = {o}, folds[o]["into"]
    while t in folds and t not in seen:
        seen.add(t)
        t = folds[t]["into"]
    if t in seen or t in drops:
        report["fold_cycle_or_dropped"].append(folds.pop(o))
    else:
        folds[o]["into"] = t
for o in folds:
    fixes.pop(o, None)
    common.pop(o, None)
for d in drops:
    fixes.pop(d, None)
    common.pop(d, None)
# A fix with neither nutrients, sizes, name nor category is nothing.
fixes = {i: f for i, f in fixes.items() if any(k in f for k in ("nutrients", "sizes", "name", "category"))}
for f in fixes.values():
    if f.get("nutrients") == {}:
        f.pop("nutrients")
for a in adds.values():
    t = max((common.get(a["id"], 0),), default=0)

out = {
    "note": "Store-checked fixes, Max 2026-11-12. Agents read Meny, Spar, Joker, Oda, Coop, Rema 1000 and kassal.app pages; a second agent re-read the source for every fix. See tools/checked.py.",
    "checked": "2026-11-12",
    "fixes": sorted(fixes.values(), key=lambda f: f["id"]),
    "fold": sorted(folds.values(), key=lambda f: f["id"]),
    "drop": sorted(drops.values(), key=lambda f: f["id"]),
    "add": sorted(adds.values(), key=lambda f: f["id"]),
    "common": dict(sorted(common.items())),
}
json.dump(out, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(report, open(os.path.join(HERE, "triage_report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print({k: len(v) for k, v in out.items() if isinstance(v, (list, dict))})
print({k: len(v) for k, v in report.items()})
