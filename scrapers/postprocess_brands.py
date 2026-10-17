"""Add non-destructive quality flags to the norwegian-brands-dairy-meat sources (source values are never changed).
Run only when no scraper is appending to these files."""
import json, os, re, sys

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "raw")
SRC = ["gilde", "prior", "q-meieriene", "fjordland", "tine", "grandiosa", "nidar", "saetre", "toro", "firstprice", "eldorado", "mills", "ringnes", "synnove", "kavli", "hennig-olsen"]


def v(p, k):
    x = (p or {}).get(k)
    return x["value"] if x and x.get("value") is not None else None


def flags_for(d):
    f = []
    p = d.get("nutrition_per100")
    if not p:
        return f
    kcal, kj = v(p, "energy_kcal"), v(p, "energy_kj")
    fat, carb, prot, fib = v(p, "fat"), v(p, "carbs"), v(p, "protein"), v(p, "fibre") or 0
    if kcal is not None and kcal > 900:
        f.append("kcal_implausible_over_900")
    if kcal and kj and not (3.9 <= kj / kcal <= 4.5):
        f.append("kj_kcal_ratio_off")
    if None not in (fat, carb, prot):
        if fat + carb + prot > 100.5:
            f.append("macros_sum_over_100g")
        if kcal and kcal > 20:
            est = 4 * prot + 4 * max(carb - fib, 0) + 9 * fat + 2 * fib
            if est < 0.6 * kcal or est > 1.4 * kcal:
                f.append("macro_energy_mismatch")
    if d.get("per100_is_prepared"):
        f.append("per100_is_prepared_state")
    if any((x or {}).get("unit_inferred") for x in p.values()):
        f.append("unit_inferred")
    return f


def fix_ringnes(d):
    m = re.match(r"Produkter\s*»\s*(.+?)\s*»\s*(.+?)\s*«\s*Ringnes AS", d.get("name") or "")
    if m:
        d["brand_line"] = m.group(1)
        d["name"] = m.group(2)


for s in SRC:
    p = os.path.join(R, s, "products.jsonl")
    if not os.path.exists(p):
        continue
    out, n, nf = [], 0, 0
    for l in open(p, encoding="utf-8"):
        d = json.loads(l)
        if s == "ringnes":
            fix_ringnes(d)
        fl = flags_for(d)
        if fl:
            d["quality_flags"] = fl
            nf += 1
        else:
            d.pop("quality_flags", None)
        out.append(json.dumps(d, ensure_ascii=False))
        n += 1
    tmp = p + ".tmp"
    open(tmp, "w", encoding="utf-8").write("\n".join(out) + "\n")
    os.replace(tmp, p)
    print(s, n, "flagged", nf)
