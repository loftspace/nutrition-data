"""Write COVERAGE.md for the unified macro library (reads products.sqlite, stats.json, products.jsonl)."""
import collections
import datetime
import json
import os
import re
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = 'C:/Users/Admin/Documents/Claude/zz-Misc/macro-library'
U = ROOT + '/data/unified'
db = sqlite3.connect(U + '/products.sqlite')
st = json.load(open(U + '/stats.json'))
try:
    st0 = json.load(open(U + '/stats_before.json'))        # first-pass build (copied before the second-pass rebuild)
except OSError:
    st0 = {}
# per-source table of the first-pass COVERAGE.md (entries / primary / kcal ...), kept as data/unified/COVERAGE_before.md
BEFORE = {}
try:
    for ln in open(U + '/COVERAGE_before.md', encoding='utf-8'):
        m = re.match(r'^\| ([a-z0-9\-]+) \| (\d*) \| (\d+) \| (\d+) \| (\d+) \| (\d+) \| (\d+) \| (\d+) \| (\d+) \| (\d+) \| (\d+) \| (\d+) \|$', ln)
        if m:
            BEFORE[m.group(1)] = {'raw': int(m.group(2) or 0), 'read': int(m.group(3)), 'entries': int(m.group(4)), 'primary': int(m.group(5)), 'kcal': int(m.group(6))}
except OSError:
    pass
PRODUCTS_BEFORE = st0.get('products', 85553)


def q(sql, *a):
    return db.execute(sql, a).fetchall()


def one(sql, *a):
    return db.execute(sql, a).fetchone()[0]


def du(path):
    t = 0
    for dp, dn, fn in os.walk(path):
        for f in fn:
            try:
                t += os.path.getsize(os.path.join(dp, f))
            except OSError:
                pass
    return t


def mb(b):
    return '%.0f MB' % (b / 1e6) if b < 1e9 else '%.2f GB' % (b / 1e9)


total = one('select count(*) from products')
out = []
w = out.append
w('# Macro library coverage')
w('')
w('Built %s by `build/build.py` + `build/coverage.py`. Personal use only (ODbL / CC BY / USDA CC0 / store data: see `data/raw/*/LICENSE-NOTE.txt`).' % datetime.date.today().isoformat())
w('')
w('Everything is **from_source**: values are what the sources published. Nothing is estimated, except three labelled derivations (`kcal` from kJ / 4.184, `salt_g` from sodium x 2.5, `sodium_mg` from salt x 400), which are marked in `field_provenance` as `derived`.')
w('')
w('## Totals')
w('')
w('| What | Count |')
w('|---|---:|')
w('| Raw records read (after dropping non-food without nutrition) | %d |' % st['candidates'])
w('| **Unified products** | **%d** (first pass: %d) |' % (total, PRODUCTS_BEFORE))
FULL = "kcal is not null and protein_g is not null and fat_g is not null and carbs_g is not null"
w('| **Norway-relevant products** (a Norwegian source, or a Nordic / EU / UK online shop Max can buy from) | **%d** |' % one('select count(*) from products where norway_relevant=1'))
w('| Norway-relevant products with full macros (kcal + protein + fat + carbs) | %d |' % one('select count(*) from products where norway_relevant=1 and ' + FULL))
w('| Norway-relevant, full macros, EAN and not discontinued | %d |' % one('select count(*) from products where norway_relevant=1 and discontinued=0 and ean is not null and ' + FULL))
w('| Discontinued products (every source page gone) | %d |' % one('select count(*) from products where discontinued=1'))
w('| Products with more than one EAN (flavours / sizes of one page answer to all of them) | %d |' % one("select count(*) from (select product_id from product_eans group by 1 having count(*)>1)"))
w('| Duplicate source records merged into an existing product (same EAN) | %d |' % st['merged_duplicates'])
w('| Products with an EAN (valid GTIN checksum) | %d |' % one('select count(*) from products where ean is not null'))
w('| Products with several source entries | %d |' % one('select count(*) from products where n_sources>1'))
w('| Product source entries (product_sources rows) | %d |' % one('select count(*) from product_sources'))
w('| Nutrient codes defined / used | %d / %d |' % (st['nutrient_codes_defined'], st['nutrient_codes_used']))
w('| Distinct raw labels left unmapped (in `unmapped.json`) | %d (%d occurrences) |' % (st['unmapped_distinct'], st['unmapped_occurrences']))
w('| Nutrient rows (long table) | %d |' % one('select count(*) from nutrients'))
w('')
w('Records dropped before the merge (counted per source in the food vs non-food table below): ' + ', '.join('%s %d' % (k, sum(v.values())) for k, v in sorted(st['dropped_non_food_no_nutrition'].items(), key=lambda kv: -sum(kv[1].values()))[:12]) + ' ... Non-food = name or category says clothing, gear, shaker, cosmetics, pet food or household, AND the record has no nutrition. Nemlig all-zero placeholder rows are dropped too. Samples of every drop reason are in `stats.json` (`drop_samples`).')
w('')
w('## Counts per source, before and after')
w('')
w('`raw` is the number of records the collector saved, `read` what went into the merge (after dropping non-food without nutrition; variant rows of one page are collapsed to one candidate), `entries` the number of source entries kept in product_sources, `primary` how many products use this source as their primary (priority: pack label = producer or store page > Kassalapp > NorgesGruppen > Open Food Facts > USDA branded > generic tables; a live page beats a gone page; only a source that has kcal can win over one that has none). kcal/protein/fat/carbs/fibre/salt are counted over source entries with a per-100 g value. `entries before` is the first-pass build (85,553 products), `new` is entries now minus before. The first-pass folders of tights, gymgrossisten, bodystore, proteinfabrikken and bulk are replaced by their `-v2` folders (same shop, name kept).')
w('')
w('| Source | region | NO-relevant | raw | read | entries | entries before | new | primary | kcal | protein | fat | carbs | fibre | salt | EAN | gone |')
w('|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|')
cnt = collections.defaultdict(collections.Counter)
srcmeta = {}
for src, pj, ean, reg, nr, gone in q('select s.source, s.per_100g_json, p.ean, s.region, s.norway_relevant, s.page_gone from product_sources s join products p on p.id=s.product_id'):
    d = json.loads(pj)
    cnt[src]['entries'] += 1
    for k in ('kcal', 'protein_g', 'fat_g', 'carbs_g', 'fibre_g', 'salt_g'):
        if k in d:
            cnt[src][k] += 1
    if ean:
        cnt[src]['ean'] += 1
    if gone:
        cnt[src]['gone'] += 1
    srcmeta.setdefault(src, collections.Counter())[(reg, nr)] += 1
