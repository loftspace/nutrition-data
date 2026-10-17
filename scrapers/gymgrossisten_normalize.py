#!/usr/bin/env python
"""Offline normaliser for gymgrossisten products.jsonl (no network).
Reads data/raw/gymgrossisten/products.jsonl (tables_raw) and writes
data/raw/gymgrossisten/nutrition_rows.jsonl: one row per product x variant(flavour) x basis
with a flat macro dict (per 100 g/ml when basis=per_100) plus every other nutrient line as parsed.
"""
import json, re, os, sys, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data", "raw", "gymgrossisten")

NUM = re.compile(r"(<|>|~|ca\.?)?\s*(\d+(?:[.,]\d+)?)\s*(kj|kcal|mcg|µg|μg|ug|mg|g|ml|iu|ie|%)?", re.I)


def fl(x):
    return float(x.replace(",", "."))


def cell(t):
    t = (t or "").strip().replace("\xa0", " ")
    if not t or t in ("-", "–", "—", "*"):
        return None
    out = {"raw": t}
    kj = re.search(r"(\d+(?:[.,]\d+)?)\s*kj", t, re.I)
    kc = re.search(r"(\d+(?:[.,]\d+)?)\s*kcal", t, re.I)
    if kj:
        out["kj"] = fl(kj.group(1))
    if kc:
        out["kcal"] = fl(kc.group(1))
    if kj or kc:
        return out
    m = NUM.search(t)
    if m:
        out["value"] = fl(m.group(2))
        u = (m.group(3) or "").lower().replace("µ", "mc").replace("μ", "mc")
        out["unit"] = {"ug": "mcg", "ie": "iu"}.get(u, u) or None
        if m.group(1) and m.group(1).startswith("<"):
            out["less_than"] = True
    return out


def key(label):
    l = label.lower().strip(" -–:*")
    if re.search(r"mettet|saturat", l): return "saturated_fat_g"
    if re.search(r"enumettet|flerumettet|omega", l): return None
    if re.search(r"sukker|sugar", l): return "sugars_g"
    if re.search(r"polyol", l): return "polyols_g"
    if re.search(r"^energi|^energy|^kalorier", l): return "energy"
    if re.search(r"^fett|^fat", l): return "fat_g"
    if re.search(r"karbo|carb", l): return "carbs_g"
    if re.search(r"fiber|fibre|kostfiber", l): return "fibre_g"
    if re.search(r"^protein", l): return "protein_g"
    if re.search(r"^salt|natrium", l): return "salt_g" if l.startswith("salt") else None
    return None


def basis_from(text):
    l = text.lower()
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(g|ml)\b", l)
    if re.search(r"100\s*(g|ml)", l):
        return "per_100", {"value": 100.0, "unit": "ml" if re.search(r"100\s*ml", l) else "g"}
    if m:
        return "per_serving", {"value": fl(m.group(1)), "unit": m.group(2)}
    if re.search(r"porsjon|serving|dose|kapsel|kapslar|tablett|scoop|skje|stk|dagsdose", l):
        return "per_serving", {"text": text}
    return None, None


