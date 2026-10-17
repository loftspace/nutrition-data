"""Danish Food Composition Database (Frida) v6.1, DTU Food Institute, CC BY 4.0. Converts the official xlsx
(figshare DOI 10.11583/DTU.32312844, downloaded with curl) into products.jsonl. Values per 100 g edible part."""
import openpyxl, json, datetime, sys
ROOT = "C:/Users/Admin/Documents/Claude/zz-Misc/macro-library"
D = ROOT + "/data/raw/frida-dk/"
wb = openpyxl.load_workbook(D + "_download/FCDB_6.1_Dataset.xlsx", read_only=True)


def rows(name):
    it = wb[name].iter_rows(values_only=True)
    h = next(it)
    for r in it:
        yield dict(zip(h, [None if v == "NULL" else v for v in r]))


params = {str(p["ParameterID"]): p for p in rows("Parameter")}
foods = {str(f["FoodID"]): f for f in rows("Food")}
nut = {}
for r in rows("Data_Normalised"):
    if r["ResVal"] is None:
        continue
    p = params.get(str(r["ParameterID"]), {})
    nut.setdefault(str(r["FoodID"]), {})[str(r["ParameterID"])] = {
        "label": r["ParameterName"], "label_da": r["ParameterNavn"], "value": float(r["ResVal"]), "unit": p.get("Unit"),
        "eurofir": p.get("EurofirComponentID"), "min": r["Min"], "max": r["Max"], "n_determinations": r["NumberOfDeterminations"],
        "source_ref": r["Source"]}
n = 0
today = datetime.date.today().isoformat()
with open(D + "products.jsonl", "w", encoding="utf-8") as o:
    for fid, f in foods.items():
        nn = nut.get(fid, {})
        rec = {"source": "frida-dk", "source_id": fid, "name": f["FødevareNavn"], "name_en": f["FoodName"],
               "name_scientific": f.get("TaxonomicName"), "food_group": f.get("FoodGroup"), "food_group_da": f.get("FødevareGruppe"),
               "langual": f.get("LangualCode"), "brand": None, "ean": None, "pack_size": None, "per": "100 g edible part (see unit per nutrient)",
               "nutrients": nn, "source_url": "https://frida.fooddata.dk/food/" + fid, "fetched_on": today,
               "license": "CC BY 4.0 (DTU Food Institute, Frida v6.1)"}
        o.write(json.dumps(rec, ensure_ascii=False) + "\n"); n += 1
msg = f"frida: {n} foods, {sum(1 for v in nut.values() if '356' in v)} with kcal"
print(msg)
open(ROOT + "/logs/frida-dk.log", "a", encoding="utf-8").write(f"{datetime.datetime.now().isoformat(timespec='seconds')} {msg}; 0 live requests beyond the 3 curl downloads\n")