prim = dict(q('select primary_source, count(*) from products group by 1'))
rawc = st['raw_records_per_source']


def raw_lines(folder):
    n = 0
    p_ = ROOT + '/data/raw/%s/products.jsonl' % folder
    if not os.path.exists(p_):
        return None
    with open(p_, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 24), b''):
            n += chunk.count(b'\n')
    return n


V2 = {'tights': 'tights-v2', 'gymgrossisten': 'gymgrossisten-v2', 'bodystore': 'bodystore-v2', 'proteinfabrikken': 'proteinfabrikken-v2', 'bulk': 'bulk-v2'}
RAWLINES = {}
for s_ in cnt:
    n_ = raw_lines(V2.get(s_, s_))
    if n_ is None and s_ in ('usda-fdc',):
        n_ = sum(raw_lines('usda-fdc/' + x) or 0 for x in ())
    RAWLINES[s_] = n_
order = sorted(cnt, key=lambda s_: -cnt[s_]['entries'])
for s_ in order:
    c = cnt[s_]
    reg, nr = srcmeta[s_].most_common(1)[0][0]
    if len(srcmeta[s_]) > 1:
        reg, nr = 'mixed', any(k_[1] for k_ in srcmeta[s_])
    b0 = BEFORE.get(s_, {})
    w('| %s | %s | %s | %s | %d | %d | %s | %+d | %d | %d | %d | %d | %d | %d | %d | %d | %d |' % (
        s_, reg, 'yes' if nr else 'no', RAWLINES.get(s_) if RAWLINES.get(s_) is not None else '', st['raw_records_per_source'].get(s_, 0), c['entries'], b0.get('entries', 0) if b0 else 0,
        c['entries'] - (b0.get('entries', 0) if b0 else 0), prim.get(s_, 0), c['kcal'], c['protein_g'], c['fat_g'], c['carbs_g'], c['fibre_g'], c['salt_g'], c['ean'], c['gone']))