def rows_for_table(rows, name_hint=None):
    """Return list of (variant, basis, basis_amount, [(label, parsed)...])"""
    if len(rows) < 2:
        return []
    head, body = rows[0], rows[1:]
    ncols = len(head) - 1
    if ncols < 1:
        return []
    head0 = head[0]
    out = []
    # layout A: first header says per 100 -> columns are variants
    if re.search(r"100\s*(g|ml)", head0, re.I) and not any(re.search(r"100\s*(g|ml)|per", h, re.I) for h in head[1:]):
        b, amt = basis_from(head0)
        for ci in range(1, len(head)):
            out.append((head[ci], b, amt, [(r[0], cell(r[ci])) for r in body if len(r) > ci]))
        return out
    # layout C: column headers carry the basis (Per 100 g | Per 55 g)
    colb = [basis_from(h) for h in head[1:]]
    if all(b[0] for b in colb):
        variant = head0.split(":", 1)[1].strip() if ":" in head0 else None
        for ci, (b, amt) in enumerate(colb, 1):
            out.append((variant, b, amt, [(r[0], cell(r[ci])) for r in body if len(r) > ci]))
        return out
    # layout B: header 'Smak' ; a body row 'Næringsinnhold' lists basis per column
    for ri, r in enumerate(body):
        if re.match(r"n.ringsinn?h", r[0], re.I) and len(r) > 1 and all(basis_from(x)[0] for x in r[1:]):
            rest = body[:ri] + body[ri + 1:]
            for ci in range(1, len(r)):
                b, amt = basis_from(r[ci])
                out.append((head[ci] if ci < len(head) else None, b, amt, [(x[0], cell(x[ci])) for x in rest if len(x) > ci]))
            return out
    # layout D: per-serving table. Column header (or head0) gives serving
    for ci in range(1, len(head)):
        b, amt = basis_from(head[ci])
        if not b:
            b, amt = basis_from(head0)
        if not b:
            b, amt = "per_serving", {"text": head[ci] or head0}
        out.append((None, b, amt, [(r[0], cell(r[ci])) for r in body if len(r) > ci]))
    return out


def normalise(rec):
    res = []
    seen = set()
    for t in rec.get("tables_raw", []):
        for variant, basis, amt, lines in rows_for_table(t["rows"]):
            lines = [(l, c) for l, c in lines if l and c is not None]
            if not lines:
                continue
            sig = (variant, basis, json.dumps(amt, sort_keys=True), json.dumps(lines, sort_keys=True))
            if sig in seen:
                continue
            seen.add(sig)
            macro, other = {}, []
            for l, c in lines:
                k = key(l)
                if k == "energy":
                    if "kcal" in c: macro["kcal"] = c["kcal"]
                    if "kj" in c: macro["kj"] = c["kj"]
                    if "kcal" not in c and "kj" not in c and "value" in c:
                        macro["energy_bare"] = c["value"]
                elif k and c.get("value") is not None and k not in macro:
                    macro[k] = c["value"]
                    if c.get("less_than"): macro[k + "_lt"] = True
                else:
                    other.append({"label": l, **c})
            # bare energy: decide kcal vs kJ by magnitude vs macros when possible
            if "energy_bare" in macro and "kcal" not in macro:
                e = macro.pop("energy_bare")
                p, f, cb = macro.get("protein_g"), macro.get("fat_g"), macro.get("carbs_g")
                if None not in (p, f, cb):
                    est = 4 * p + 9 * f + 4 * cb
                    macro["kcal" if abs(e - est) < abs(e / 4.184 - est) else "kj"] = e
                    macro["energy_guess"] = True
                else:
                    macro["energy_unclear"] = e
            macro.pop("energy_bare", None)
            if "kj" in macro and "kcal" not in macro:
                macro["kcal_from_kj"] = round(macro["kj"] / 4.184, 1)
            res.append({"variant": variant, "basis": basis, "basis_amount": amt, "section": t["section"],
                        "macro": macro, "lines": [{"label": l, **c} for l, c in lines]})
    return res


def main():
    inp = os.path.join(D, "products.jsonl")
    outp = os.path.join(D, "nutrition_rows.jsonl")
    stats = collections.Counter()
    with open(outp, "w", encoding="utf8") as f:
        for ln in open(inp, encoding="utf8"):
            r = json.loads(ln)
            rows = normalise(r)
            stats["products"] += 1
            if any(x["basis"] == "per_100" and "kcal" in x["macro"] for x in rows):
                stats["products_with_per100_kcal"] += 1
            elif rows:
                stats["products_only_other_basis"] += 1
            else:
                stats["products_no_nutrition"] += 1
            for x in rows:
                stats["rows"] += 1
                f.write(json.dumps({"source": "gymgrossisten", "source_url": r["source_url"], "sku": r["sku"],
                                    "ean": r["ean"], "name": r["name"], "brand": r["brand"],
                                    "ingredients_text": r.get("ingredients_text"), **x}, ensure_ascii=False) + "\n")
    print(dict(stats))


if __name__ == "__main__":
    main()
