"""Look a product up in Makro's live product database (2026.11.11, read-only).
Usage:
  python -I match.py ean 7038010016745          -> the row that owns this barcode (and whether it is a redirect)
  python -I match.py q "norvegia lettost"       -> up to 15 rows whose search text has all the words (prefix match)
  python -I match.py id "<product id>"          -> one row by id
Each row: id, name, brand, pack_size, category, verified, source, per-100 numbers, number of barcodes."""
import json, sqlite3, sys, unicodedata, os

DB = os.environ.get("MAKRO_DB") or sys.exit("set MAKRO_DB to a products.sqlite built by tools/build_slim.py")
db = sqlite3.connect(f"file:{os.path.abspath(DB)}?mode=ro", uri=True)
COLS = "id,name,brand,pack_size,category,verified,source,per_100_unit,kcal,protein_g,fat_g,sat_fat_g,carbs_g,sugars_g,fibre_g,salt_g,data_quality"


def norm(s):
    s = s.lower().replace("ø", "o").replace("æ", "ae").replace("å", "a")
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return "".join(c if c.isalnum() or c in "% " else " " for c in s)


def row(r):
    d = dict(zip(COLS.split(","), r))
    d["n_eans"] = db.execute("select count(*) from product_eans where product_id=?", (d["id"],)).fetchone()[0]
    return d


def canon(e):
    e = "".join(c for c in e if c.isdigit())
    if len(e) == 14 and e[0] == "0":
        e = e[1:]
    return e.zfill(13) if len(e) < 13 else e


mode, arg = sys.argv[1], sys.argv[2]
rows = []
if mode == "ean":
    for (pid,) in db.execute("select product_id from product_eans where ean=?", (canon(arg),)):
        rows += [row(r) for r in db.execute(f"select {COLS} from products where id=?", (pid,))]
    if not rows:
        print(json.dumps({"ean": arg, "found": False}))
elif mode == "id":
    rows = [row(r) for r in db.execute(f"select {COLS} from products where id=?", (arg,))]
    if not rows:
        red = db.execute("select new_id from redirects where old_id=?", (arg,)).fetchone()
        print(json.dumps({"id": arg, "found": False, "redirects_to": red[0] if red else None}))
else:
    toks = [t for t in norm(arg).split() if t]
    q = " ".join(f'"{t}"*' for t in toks)
    rows = [row(r) for r in db.execute(
        f"select {COLS} from products where rowid in (select rowid from products_fts where products_fts match ?) limit 15", (q,))]
    if not rows:
        print(json.dumps({"q": arg, "found": False}))
for r in rows:
    print(json.dumps(r, ensure_ascii=True))