w('')
w('`raw` counts file lines in `data/raw/<folder>/products.jsonl` (v2 folder for the five replaced shops; for usda-fdc and a few multi-file sources it is blank). Variant, page and offer rows of one page are separate lines in the raw file but one candidate here.')
w('')
w('## Food vs non-food per store')
w('')
w('Food = every record that went into the merge. Non-food = records dropped because they had no nutrition AND the name or category says clothing, gear, shaker, cosmetics, pet food or household. Placeholder = Nemlig rows whose nutrition is all zero. Not-a-product = a record with no name, no EAN and no nutrition. Kept without nutrition are products that stay in the library (supplements with an image-only table and so on).')
w('')
w('| Source | read (food) | with per-100 kcal | kept without nutrition | dropped non-food | dropped placeholder / empty |')
w('|---|---:|---:|---:|---:|---:|')
for s_ in sorted(set(order) | set(st['dropped_non_food_no_nutrition']), key=lambda x: -(cnt[x]['entries'] if x in cnt else 0)):
    dr = st['dropped_non_food_no_nutrition'].get(s_, {})
    nf = dr.get('nonfood_no_nutrition', 0)
    ph = sum(v for k, v in dr.items() if k != 'nonfood_no_nutrition')
    nn = one("select count(*) from product_sources where source=? and per_100g_json='{}'", s_) if s_ in cnt else 0
    if not (cnt[s_]['entries'] if s_ in cnt else 0) and not nf and not ph:
        continue
    w('| %s | %d | %d | %d | %d | %d |' % (s_, st['raw_records_per_source'].get(s_, 0), cnt[s_]['kcal'] if s_ in cnt else 0, nn, nf, ph))
w('')
w('## Region and Norway relevance')
w('')
w('`region` of a product is the best region among its sources in the order NO, SE, DK, EU, UK, US, other (so an EAN found in a Norwegian shop is NO even if a Swedish shop also has it); `regions` lists all. `norway_relevant` is true when any source is Norwegian, or a Nordic, EU or UK online shop / database Max can buy from (Swedish and Danish shops, Bulk, Myprotein UK, Scitec, ESN, Weider, Optimum Nutrition EU, Grenade and other UK sites, Open Food Facts records tagged for a Nordic country). It is false when every source is USDA branded, Frida, Livsmedelsverket, a US brand site (Quest, Cellucor, MuscleTech, Ghost, Transparent Labs, Gorilla Mind, Legion, Dymatize, Bodybuilding.com) or an Open Food Facts record that is not tagged for a Nordic country. That is a judgement about reach, not a statement that the product cannot be bought in Norway.')
w('')
w('| Region | products | norway-relevant | with full macros | relevant with full macros | with EAN | discontinued |')
w('|---|---:|---:|---:|---:|---:|---:|')
for reg in ('NO', 'SE', 'DK', 'EU', 'UK', 'US', 'other'):
    w('| %s | %d | %d | %d | %d | %d | %d |' % (reg, one('select count(*) from products where region=?', reg), one('select count(*) from products where region=? and norway_relevant=1', reg),
                                              one('select count(*) from products where region=? and ' % () + FULL, reg), one('select count(*) from products where region=? and norway_relevant=1 and ' % () + FULL, reg),
                                              one('select count(*) from products where region=? and ean is not null', reg), one('select count(*) from products where region=? and discontinued=1', reg)))
w('| **all** | %d | %d | %d | %d | %d | %d |' % (total, one('select count(*) from products where norway_relevant=1'), one('select count(*) from products where ' + FULL),
                                                  one('select count(*) from products where norway_relevant=1 and ' + FULL), one('select count(*) from products where ean is not null'), one('select count(*) from products where discontinued=1')))
w('')
w('Norway-relevant products by how they qualify: ' + ', '.join('%s %d' % (k, n) for k, n in [(r_[0], r_[1]) for r_ in [(v, one("select count(*) from products where id in (select id from products where norway_relevant=1) and region=?", v)) for v in ('NO', 'SE', 'DK', 'EU', 'UK', 'other')]]) + ' (by best region).')
w('')
w('Of the Norway-relevant products with full macros, %d have the per-100 g values derived from a per-serving table (flag `per100_derived_from_serving`) and %d carry the flag `flavour_nutrition_shared_assumed`.' % (
    one("select count(*) from products where norway_relevant=1 and " + FULL + " and data_quality like '%per100_derived_from_serving%'"), one("select count(*) from products where norway_relevant=1 and " + FULL + " and data_quality like '%flavour_nutrition_shared_assumed%'")))
w('')
w('## Discontinued products')
w('')
w('A product is `discontinued` when every one of its source pages is gone: the live URL answered 404/410 or redirected elsewhere, and the data comes from an Internet Archive snapshot (tights, gymgrossisten, bodystore, proteinfabrikken, myprotein, bulk, life.no), or Open Food Facts marks the product obsolete. Products whose page is live but hidden from the shop listing are NOT discontinued. If any live source exists the product is not discontinued, even when an old shop page is gone.')
w('')
w('| Primary source | discontinued products | with full macros | with EAN |')
w('|---|---:|---:|---:|')
for s_, n_ in q('select primary_source, count(*) from products where discontinued=1 group by 1 order by 2 desc limit 20'):
    w('| %s | %d | %d | %d |' % (s_, n_, one('select count(*) from products where discontinued=1 and primary_source=? and ' % () + FULL, s_), one('select count(*) from products where discontinued=1 and primary_source=? and ean is not null', s_)))
