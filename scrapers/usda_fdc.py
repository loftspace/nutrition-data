"""USDA FoodData Central: Foundation + SR Legacy fully; Branded filtered to supplement/protein brands, Nordic brands and
supplement categories. Works from the official bulk CSV zips (public domain, CC0) unzipped in data/raw/usda-fdc/_download/."""
import csv, json, re, os, datetime, glob
csv.field_size_limit(10**9)
ROOT = "C:/Users/Admin/Documents/Claude/zz-Misc/macro-library"
D = ROOT + "/data/raw/usda-fdc/"; X = D + "_download/"
TODAY = datetime.date.today().isoformat()


def rd(p):
    return csv.DictReader(open(p, encoding="utf-8", newline=""))


def folder(prefix):
    return glob.glob(X + f"x_FoodData_Central_{prefix}*/FoodData_Central_*/")[0]


nutdef = {}


def load_nutdefs(f):
    for r in rd(f + "nutrient.csv"):
        nutdef[r["id"]] = r


BRANDS = [
    "optimum nutrition", "myprotein", "my protein", "dymatize", "muscletech", "muscle tech", r"\bbsn\b", "cellucor", r"\bghost\b",
    "isopure", "orgain", r"\bquest\b", "premier protein", "premier nutrition", "muscle milk", "gaspari", "universal nutrition",
    "transparent labs", "legion", "garden of life", r"\bvega\b", "now foods", "rule 1", "rule one", "kaged", r"\bjym\b", "musclepharm",
    "muscle pharm", "met-rx", "metrx", "labrada", "allmax", "six star", "pure protein", "fitcrunch", "barebells", "grenade", "nick'?s",
    "weider", "olimp", "scitec", "sci-mx", r"\bphd\b", r"\busn\b", "applied nutrition", "maxler", "nutrex", "evlution", "redcon1",
    "alani", "bloom nutrition", "fairlife", "oikos", "glanbia", "body ?armor", "bulk powders", "gnc", "general nutrition",
    "vital proteins", "designer protein", "designer whey", "naked nutrition", "ascent", "momentous", "nutrabolt", "nordic naturals",
    "carlson", "solgar", "thorne", "life extension", "swanson", "nature made", "centrum", "bpi sports", "promix", "sunwarrior",
    "trec nutrition", "biotech usa", "atkins", "ensure", "abbott nutrition", "isagenix", "herbalife", "shakeology", "huel", "soylent",
    r"\btine\b", "q-meieriene", "nortura", "gilde", r"\bprior\b", "orkla", "freia", "m.llerens", "stabburet", r"\btoro\b", "maarud",
    r"\bolw\b", "fjordland", "lerum", r"\bidun\b", "grandiosa", r"\barla\b", "oatly", r"\bwasa\b", "wasabrod", "kavli", "lantm.nnen",
    "santa maria", "findus", "nidar", "nordic", "norweg", "norsk", "norway", "sweden", "swedish", "denmark", "danish", "finland",
    "finnish", "iceland", r"\bskyr\b", "siggi", "ryvita", "leksands", "p.gen", "lofoten", "mowi", "salmar", "ler.y",
]
BRE = re.compile("|".join(BRANDS), re.I)
CATS = re.compile(r"supplement|vitamin|protein|muscle|sport|weight|meal replacement|energy|amino|fatty acid|formula|nutritional|green|fiber", re.I)
NOT_CATS = re.compile(r"snack|candy|cereal|bread|cookie|chip", re.I)
log = open(ROOT + "/logs/usda-fdc.log", "a", encoding="utf-8")


def L(m):
    log.write(f"{datetime.datetime.now().isoformat(timespec='seconds')} {m}\n"); log.flush(); print(m, flush=True)


def nutrients_for(f, want):
    by = {}
    for r in rd(f + "food_nutrient.csv"):
        if r["fdc_id"] in want:
            nd = nutdef.get(r["nutrient_id"], {})
            by.setdefault(r["fdc_id"], {})[nd.get("nutrient_nbr") or r["nutrient_id"]] = {
                "label": nd.get("name"), "value": float(r["amount"]) if r["amount"] != "" else None,
                "unit": nd.get("unit_name"), "usda_nutrient_id": r["nutrient_id"]}
    return by


def run(kind, prefix, out, branded=False):
    f = folder(prefix); load_nutdefs(f)
    foods = {r["fdc_id"]: r for r in rd(f + "food.csv")}
    extra = {}
    if branded:
        for r in rd(f + "branded_food.csv"):
            b = r["brand_owner"] + " | " + r["brand_name"] + " | " + r["subbrand_name"]
            desc = foods.get(r["fdc_id"], {}).get("description", "")
            cat = r["branded_food_category"]
            if BRE.search(b) or (CATS.search(cat) and not NOT_CATS.search(cat)) or re.search(r"protein powder|whey|creatine|casein|bcaa", desc, re.I):
                extra[r["fdc_id"]] = r
        ids = set(extra)
        L(f"branded filter kept {len(ids)} of {len(foods)}")
    else:
        ids = {i for i, r in foods.items() if r["data_type"] in ("foundation_food", "sr_legacy_food")}
    by = nutrients_for(f, ids)
    cats = {r["id"]: r["description"] for r in rd(f + "food_category.csv")} if os.path.exists(f + "food_category.csv") else {}
    portions = {}
    if os.path.exists(f + "food_portion.csv") and not branded:
        for r in rd(f + "food_portion.csv"):
            portions.setdefault(r["fdc_id"], []).append({k: r[k] for k in ("amount", "gram_weight", "portion_description", "modifier") if k in r})
    n = withk = 0
    with open(out, "w", encoding="utf-8") as o:
        for i in sorted(ids, key=int):
            fr = foods[i]; b = extra.get(i)
            nut = by.get(i, {})
            rec = {"source": "usda-fdc", "dataset": kind, "source_id": i, "name": fr["description"],
                   "category": cats.get(fr.get("food_category_id")) or (b or {}).get("branded_food_category"),
                   "brand": ((b or {}).get("brand_name") or (b or {}).get("brand_owner") or None),
                   "brand_owner": (b or {}).get("brand_owner"), "ean": (b or {}).get("gtin_upc") or None,
                   "pack_size": (b or {}).get("package_weight") or None, "serving_size": (b or {}).get("serving_size"),
                   "serving_unit": (b or {}).get("serving_size_unit"), "household_serving": (b or {}).get("household_serving_fulltext"),
                   "ingredients": (b or {}).get("ingredients"), "market_country": (b or {}).get("market_country"),
                   "per": "100 g (branded: per 100 g or 100 ml as listed by USDA)", "nutrients": nut, "portions": portions.get(i),
                   "source_url": f"https://fdc.nal.usda.gov/food-details/{i}/nutrients", "fetched_on": TODAY,
                   "publication_date": fr.get("publication_date"), "license": "CC0 / public domain (USDA)"}
            if any(k in nut for k in ("208", "957", "958")): withk += 1
            o.write(json.dumps(rec, ensure_ascii=False) + "\n"); n += 1
    L(f"{kind}: {n} records, {withk} with kcal(208) -> {out}")
    return n


L("start (bulk CSV processing; downloads done via curl at 1 req/s, honest UA)")
run("foundation", "foundation_food_csv", D + "foundation.jsonl")
run("sr_legacy", "sr_legacy_food_csv", D + "sr_legacy.jsonl")
run("branded_filtered", "branded_food_csv", D + "branded_filtered.jsonl", True)
L("done")
