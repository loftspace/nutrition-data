"""Add Jev categories to products.sqlite and fold plain single-ingredient supplements into one canonical product each.
Run after build.py + coverage.py:  python -I build/postprocess_jev.py     (idempotent: re-running rebuilds the added columns/rows)

Adds columns to products: category, category_conf, category_review, is_supplement, ingredient_group, merged_into, hidden.
Merge rule: a product is folded into a canonical product ONLY when
  - Jev says it is a single plain active ingredient (is_single_active_ingredient > 0.8),
  - the ingredient group is a pure compound whose nutrition does not depend on the brand (list below), with group confidence > 0.7,
  - it has no macros of its own or macros at or below 10 kcal (anything with real macros stays visible: it is a different product),
  - it is not discontinued-only noise (discontinued products are folded too; they are hidden either way).
Members are kept in the database with merged_into = canonical id and hidden = 1; nothing is deleted."""
import json, os, sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = ROOT + '/data/unified/products.sqlite'
SUPP_CATS = {'protein_powder', 'protein_bar', 'protein_drink_or_dessert', 'mass_gainer_meal_replacement', 'creatine', 'pre_workout', 'amino_acids', 'vitamin_mineral',
             'omega3_oils', 'collagen_joint', 'fat_burner_weight_loss', 'herbal_other_supplement', 'energy_gel_sports_drink'}

# group -> (canonical id, name, category, serving_g, note)
CANON = {
    'creatine_monohydrate': ('generic:creatine-monohydrate', 'Creatine monohydrate', 'creatine', 3.0, 'Typical serving 3 to 5 g. Pure compound: no meaningful energy or macros.'),
    'beta_alanine': ('generic:beta-alanine', 'Beta-alanine', 'amino_acids', 3.2, 'Typical serving 2 to 5 g. Pure compound; amino acids count about 4 kcal per g if you track them as energy.'),
    'citrulline': ('generic:citrulline', 'Citrulline (L-citrulline / citrulline malate)', 'amino_acids', 6.0, 'Typical serving 6 to 8 g. Pure compound.'),
    'glutamine': ('generic:glutamine', 'L-glutamine', 'amino_acids', 5.0, 'Typical serving 5 g. Pure amino acid, about 4 kcal per g.'),
    'taurine': ('generic:taurine', 'Taurine', 'amino_acids', 3.0, 'Typical serving 1 to 3 g. Pure compound.'),
    'caffeine': ('generic:caffeine', 'Caffeine (anhydrous)', 'pre_workout', 0.2, 'Typical dose 100 to 200 mg. Pure compound, no macros.'),
}
ENERGY_PER_G = {'generic:glutamine': 4.0, 'generic:beta-alanine': 4.0, 'generic:citrulline': 4.0}


def main():
    c = sqlite3.connect(DB)
    cols = {r[1] for r in c.execute('pragma table_info(products)')}
    # idempotent: drop previously added canonical rows, then add columns if missing
    c.execute("delete from products where id like 'generic:%'")
    c.execute("delete from nutrients where product_id like 'generic:%'")
    c.execute("delete from product_sources where product_id like 'generic:%'")
    for col, typ in [('category', 'TEXT'), ('category_conf', 'REAL'), ('category_review', 'INTEGER'), ('is_supplement', 'INTEGER'),
                     ('ingredient_group', 'TEXT'), ('merged_into', 'TEXT'), ('hidden', 'INTEGER')]:
        if col not in cols:
            c.execute('alter table products add column %s %s' % (col, typ))
    c.execute('update products set category=null, category_conf=null, category_review=null, is_supplement=null, ingredient_group=null, merged_into=null, hidden=0')

    s1 = {}
    for l in open(ROOT + '/data/jev/stage1.jsonl', encoding='utf-8'):
        r = json.loads(l); s1[r['id']] = r
    s2 = {}
    for l in open(ROOT + '/data/jev/stage2.jsonl', encoding='utf-8'):
        r = json.loads(l); s2[r['id']] = r
    rows = []
    for pid, r in s1.items():
        sup = 1 if (r['is_supplement'] > 0.5 or r['category'] in SUPP_CATS) else 0
        rows.append((r['category'], r['category_conf'], 1 if r['category_conf'] < 0.5 else 0, sup, pid))
    c.executemany('update products set category=?, category_conf=?, category_review=?, is_supplement=? where id=?', rows)
    c.executemany('update products set ingredient_group=? where id=?', [(r['ingredient_group'], pid) for pid, r in s2.items() if r['is_single_active_ingredient'] > 0.5])

    merged = {}
    for pid, r in s2.items():
        g = r['ingredient_group']
        if g not in CANON or r['is_single_active_ingredient'] <= 0.8 or r['ingredient_group_conf'] <= 0.7:
            continue
        p = c.execute('select kcal, protein_g, fat_g, carbs_g from products where id=?', (pid,)).fetchone()
        if p is None:
            continue
        kcal = p[0]
        if kcal is not None and kcal > 10:
            continue
        if any(v is not None and v > 1 for v in p[1:]):
            continue
        merged.setdefault(g, []).append(pid)

    report = {}
    for g, pids in merged.items():
        cid, name, cat, serving, note = CANON[g]
        kcal_g = ENERGY_PER_G.get(cid, 0.0) * 100
        c.execute('''insert into products(id,name,brand,pack_size,ean,kind,flavour,categories,ingredients,allergens,serving_g,primary_source,n_sources,status,data_quality,region,regions,
                     norway_relevant,discontinued,all_eans,kcal,protein_g,fat_g,sat_fat_g,carbs_g,sugars_g,fibre_g,salt_g,kj,category,category_conf,category_review,is_supplement,
                     ingredient_group,merged_into,hidden) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (cid, name, None, None, None, 'generic', None, json.dumps([cat]), None, None, serving, 'derived-jev', len(pids), 'derived',
                   json.dumps(['derived_canonical_from_%d_products' % len(pids), 'pure_compound', note]), 'NO', 'NO,SE,DK,UK,US,EU', 1, 0, None,
                   kcal_g if kcal_g else 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, None, cat, 1.0, 0, 1, g, None, 0))
        c.execute("insert into nutrients(product_id,basis,code,value,unit,qualifier,source) values(?,?,?,?,?,?,?)", (cid, 'per_100g', 'kcal', kcal_g, 'kcal', None, 'derived-jev'))
        c.executemany('update products set merged_into=?, hidden=1 where id=?', [(cid, p) for p in pids])
        report[cid] = len(pids)
    c.execute("insert into products_fts(products_fts) values('rebuild')")
    c.execute('create index if not exists ix_products_category on products(category, norway_relevant, hidden)')
    c.commit()
    n_vis = c.execute('select count(*) from products where norway_relevant=1 and hidden=0').fetchone()[0]
    print('canonical products and folded members:', report)
    print('visible Norway-relevant products:', n_vis, '| needing category review (conf<0.5):', c.execute('select count(*) from products where category_review=1').fetchone()[0])
    c.close()


if __name__ == '__main__':
    main()