w('')
w('Source entries with a gone page (including entries that sit inside a still-live product): %d.' % one('select count(*) from product_sources where page_gone=1'))
w('')
w('## Nutrient completeness of the unified products (primary values + gap fills)')
w('')
w('| Has | Products | % of all | % of products with a barcode |')
w('|---|---:|---:|---:|')
ean_total = one('select count(*) from products where ean is not null')


def row(label, n, n_ean):
    w('| %s | %d | %.1f%% | %.1f%% |' % (label, n, 100 * n / total, 100 * n_ean / ean_total))


for label, col in [('kcal', 'kcal'), ('protein', 'protein_g'), ('fat', 'fat_g'), ('carbs', 'carbs_g'), ('fibre', 'fibre_g'), ('salt', 'salt_g'), ('sugars', 'sugars_g'), ('saturated fat', 'sat_fat_g')]:
    row(label, one('select count(*) from products where %s is not null' % col), one('select count(*) from products where %s is not null and ean is not null' % col))
row('kcal + protein + fat + carbs (full macros)', one('select count(*) from products where kcal is not null and protein_g is not null and fat_g is not null and carbs_g is not null'),
    one('select count(*) from products where kcal is not null and protein_g is not null and fat_g is not null and carbs_g is not null and ean is not null'))
row('full macros + fibre + salt', one('select count(*) from products where kcal is not null and protein_g is not null and fat_g is not null and carbs_g is not null and fibre_g is not null and salt_g is not null'),
    one('select count(*) from products where kcal is not null and protein_g is not null and fat_g is not null and carbs_g is not null and fibre_g is not null and salt_g is not null and ean is not null'))
for label, grp in [('at least one vitamin', 'vitamin'), ('at least one mineral (besides sodium)', 'mineral'), ('at least one amino acid', 'amino_acid'), ('at least one fatty-acid detail (omega-3, EPA, chains)', 'fatty_acid')]:
    extra = " and n.code<>'sodium_mg'" if grp == 'mineral' else ''
    n1 = one("select count(distinct n.product_id) from nutrients n join nutrient_dictionary d on d.code=n.code where n.basis='per_100g' and d.grp=? %s" % extra, grp)
    n2 = one("select count(distinct n.product_id) from nutrients n join nutrient_dictionary d on d.code=n.code join products p on p.id=n.product_id where n.basis='per_100g' and d.grp=? and p.ean is not null %s" % extra, grp)
    row(label, n1, n2)
_vm = "select count(*) from (select n.product_id from nutrients n join nutrient_dictionary d on d.code=n.code join products p on p.id=n.product_id where n.basis='per_100g' and (d.grp='vitamin' or (d.grp='mineral' and n.code<>'sodium_mg')) %s group by n.product_id having sum(d.grp='vitamin')>0 and sum(d.grp='mineral')>0)"
row('both a vitamin and a mineral', one(_vm % ''), one(_vm % 'and p.ean is not null'))
row('per-serving values (any)', one("select count(distinct product_id) from nutrients where basis='per_serving'"), one("select count(distinct n.product_id) from nutrients n join products p on p.id=n.product_id where n.basis='per_serving' and p.ean is not null"))
row('no nutrition at all', one("select count(*) from products where data_quality like '%no_nutrition%'"), one("select count(*) from products where data_quality like '%no_nutrition%' and ean is not null"))
w('')
w('Product kinds: ' + ', '.join('%s %d' % (k, n) for k, n in q('select kind, count(*) from products group by 1')) + ' (`generic` = food composition table rows: Matvaretabellen, Frida, Livsmedelsverket, USDA Foundation/SR Legacy; they have no EAN or brand).')
w('')
w('Products with a barcode by region of the primary EAN prefix: Norwegian 70xx: %d; other: %d.' % (one("select count(*) from products where ean like '70%'"), one("select count(*) from products where ean is not null and ean not like '70%'")))
w('')
w('## Data-quality flags')
w('')
w('Every product has a `data_quality` list; the primary source decides it, plus cross-source flags. Thresholds: kcal vs 4/4/9 (plus 2 kcal/g fibre, 7 kcal/g alcohol, 2.4 kcal/g polyols) must be within 15 % or 20 kcal; kJ/kcal within 12 %; protein+fat+carbs over 105 g per 100 g is flagged as probably per-serving or a unit error; cross-source disagreement: kcal more than 15 % and 20 kcal apart, protein/fat/carbs more than 25 % and 3 g apart.')
w('')
fl = collections.Counter()
for (x,) in q('select data_quality from products'):
    for f in json.loads(x):
        fl[f.split(':')[0] if not f.startswith('filled_from') else 'filled_from_other_source'] += 1
desc = {
    'no_nutrition': 'no per-100 g or per-serving nutrition at all', 'missing_fibre': 'has kcal but no fibre value', 'missing_salt': 'has kcal but neither salt nor sodium',
    'missing_kcal': 'per-100 g values exist but no energy', 'missing_macros': 'kcal present but protein, fat or carbs missing', 'per_serving_only': 'only per-serving values, no per-100 g (not converted)',
    'kcal_macro_mismatch': 'kcal does not match macros (4/4/9 check)', 'kj_kcal_mismatch': 'kJ and kcal disagree by more than 12 %', 'macros_sum_over_100g': 'protein+fat+carbs over 105 g: per-100 g may be per-serving',
    'kcal_implausible_high': 'over 910 kcal per 100 g', 'sat_fat_exceeds_fat': 'saturated fat above total fat', 'sugars_exceed_carbs': 'sugars above carbohydrate',
    'salt_sodium_mismatch': 'salt and sodium differ by more than 40 % from the 2.5 factor', 'sources_disagree': 'two sources disagree on kcal/protein/fat/carbs, see source_disagreements',
    'per100_basis_unverified': 'page table did not state per 100 g or per serving', 'per100_derived_from_serving': 'per-100 g computed by the scraper from a serving size', 'per100_is_prepared_state': 'per-100 g is the prepared (cooked) state, not as sold',
    'ean_checksum_invalid': 'EAN given by the source fails the GTIN check digit (not used for merging)', 'ean_malformed': 'EAN is a PLU/short code (weighed goods) or wrong length (not used for merging)',
    'filled_from_other_source': 'gaps in the primary filled from an agreeing source (kcal within tolerance), see field_provenance', 'us_market_product': 'USDA branded product (US market)',
    'unit_assumed': 'a vitamin/mineral value had no unit, canonical unit assumed', 'sodium_unit_assumed': 'sodium without unit: values <= 5 read as g, else mg',
    'flavour_nutrition_shared_assumed': 'page lists several flavours / variants; one nutrition table is used for the product (decided: flavours share nutrition)',
    'implausible_value_removed_by_collector': 'a value above physical limits was removed by the fix-flavours collector',
    'per100_prepared_state_only': 'only a prepared-drink column exists, not mapped', 'kj_dropped_inconsistent_with_kcal': 'kJ disagreed with kcal and was dropped (kcal kept)',
    'ingredients_discarded_junk': 'scraped text was a page footer or a whole-page dump, not an ingredient list; discarded',
    'off_obsolete': 'Open Food Facts marks the product obsolete (treated as discontinued)', 'nutrition_image_only': 'nutrition is only an image on the page (not read)',
    'per100_derived_from_serving': 'per-100 g computed from a per-serving table and its gram size (energy present, serving at least 5 g)',
    'per100_basis_assumed': 'the table did not print per 100 g / 100 ml; per 100 assumed',
    'carbs_over_100g': 'carbohydrate above 100 g per 100 g', 'protein_over_100g': 'protein above 100 g per 100 g', 'fat_over_100g': 'fat above 100 g per 100 g',
    'flavour_table_ambiguous': 'proteinfabrikken page with several candidate tables; the collector could not pick one', 'unit_inferred_by_scraper': 'unit not printed, inferred by the collector',
    'scraper_flag_macro_energy_mismatch': 'collector flagged macros vs energy', 'scraper_flag_kj_kcal_ratio': 'collector flagged kJ vs kcal',
    'variants_share_one_nutrition_table': 'page states that variants share one table', 'flavour_macros_may_differ': 'page text says flavour macros may differ',
    'energy_unit_guessed': 'Gymgrossisten energy unit guessed', 'energy_unit_unclear': 'Gymgrossisten energy unit unclear',
    'bundle_or_multipack': 'bundle or multipack page', 'nutrition_text_only': 'nutrition only as free text, not parsed', 'variant_table_ambiguous': 'several flavour tables, first used',
}
w('| Flag | Products | Meaning |')
w('|---|---:|---|')
for f, n in fl.most_common():
    w('| %s | %d | %s |' % (f, n, desc.get(f, '')))
w('')
w('## Real searches against products.sqlite')
w('')
w('Run with FTS5 (`products_fts` on name, brand, flavour, categories; unicode61, diacritics folded). Ranking is bm25, products with kcal first. Values per 100 g. `src` = primary source, `n` = number of source entries.')
w('')
SEARCHES = [
    ('YT proteinyoghurt', 'yt AND proteinyoghurt*'),
    ('Skyr', 'skyr'),
    ('Tine Lett', 'tine AND lett*'),
    ('protein powder chocolate', '(protein* OR whey* OR myseprotein* OR proteinpulver*) AND (chocolate OR sjokolade OR choc* OR chokolade)'),
    ('Gilde kjottdeig', 'gilde AND (kjottdeig* OR kjøttdeig*)'),
]
searches_json = {}
for title, match in SEARCHES:
    rows = q("""select p.id, p.name, p.brand, p.flavour, p.kcal, p.protein_g, p.fat_g, p.carbs_g, p.salt_g, p.primary_source, p.n_sources, p.pack_size
                from products_fts f join products p on p.rowid=f.rowid where products_fts match ?
                order by (p.kcal is null), bm25(products_fts) limit 10""", match)
    total_hits = one('select count(*) from products_fts where products_fts match ?', match)
    w('### %s' % title)
    w('')
    w('`MATCH %s` : %d hits, top %d' % (match, total_hits, len(rows)))
    w('')
    w('| id | name | brand | flavour | kcal | protein | fat | carbs | salt | src | n |')
    w('|---|---|---|---|---:|---:|---:|---:|---:|---|---:|')
    for r in rows:
        w('| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (r[0], (r[1] or '').replace('|', '/'), r[2] or '', r[3] or '', *[('%g' % x if x is not None else '') for x in r[4:9]], r[9], r[10]))
    w('')
    searches_json[title] = {'match': match, 'hits': total_hits}
w('Reproduce: `sqlite3 products.sqlite "select p.name,p.brand,p.kcal,p.protein_g from products_fts f join products p on p.rowid=f.rowid where products_fts match \'skyr\' order by bm25(products_fts) limit 10"`.')
w('')
w('## Protein powders and supplements')
w('')
SUPP = re.compile(r"(whey|myse|vassle|valle|protein|kreatin|creatine|bcaa|eaa|amino|pre-?workout|pwo|casein|kasein|gainer|vitamin|omega|kollagen|collagen|magnesium|glutamin|beta-?alanin|citrullin|koffein|caffeine|zink|zinc|jern|multivit|probiot|kosttilskudd|kosttillskott|elektrolytt|electrolyte|pump|fatburner|thermo|bar\b|barer\b)", re.I)
rows_ = q("select name, categories, region, norway_relevant, kcal, protein_g, fat_g, carbs_g, data_quality, discontinued, ean is not null from products where kind='product'")
agg = collections.defaultdict(collections.Counter)
for name, cats, reg, nr, kcal, p_, f_, c_, dq, disc, hasean in rows_:
    if not SUPP.search((name or '') + ' ' + (cats or '')):
        continue
    for key in (reg, 'all'):
        a_ = agg[key]
        a_['products'] += 1
        a_['kcal'] += kcal is not None
        a_['full'] += (kcal is not None and p_ is not None and f_ is not None and c_ is not None)
        a_['serving_only'] += ('per_serving_only' in dq)
        a_['none'] += ('"no_nutrition"' in dq)
        a_['nr'] += bool(nr)
        a_['disc'] += bool(disc)
        a_['ean'] += bool(hasean)
w('Products whose name or category matches protein, whey, creatine, BCAA/EAA, amino, pre-workout, casein, gainer, vitamin, omega, collagen, magnesium and similar words (kind = product, so no generic tables). This is a name match, not a curated category; Jev (TypeSafe) was NOT used to classify, it needs a chat yes first.')
w('')
w('| Region | supplement-like products | Norway-relevant | with per-100 kcal | with full macros | per-serving only | no nutrition | with EAN | discontinued |')
w('|---|---:|---:|---:|---:|---:|---:|---:|---:|')
for key in ('NO', 'SE', 'DK', 'EU', 'UK', 'US', 'other', 'all'):
    a_ = agg[key]
    w('| %s | %d | %d | %d | %d | %d | %d | %d | %d |' % (key, a_['products'], a_['nr'], a_['kcal'], a_['full'], a_['serving_only'], a_['none'], a_['ean'], a_['disc']))
w('')
w('Supplement and protein shops, per source (entries, per-100 g kcal, per-serving only, no nutrition among products where the source is primary):')
w('')
w('| Source | region | entries | with per-100 g kcal | per-serving only | no nutrition |')
w('|---|---|---:|---:|---:|---:|')
SUPP_SHOPS = ['tights', 'gymgrossisten', 'bodystore', 'proteinfabrikken', 'bulk', 'myprotein', 'tights-discontinued', 'gymgrossisten-discontinued', 'bodystore-discontinued', 'proteinfabrikken-discontinued',
              'myprotein-discontinued', 'bulk-discontinued', 'bodylab-no', 'life-no', 'life-no-discontinued', 'kost1-no', 'proteincompany-no', 'sportylab-no', 'helsekost-no', 'apex-no', 'nordicpower-no',
              'coore-no', 'diggbox-no', 'barebells-no', 'gymgrossisten-se', 'bodystore-se', 'tillskottsbolaget', 'bodylab-se', 'proteinbolaget', 'goldenathlete', 'mmsports', 'sportkost', 'bodypower', 'tyngre',
              'life-se', 'halsokostbolaget', 'halsafitnessbutiken', 'barebells', 'nocco', 'starnutrition-se', 'kungmarkatta', 'bodystore-dk', 'bodylab-dk', 'nutramino-dk', 'helsam-dk', 'matas-dk',
              'myprotein-uk', 'quest', 'fulfil', 'reflex', 'esn', 'grenade', 'cellucor', 'muscletech', 'applied-nutrition', 'weider', 'gorilla-mind', 'ghost', 'transparent-labs', 'optimum-nutrition',
              'dymatize', 'scitec', 'legion', 'bodybuilding']
for s_ in SUPP_SHOPS:
    if s_ not in cnt:
        continue
    e = one("select count(*) from product_sources where source=?", s_)
    k = one("select count(*) from product_sources where source=? and kcal is not null", s_)
    ps = one("select count(*) from products where primary_source=? and data_quality like '%per_serving_only%'", s_)
    nn = one("select count(*) from products where primary_source=? and data_quality like '%\"no_nutrition\"%'", s_)
    w('| %s | %s | %d | %d | %d | %d |' % (s_, srcmeta[s_].most_common(1)[0][0][0], e, k, ps, nn))
w('')
w('Products whose name or categories mention whey/protein powder/kreatin/casein and have per-100 g protein: %d.' % one("""select count(*) from products where protein_g is not null and (lower(name) like '%whey%' or lower(name) like '%myseprotein%' or lower(name) like '%proteinpulver%' or lower(name) like '%protein powder%' or lower(name) like '%casein%' or lower(name) like '%vassle%')"""))
w('')
w('## Gaps and honest limits')
w('')
for line in [
    'Kassalapp: 5,994 records saved (the priority pass stopped at its 3 h cap; about 154,000 queued products remain, mostly priority 2 "unknown" and food keywords). NorgesGruppen covers Meny/Spar/Joker (~39k EANs, 24k with nutrition); Kiwi is not covered. Only 600 NorgesGruppen products got the detail pass, so many lack ingredients. Resume Kassalapp with `scrapers/kassalapp_prio.py`.',
    'Duplicates are merged on a valid EAN (GTIN check digit), across shops and countries. A page that lists several flavours or sizes is ONE product that answers to all of its EANs (union of EANs, so a flavour EAN found in another shop joins the same product). Producer pages and grocery sources without EAN (Tine, Fjordland, Toro, Ringnes, Synnove, Kavli, Mills, Grandiosa, Nidar, Saetre, Q-Meieriene mostly; Nemlig, Rema 1000 DK, Kost1, Nordic Power, Barebells.no) stay separate products; they are not fuzzy-matched. Expect some products to exist twice because of that.',
    'Flavours share nutrition (Max decided). Every page that lists two or more flavours is one product with ONE table (the page default or the first one) and the flag `flavour_nutrition_shared_assumed`; real flavour differences of a few kcal or grams are not visible. The old per-flavour split of Gymgrossisten and Tights is gone.',
    'US brand sites (Quest, Cellucor, MuscleTech, Ghost, Transparent Labs, Gorilla Mind, Legion, Dymatize, Bodybuilding.com) publish per serving only or an image; where a gram serving and energy exist, per-100 g is derived and flagged `per100_derived_from_serving`. Image-only panels (Applied Nutrition 238, Ghost 177, Bodybuilding 213 and more) were not read: those products stay without nutrition. Their EANs are mostly missing, so they rarely merge with a Nordic shop.',
    'Norway relevance for US brand sites is false by definition used here (no Norwegian shop behind the page). Many of those brands are sold in Norwegian shops; the EAN merge makes such products relevant when a Norwegian source carries the same barcode.',
    'Not collected, with reasons: Prozis, Apotea (Cloudflare challenge), BSN, PhD Nutrition, Sci-MX, Foodspring, Clean Machine, Warrior, Olimp, Misfits, mmsports.no and nutravit.no (robots disallow), Healthwell.dk, Netto, Coop DK/SE, Lidl DK, Willys, Hemkop, Svenskt Kosttillskott (nutrition only as images), image-only Norwegian shops (getfit, gymbutikken, proteinspesialisten, tomminutrition, fitnessgrossisten, go-on-shop, kinsarvik, sunkost, vitusapotek, apotek1, farmasiet, med24), Nupo.dk, Med24.dk, Helsebixen.dk (not attempted). Fotex was sampled on food keywords only (281 of about 40,000 pages), Matas on supplement and food slugs only (2,699 of 63,000), ICA.se covers 5,061 of its 5,064 sitemap products but 4,226 of them have no nutrition table.',
    'Nemlig and Rema 1000 DK have no EAN, so their 9,000+ Danish grocery products never merge with the library; 2,121 Nemlig rows with an all-zero table were dropped as placeholders. Rema 1000 DK prints bare numbers; per 100 g or 100 ml is assumed (flag `per100_basis_assumed`).',
    'Open Food Facts global (89,463 records) was selected by category tags and by Sweden/Denmark; protein or supplement products with missing or unusual category tags are not in it. 3,600 of its records had no product name and keep a null name. Its values carry the usual crowd-sourced noise (3,700 kJ/kcal mismatches, 2,800 kcal/macro mismatches); it is lowest priority after pack-label and store pages. Name text may contain mojibake from OFF itself.',
    'Discontinued coverage is only what the Internet Archive and the live "hidden" pages gave: tights and gymgrossisten snapshots, bodystore, proteinfabrikken, myprotein, bulk and life.no. Archive snapshots often come in an older layout (no EAN, no nutrition). Bodylab.no archive pages load nutrition by script, so none were usable. 89 Gymgrossisten gone URLs had no snapshot at all.',
    'Non-food detection is a word list on name and the first three category levels, applied only to records with no nutrition. Non-food items without telltale words (a "Ribbed T-back" style garment) can still be in the library with `no_nutrition`; food-like supplement pages without a table are kept on purpose.',
    'Per-serving-only products (supplements, vitamins) are not converted to per 100 g unless they have energy and a serving of at least 5 g; `per_serving` holds their values with `serving_g` when the table gives a gram size.',
    'USDA branded rows are a filtered US set (supplement and protein brands): US EANs, English names, only merged when the barcode matches. Livsmedelsverket, Frida and USDA generic rows are tables, never Norway-relevant on their own.',
    'Swedish, Danish and Finnish label mapping was extended (Energi, Fett, mattat / maettede fedtsyrer, Kolhydrater / Kulhydrat, sockerarter, Fibrer / Kostfibre, Salt, Finnish rasva / hiilihydraatit / suola and joined labels such as "Kolhydrater -varav sockerarter"). About 18,000 distinct labels remain unmapped on purpose; the great majority are supplement actives (extracts, enzymes, probiotics, salts of minerals) and USDA / Frida detail rows, listed in `unmapped.json` and kept under `other_nutrients` / `per_100g_as_reported`. Mapped supplement codes: creatine, caffeine, taurine, beta-alanine, citrulline, carnitine, collagen, CoQ10, BCAA/EAA, amino acids.',
    'Vitamin A is stored as RAE/RE ug, vitamin E as alpha-tocopherol equivalents mg, niacin as mg; IU values are ignored in favour of the ug rows. Sources disagree on how these are measured; no conversions beyond units.',
    'Categories: the library keeps each source category list as-is. No unified category tree exists yet; Jev (TypeSafe) could classify the 217,000 names into one, but it needs a chat yes/no first and was not called.',
]:
    w('- ' + line)
w('')
w('## Folder size')
w('')
tot_b = du(ROOT)
w('| Folder | Size |')
w('|---|---:|')
for name, p in [('data/unified (products.jsonl, products.sqlite, dictionary)', U), ('data/raw (all collector output)', ROOT + '/data/raw'), ('logs', ROOT + '/logs'), ('scrapers + build', None)]:
    if p:
        w('| %s | %s |' % (name, mb(du(p))))
w('| scrapers + build | %s |' % mb(du(ROOT + '/scrapers') + du(ROOT + '/build')))
w('| **macro-library total** | **%s** (cap 10 GB) |' % mb(tot_b))
w('')
w('Files: `products.jsonl` %s, `products.sqlite` %s.' % (mb(os.path.getsize(U + '/products.jsonl')), mb(os.path.getsize(U + '/products.sqlite'))))
w('')
w('## How to query')
w('')
w('```sql')
w("-- per-100 g macros for one barcode")
w("select code, value, unit, source from nutrients where product_id='ean:7038010061844' and basis='per_100g';")
w("-- all products with at least 20 g protein and under 150 kcal per 100 g")
w("select name, brand, kcal, protein_g from products where protein_g>=20 and kcal<150 order by protein_g desc limit 20;")
w("-- every source's opinion of one product")
w("select source, url, kcal, protein_g, fat_g, carbs_g from product_sources where product_id='ean:7038010061844';")
w('```')
open(ROOT + '/COVERAGE.md', 'w', encoding='utf-8').write('\n'.join(out) + '\n')
json.dump({'total': total, 'folder_bytes': tot_b}, open(U + '/coverage_numbers.json', 'w'))
print('COVERAGE.md written', total, mb(tot_b))
