"""Build the slim app database (products.sqlite) from the JSONL shards.

The slim database is what the iOS app bundles and what the web app downloads.
Contract: Maxaubert/Makro, packages/contracts/products-db.md (v1, schema_version 2).

Usage:
  python tools/build_slim.py --data data --out products.sqlite --db-version 2026.10.18 \
      [--variant full|open] [--previous old.sqlite] [--built-at ISO] [--source-commit SHA]

Needs only the products, product_eans and nutrients shards, so it runs on a
fresh Linux checkout. The raw scraper output is not needed.
"""
import argparse
import gzip
import json
import os
import re
import sqlite3
import sys
import unicodedata
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import families as fam  # noqa: E402

SCHEMA_VERSION = 2

# Sources whose licences allow republishing (LICENSES.md, "open sources").
# The open variant keeps a product only if its primary source is in this set,
# because the numbers shown for a product come from its primary source.
OPEN_SOURCES = (
    'openfoodfacts',
    'openfoodfacts-nordic-global',
    'usda-fdc',
    'matvaretabellen',
    'frida-dk',
    'livsmedelsverket',
)

# The one place that maps a source slug to (display name, kind). Contract: `sources` table.
# kind is open_database, government, brand, shop or custom. A `shop` source is never verified,
# so a site that sells many brands is a shop; a brand's own site or store is a brand.
# The build fails if a product uses a slug that is not listed here.
SOURCES = {
    'custom': ('Your own food', 'custom'),
    # Open databases and government food tables
    'openfoodfacts': ('Open Food Facts', 'open_database'),
    'openfoodfacts-nordic-global': ('Open Food Facts', 'open_database'),
    'usda-fdc': ('USDA FoodData Central', 'government'),
    'matvaretabellen': ('Matvaretabellen', 'government'),
    'frida-dk': ('Frida (DTU Food)', 'government'),
    'livsmedelsverket': ('Livsmedelsverket', 'government'),
    # Brands (the producer's own site or store)
    'applied-nutrition': ('Applied Nutrition', 'brand'),
    'barebells': ('Barebells', 'brand'),
    'barebells-no': ('Barebells', 'brand'),
    'bulk': ('Bulk', 'brand'),
    'bulk-discontinued': ('Bulk (archived page)', 'brand'),
    'cellucor': ('Cellucor', 'brand'),
    'dymatize': ('Dymatize', 'brand'),
    'eldorado': ('Eldorado', 'brand'),
    'esn': ('ESN', 'brand'),
    'firstprice': ('First Price', 'brand'),
    'fjordland': ('Fjordland', 'brand'),
    'fulfil': ('Fulfil', 'brand'),
    'ghost': ('Ghost', 'brand'),
    'gilde': ('Gilde', 'brand'),
    'gorilla-mind': ('Gorilla Mind', 'brand'),
    'grandiosa': ('Grandiosa', 'brand'),
    'grenade': ('Grenade', 'brand'),
    'hennig-olsen': ('Hennig-Olsen', 'brand'),
    'kavli': ('Kavli', 'brand'),
    'kungmarkatta': ('Kung Markatta', 'brand'),
    'legion': ('Legion', 'brand'),
    'mills': ('Mills', 'brand'),
    'muscletech': ('MuscleTech', 'brand'),
    'myprotein': ('Myprotein', 'brand'),
    'myprotein-discontinued': ('Myprotein (archived page)', 'brand'),
    'myprotein-uk': ('Myprotein UK', 'brand'),
    'nidar': ('Nidar', 'brand'),
    'nocco': ('Nocco', 'brand'),
    'nutramino-dk': ('Nutramino', 'brand'),
    'optimum-nutrition': ('Optimum Nutrition', 'brand'),
    'prior': ('Prior', 'brand'),
    'q-meieriene': ('Q-Meieriene', 'brand'),
    'quest': ('Quest', 'brand'),
    'reflex': ('Reflex Nutrition', 'brand'),
    'ringnes': ('Ringnes', 'brand'),
    'saetre': ('Sætre', 'brand'),
    'scitec': ('Scitec Nutrition', 'brand'),
    'synnove': ('Synnøve', 'brand'),
    'tine': ('Tine', 'brand'),
    'toro': ('Toro', 'brand'),
    'transparent-labs': ('Transparent Labs', 'brand'),
    'tyngre': ('Tyngre', 'brand'),
    'weider': ('Weider', 'brand'),
    # Shops and shop data
    'apex-no': ('Apex', 'shop'),
    'bodybuilding': ('Bodybuilding.com', 'shop'),
    'bodylab-dk': ('Bodylab DK', 'shop'),
    'bodylab-no': ('Bodylab', 'shop'),
    'bodylab-se': ('Bodylab SE', 'shop'),
    'bodypower': ('Bodypower', 'shop'),
    'bodystore': ('Bodystore', 'shop'),
    'bodystore-discontinued': ('Bodystore (archived page)', 'shop'),
    'bodystore-dk': ('Bodystore DK', 'shop'),
    'bodystore-se': ('Bodystore SE', 'shop'),
    'coore-no': ('Coore', 'shop'),
    'diggbox-no': ('Diggbox', 'shop'),
    'goldenathlete': ('Golden Athlete', 'shop'),
    'gymgrossisten': ('Gymgrossisten', 'shop'),
    'gymgrossisten-discontinued': ('Gymgrossisten (archived page)', 'shop'),
    'gymgrossisten-se': ('Gymgrossisten SE', 'shop'),
    'halsafitnessbutiken': ('Hälsa & Fitnessbutiken', 'shop'),
    'halsokostbolaget': ('Hälsokostbolaget', 'shop'),
    'helsam-dk': ('Helsam', 'shop'),
    'helsekost-no': ('Helsekost', 'shop'),
    'ica-se': ('ICA', 'shop'),
    'kassalapp': ('Kassalapp', 'shop'),
    'kost1-no': ('Kost1', 'shop'),
    'life-no': ('Life', 'shop'),
    'life-no-discontinued': ('Life (archived page)', 'shop'),
    'life-se': ('Life SE', 'shop'),
    'matas-dk': ('Matas', 'shop'),
    'mmsports': ('MM Sports', 'shop'),
    'nordicpower-no': ('Nordic Power', 'shop'),
    'norgesgruppen': ('NorgesGruppen (Meny, Spar, Joker)', 'shop'),
    'proteinbolaget': ('Proteinbolaget', 'shop'),
    'proteincompany-no': ('Protein Company', 'shop'),
    'proteinfabrikken': ('Proteinfabrikken', 'shop'),
    'proteinfabrikken-discontinued': ('Proteinfabrikken (archived page)', 'shop'),
    'sportkost': ('Sportkost', 'shop'),
    'sportylab-no': ('Sportylab', 'shop'),
    'starnutrition-se': ('Star Nutrition', 'shop'),
    'tights': ('Tights.no', 'shop'),
    'tights-discontinued': ('Tights.no (archived page)', 'shop'),
    'tillskottsbolaget': ('Tillskottsbolaget', 'shop'),
    # Canonical single-ingredient products made in build/postprocess_jev.py. Their status is
    # `derived`, so they are never verified; `shop` keeps that true even if the status changed.
    'derived-jev': ('Makro canonical product', 'shop'),
}
SOURCE_KINDS = ('open_database', 'government', 'brand', 'shop', 'custom')

# Contract: Data quality. The code is the text before the first colon.
SUSPECT_FLAGS = frozenset((
    'no_nutrition', 'nutrition_text_only', 'nutrition_image_only', 'flavour_nutrition_shared_assumed',
    'flavour_table_ambiguous', 'variant_table_ambiguous', 'variants_share_one_nutrition_table',
    'flavour_macros_may_differ', 'bundle_or_multipack', 'per100_basis_unverified', 'per100_basis_assumed',
    'per100_derived_from_serving', 'per100_is_prepared_state', 'per100_prepared_state_only',
    'kcal_macro_mismatch', 'kj_kcal_mismatch', 'kj_dropped_inconsistent_with_kcal',
    'scraper_flag_macro_energy_mismatch', 'scraper_flag_kj_kcal_ratio', 'salt_sodium_mismatch',
    'sources_disagree', 'unit_assumed', 'unit_inferred_by_scraper', 'sodium_unit_assumed',
    'energy_unit_guessed', 'energy_unit_unclear', 'sugars_exceed_carbs', 'sat_fat_exceeds_fat',
    'macros_sum_over_100g', 'carbs_over_100g', 'protein_over_100g', 'fat_over_100g',
    'kcal_implausible_high', 'implausible_value_removed_by_collector',
    # Still to settle with the data; until then it counts as suspect (contract).
    'per_serving_only',
))
# Informational flags. Every `filled_from_<source>` is informational too.
INFO_FLAGS = frozenset((
    'missing_fibre', 'missing_salt', 'missing_kcal', 'missing_macros', 'ean_malformed',
    'ean_checksum_invalid', 'ingredients_discarded_junk', 'us_market_product', 'pure_compound',
    'derived_canonical',
))
_FILLED = 'filled_from_'
_DERIVED_CANONICAL = re.compile(r'derived_canonical_from_\d+_products$')
_FLAG_CODE = re.compile(r'[a-z0-9_-]+$')

NUTRIENTS = ('kcal', 'protein_g', 'fat_g', 'sat_fat_g', 'carbs_g', 'sugars_g', 'fibre_g', 'salt_g')
MACROS = ('kcal', 'protein_g', 'fat_g', 'carbs_g')

# Zero kcal rule (contract: Zero kcal). Products whose four macros are all 0 get NULL and
# `no_nutrition`, unless the name says water, a sweetener or salt, it is a diet drink in ml, or the product is a
# curated pure compound (creatine, caffeine, taurine). The CI test fails above this count.
MAX_ALL_ZERO = 275  # 259 on 2026-10-25 (water, sweeteners, salt, pure compounds), before diet drinks
_SWEETENER_WORDS = frozenset((
    'sukralose', 'sucralose', 'sweetener', 'sweeteners', 'sotstoff', 'sotningsmiddel',
    'sotningsmedel', 'sodemiddel', 'suketter', 'erythritol', 'erytritol',
))  # and every word starting with `stevi` (stevia, steviosa)
_SWEETENER_PHRASES = ('flavor drops', 'flavour drops', 'smaksdraper', 'zero drops', 'tasty drops')
_WATER_SALT_WORDS = frozenset((
    'vann', 'vatten', 'vand', 'water', 'eau', 'aqua', 'isklar', 'farris', 'imsdal', 'bonaqua', 'olden',
    'voss', 'evian', 'ramlosa', 'loka', 'pellegrino', 'sprudle',
    'salt', 'salz', 'sel',
))
_WATER_SALT_SUFFIXES = ('vann', 'vatten', 'salt', 'salz')  # mineralvann, kildevann, havsalt, jodsalz
# A name with one of these is a food that only mentions salt or water (chips, herring, a bar).
# A drink (per 100 ml) with one of these is a diet soft drink or energy drink: about 0 kcal is real.
_DIET_DRINK_WORDS = frozenset(('zero', 'light', 'lett', 'max', 'sukkerfri', 'sockerfri', 'sugarfree', 'diet'))
_ZERO_DENY = ('chips', 'sild', 'krydder', 'karamell', 'caramel', 'notter', 'nuts', 'lakris', 'popcorn', 'kjeks')

_LETTERS = {'ø': 'o', 'æ': 'ae', 'å': 'a', 'ä': 'a', 'ö': 'o', 'ü': 'u', 'ß': 'ss'}


def normalise(text):
    """Search normalisation. The app and the web app apply the same rule to the query.

    Lowercase, then ø->o, æ->ae, å->a (also ä, ö, ü, ß), then strip any other accents.
    """
    if not text:
        return ''
    text = text.lower()
    for k, v in _LETTERS.items():
        text = text.replace(k, v)
    text = unicodedata.normalize('NFKD', text)
    return ''.join(ch for ch in text if not unicodedata.combining(ch))


def canonical_ean(code):
    """Canonical barcode (contract: Barcodes), or None when it is not a barcode.

    Digits only; fewer than 13 digits are left-padded to 13; 14 digits starting with 0 drop it;
    no digits or more than 14 is not a barcode. No check-digit validation.
    """
    if code is None:
        return None
    digits = ''.join(ch for ch in str(code) if ch in '0123456789')
    if not digits or len(digits) > 14:
        return None
    if len(digits) < 13:
        return digits.zfill(13)
    if len(digits) == 14 and digits[0] == '0':
        return digits[1:]
    return digits


_QUANTITY = re.compile(r'\d+(?:[.,]\d+)?\s*(ml|cl|dl|ltr|liter|litre|l|kg|grams|gram|gr|g)(?!\w)')
_ML_UNITS = frozenset(('ml', 'cl', 'dl', 'ltr', 'liter', 'litre', 'l'))


def per_100_unit(pack_size, name):
    """`g` or `ml`: the unit the per-100 values are per (contract: per_100_unit).

    From a pack size written in the product name (the label text), else the pack size, else
    `g`. The name wins when the two disagree: some shops list a wrong pack size ('33cl' on a
    whey powder). Never from the category.
    """
    for text in (name, pack_size):
        m = _QUANTITY.search((text or '').lower())
        if m:
            return 'ml' if m.group(1) in _ML_UNITS else 'g'
    return 'g'


def normalise_quality(entries):
    """Map raw data_quality entries to the closed code list. Raises ValueError on an unknown code.

    `derived_canonical_from_N_products` becomes `derived_canonical`; a free-text note becomes
    `pure_compound` (the note text stays in nutrition-data). Duplicates are dropped.
    """
    out = []
    for e in entries:
        if _DERIVED_CANONICAL.match(e):
            e = 'derived_canonical'
        code = e.split(':', 1)[0]
        if not _FLAG_CODE.match(code):
            e = code = 'pure_compound'
        if code not in SUSPECT_FLAGS and code not in INFO_FLAGS and not code.startswith(_FILLED):
            raise ValueError('unknown data_quality code: %r' % e)
        if e not in out:
            out.append(e)
    return out


def zero_allowed(name, flags, unit='g'):
    """True when all-zero macros are plausible: water, sweeteners, salt, diet drinks, or a curated pure compound."""
    if any(f.split(':', 1)[0] == 'pure_compound' for f in flags):
        return True
    text = normalise(name)
    tokens = re.findall(r'\w+', text)
    if unit == 'ml' and any(t in _DIET_DRINK_WORDS for t in tokens):
        return True
    # Sweeteners first: "Stevia Drops Caramel" is a sweetener even though it names a flavour.
    if any(p in text for p in _SWEETENER_PHRASES):
        return True
    if any(t in _SWEETENER_WORDS or t.startswith('stevi') for t in tokens):
        return True
    if any(d in text for d in _ZERO_DENY) or any(t.endswith('bar') for t in tokens):
        return False
    return any(t in _WATER_SALT_WORDS or t.endswith(_WATER_SALT_SUFFIXES) for t in tokens)


def is_verified(p, flags, kind):
    """Contract: Verified."""
    macros = [p[c] for c in MACROS]
    return int(p['status'] == 'from_source'
               and all(v is not None for v in macros) and any(v != 0 for v in macros)
               and not any(f.split(':', 1)[0] in SUSPECT_FLAGS for f in flags)
               and kind != 'shop')


PRODUCT_COLUMNS = (
    'id', 'name', 'brand', 'pack_size', 'ean', 'flavour', 'category', 'serving_g',
    'per_100_unit', 'source', 'verified', 'status', 'data_quality',
    'kcal', 'protein_g', 'fat_g', 'sat_fat_g', 'carbs_g', 'sugars_g', 'fibre_g', 'salt_g',
)
# slim column -> shard column (only `source` is renamed)
_SHARD_NAME = {'source': 'primary_source'}


def read_shard(data_dir, manifest, table):
    info = manifest[table]
    cols = info['columns']
    for fn in info['files']:
        with gzip.open(os.path.join(data_dir, fn), 'rt', encoding='utf-8') as f:
            f.readline()  # header line with the column names
            for line in f:
                yield dict(zip(cols, json.loads(line)))


_KIND_RANK = {'brand': 3, 'government': 2, 'open_database': 1, 'shop': 0}


def apply_families(kept, flags_by_id, families, short_brands=frozenset(), reviewed=None):
    """Fold each flavour family into its best listing (tools/families.py, contract: Families).

    Returns (old id -> kept id, extra search text per kept id, per_100_unit per kept id).
    The kept listing keeps its own numbers; nothing is averaged. Checked again here, after the
    zero-kcal rule and the open-variant drops, so the 5% rule holds for the values in this file.
    Then two passes: a listing with no numbers joins a family when its name matches a member's,
    and families that end up with the same name and brand (sources disagreeing on one product,
    such as a shop and the brand's own site) become one when their kcal is within 15%.
    """
    unit = {i: per_100_unit(kept[i]['pack_size'], kept[i]['name']) for i in kept}

    lines = None

    def row(i):
        r = {n: kept[i][n] for n in NUTRIENTS}
        r.update(id=i, name=kept[i]['name'], brand=kept[i]['brand'], unit=unit[i])
        if lines is not None:
            r['_bkey'] = lines.brand_key(r['name'], r['brand'])
            r['_core'] = lines.core(r['name'], r['brand'])
        return r

    def rank(i):
        p = kept[i]
        kind = SOURCES[p['primary_source']][1]
        # The brand's own data first, then government tables, open databases, shops.
        return (p['kcal'] is not None, is_verified(p, flags_by_id[i], kind), _KIND_RANK.get(kind, 0),
                sum(p[n] is not None for n in NUTRIENTS), p['ean'] is not None)

    def best(ids):
        return max(sorted(ids), key=rank)  # max keeps the first (lowest id) on a tie

    lines = fam.Lines([row(i) for i in kept])

    # 1. Families from data/families.json, re-checked against their best listing.
    groups = []
    taken = set()
    for f in families:
        ids = [i for i in f['members'] if i in kept and i not in taken and kept[i]['kcal'] is not None]
        if len(ids) < 2:
            continue
        rep = best(ids)
        ids = [i for i in ids if i == rep or fam.compatible(row(i), row(rep))]  # ml and g count alike
        if len(ids) > 1:
            groups.append(set(ids))
            taken.update(ids)

    # 1b. Groups a model read as one product (Haiku, unsure ones checked by Sonnet; Max 2026-11-08):
    #     data/families_reviewed.json. Joined with any family their rows already belong to, then guarded
    #     by fam.reviewed_ok against the best listing of the whole group.
    group_of = {i: g for g in groups for i in g}
    # Unverified listings a model read as a duplicate of a verified product join it as "absorbed":
    # they do not take part in naming or the product-word check, so a shop's "Yt Drikkeyoghurt" can
    # fold into Tine's "YT Yoghurtdrikk Protein" without breaking that family apart (Max, 2026-11-08).
    absorbed = set()

    def verified_id(i):
        return bool(is_verified(kept[i], flags_by_id[i], SOURCES[kept[i]['primary_source']][1]))
    for f in reviewed or ():
        ids = [i for i in f['members'] if i in kept]
        if len(ids) < 2:
            continue
        parts, seen = [], set()
        for i in ids:
            g = group_of.get(i)
            if g is None:
                parts.append({i})
            elif id(g) not in seen:
                seen.add(id(g))
                parts.append(g)
        rep = best(set().union(*parts))
        ok = [part for part in parts if fam.reviewed_ok(row(best(part)), row(rep))]
        if len(ok) < 2:
            continue
        new = set().union(*ok)
        top = best(new)
        anchor = next(part for part in ok if top in part)
        if verified_id(top):
            for part in ok:
                if part is not anchor and not any(verified_id(i) for i in part):
                    absorbed.update(part)
        groups[:] = [g for g in groups if not any(g is part for part in ok)]
        groups.append(new)
        for i in new:
            group_of[i] = new
        taken.update(new)

    def name_of(g):
        g = (g - absorbed) or g
        rep = best(g)
        names = [fam.tidy_name(kept[i]['name'], kept[i]['brand'], short_brands) for i in sorted(g)]
        return fam.family_name(fam.tidy_name(kept[rep]['name'], kept[rep]['brand'], short_brands), names, kept[rep]['brand'])

    # 2. A listing with no numbers joins the product of the same brand and the same words (any order,
    #    sizes aside) that has numbers: in its family if it has one, else the two become a family.
    #    Listings with no numbers and no such product join each other. Nothing is lost: they have no
    #    numbers, and their barcodes and names move to the row that has them (sweep, 2026-11-08).
    in_group = {}
    for g in groups:
        for i in g:
            in_group[i] = g
    by_core = defaultdict(list)
    for i in sorted(kept):
        r = row(i)
        if r['_bkey'] and not fam.is_bundle(r['name']):
            by_core[(r['_bkey'], r['_core'], fam.variant_marks(r['name'], r['brand']))].append(i)
    for key in sorted(by_core, key=lambda k: (k[0], sorted(k[1]), sorted(k[2]))):
        ids = by_core[key]
        empty = [i for i in ids if i not in taken and all(kept[i][n] is None for n in NUTRIENTS)]
        full = [i for i in ids if kept[i]['kcal'] is not None]
        if not empty or len(ids) < 2:
            continue
        if full:
            target = best(full)
            g = in_group.get(target)
            if g is None:
                g = {target}
                groups.append(g)
                in_group[target] = g
                taken.add(target)
        else:
            g = set()
            groups.append(g)
        for i in empty:
            g.add(i)
            in_group[i] = g
            taken.add(i)
    groups = [g for g in groups if len(g) > 1]

    # 3. Families with the same name and brand are one product whose sources disagree (a shop and the
    #    brand's own site). Only when the winning listing is verified from a non-shop source, so the
    #    brand's own numbers settle it; otherwise the 5% rule stands and they stay apart.
    # A family whose name lost the product word ("Sur", "Max", "Ekologisk") is not one product line:
    # keep only its plain duplicates (third review, 2026-11-08).
    checked = []
    for full in groups:
        g = (full - absorbed) or full
        rep = best(g)
        line = lines.line(kept[rep]['name'], kept[rep]['brand'])
        names = [fam.tidy_name(kept[i]['name'], kept[i]['brand'], short_brands) for i in sorted(g)]
        common = fam.family_name(fam.tidy_name(kept[rep]['name'], kept[rep]['brand'], short_brands), names,
                                 kept[rep]['brand'], strict=True)
        same_words = len(g) < 2 or not fam.names_differ_core([row(i)['_core'] for i in g])
        if same_words or (common and line in fam.join_compounds(fam.words(common), lines.vocab)):
            checked.append(full)
            continue
        dups = defaultdict(set)
        for i in g:
            dups[row(i)['_core']].add(i)
        checked += [d for d in dups.values() if len(d) > 1]
    groups = checked

    merged_groups = {}
    for g in groups:
        rep = best(g)
        key = (' '.join(fam.words(name_of(g))), fam._brand_key(kept[rep]['brand']))
        other = merged_groups.get(key)
        if other is not None:
            a, b = kept[best(other)]['kcal'], kept[rep]['kcal']
            win = kept[best(other | g)]
            trusted = is_verified(win, flags_by_id[win['id']], SOURCES[win['primary_source']][1]) and \
                SOURCES[win['primary_source']][1] != 'shop'
            same_variant = fam.variant_marks(kept[best(other)]['name'], kept[best(other)]['brand']) == \
                fam.variant_marks(kept[rep]['name'], kept[rep]['brand'])
            # Only for the same product: both families hold a listing of the same name (YT Proteinpudding
            # Sjokolade at Tights and at tine.no). Different flavour sets that ended up with one name stay apart.
            def listing_names(grp):
                return {row(i)['_core'] for i in grp}
            shared = listing_names(other) & listing_names(g)
            if trusted and same_variant and key[1] and shared and fam.close(row(best(other)), row(rep), 0.15):
                other.update(g)
                continue
            key = key + (rep,)
        merged_groups[key] = g

    moved, extra = {}, {}
    for g in merged_groups.values():
        rep = best(g)
        p = kept[rep]
        extra[rep] = ' '.join(x for i in sorted(g) for x in (kept[i]['name'], kept[i]['flavour']) if x)
        p['name'] = name_of(g)
        for col in ('pack_size', 'flavour'):
            if len({kept[i][col] for i in g}) > 1:
                p[col] = None
        for i in g:
            if i != rep:
                moved[i] = rep
                del kept[i]
    return moved, extra, {i: unit[i] for i in kept}


def _dedupe_words(text):
    seen, out = set(), []
    for w in text.split():
        if w not in seen:
            seen.add(w)
            out.append(w)
    return ' '.join(out)


def build(data_dir, out, db_version, variant='full', previous=None, built_at='', source_commit='', stats=None, families=None):
    if variant not in ('full', 'open'):
        raise ValueError('variant must be full or open')
    if stats is None:
        stats = {}
    with open(os.path.join(data_dir, 'manifest.json'), encoding='utf-8') as f:
        manifest = json.load(f)

    kept = {}
    merged = {}  # old id -> id it was merged into
    stats['non_food_dropped'] = 0
    for p in read_shard(data_dir, manifest, 'products'):
        if p['merged_into']:
            merged[p['id']] = p['merged_into']
            continue
        if not p['norway_relevant'] or p['hidden']:
            continue
        if not (p['name'] or '').strip():
            continue
        if variant == 'open' and p['primary_source'] not in OPEN_SOURCES:
            continue
        if p['category'] == 'non_food':
            stats['non_food_dropped'] += 1
            continue
        kept[p['id']] = p

    unknown = sorted({p['primary_source'] for p in kept.values()} - set(SOURCES))
    if unknown:
        raise ValueError('sources missing from SOURCES: %s' % ', '.join(unknown))

    flags_by_id = {}
    for p in kept.values():
        flags_by_id[p['id']] = normalise_quality(json.loads(p['data_quality']) if p['data_quality'] else [])

    # Open variant: a value filled from a non-open source is dropped (contract: Variants).
    stats['open_values_dropped'] = 0
    stats['open_products_changed'] = 0
    if variant == 'open':
        changed = set()
        for n in read_shard(data_dir, manifest, 'nutrients'):
            pid = n['product_id']
            if (pid in kept and n['basis'] == 'per_100g' and n['code'] in NUTRIENTS
                    and n['source'] not in OPEN_SOURCES and kept[pid][n['code']] is not None):
                kept[pid][n['code']] = None
                changed.add(pid)
                stats['open_values_dropped'] += 1
        for pid in kept:
            flags = flags_by_id[pid]
            keep = [f for f in flags if not f.startswith(_FILLED) or f[len(_FILLED):] in OPEN_SOURCES]
            if keep != flags:
                changed.add(pid)
                flags_by_id[pid] = keep
        stats['open_products_changed'] = len(changed)

    # Zero kcal rule (contract: Zero kcal): all four macros 0 means missing, unless allowlisted.
    stats['all_zero_before'] = 0
    stats['all_zero_after'] = 0
    for p in kept.values():
        if all(p[c] == 0 for c in MACROS):
            stats['all_zero_before'] += 1
            flags = flags_by_id[p['id']]
            if zero_allowed(p['name'], flags, per_100_unit(p['pack_size'], p['name'])):
                stats['all_zero_after'] += 1
                continue
            for c in NUTRIENTS:
                if p[c] == 0:
                    p[c] = None
            if 'no_nutrition' not in flags:
                flags.append('no_nutrition')

    # Flavour families (data/families.json, made by build/jev_families.py). Contract: Families.
    if families is None:
        path = os.path.join(data_dir, 'families.json')
        families = json.load(open(path, encoding='utf-8'))['families'] if os.path.exists(path) else []
    short_brands = fam.capital_brands(p['brand'] for p in kept.values())
    rpath = os.path.join(data_dir, 'families_reviewed.json')
    reviewed = json.load(open(rpath, encoding='utf-8'))['families'] if os.path.exists(rpath) else []
    moved, extra_search, units = apply_families(kept, flags_by_id, families, short_brands, reviewed)
    stats['reviewed_groups'] = len(reviewed)

    # Unverified rows (Max, 2026-11-08): drop the ones with no numbers, and the ones that have a verified
    # version of the same brand and product line. Shop-only groceries with numbers stay.
    def _verified(p):
        return is_verified(p, flags_by_id[p['id']], SOURCES[p['primary_source']][1])
    lines = fam.Lines([dict(id=i, name=p['name'], brand=p['brand'], **{n: p[n] for n in NUTRIENTS}) for i, p in kept.items()])
    line_of = {i: (lines.brand_key(p['name'], p['brand']), lines.line(p['name'], p['brand'])) for i, p in kept.items()}
    verified_lines = {line_of[i] for i, p in kept.items() if line_of[i][0] and _verified(p)}
    dropped_empty = [i for i, p in kept.items() if not _verified(p) and p['kcal'] is None]
    dropped_twin = [i for i, p in kept.items() if not _verified(p) and line_of[i] in verified_lines
                    and p['kcal'] is not None]
    for i in dropped_empty + dropped_twin:
        del kept[i]
        extra_search.pop(i, None)
    stats['unverified_empty_dropped'] = len(dropped_empty)
    stats['unverified_with_verified_twin_dropped'] = len(dropped_twin)
    dropped = set(dropped_empty) | set(dropped_twin)
    moved = {old: new for old, new in moved.items() if new not in dropped}
    stats['family_products'] = len(extra_search)
    stats['family_members_folded'] = len(moved)

    if os.path.exists(out):
        os.remove(out)
    db = sqlite3.connect(out)
    db.executescript("""
create table products(
  id text primary key,
  name text not null,
  brand text,
  pack_size text,
  ean text,
  flavour text,
  category text,
  serving_g real,
  per_100_unit text not null check (per_100_unit in ('g', 'ml')),
  source text not null,
  verified integer not null check (verified in (0, 1)),
  status text,
  data_quality text,
  kcal real, protein_g real, fat_g real, sat_fat_g real, carbs_g real, sugars_g real, fibre_g real, salt_g real,
  search_text text not null
);
create table sources(slug text primary key, display_name text not null, kind text not null);
create table product_eans(product_id text not null, ean text not null);
create table redirects(old_id text primary key, new_id text not null);
create table removed(id text primary key);
create table meta(key text primary key, value text not null);
""")
    used = sorted({p['primary_source'] for p in kept.values()} | {'custom'})
    db.executemany('insert into sources values (?, ?, ?)', [(s,) + SOURCES[s] for s in used])

    rows = []
    stats['verified'] = 0
    stats['per_100_ml'] = 0
    for p in kept.values():
        flags = flags_by_id[p['id']]
        kind = SOURCES[p['primary_source']][1]
        derived = {
            'ean': canonical_ean(p['ean']),
            'per_100_unit': units[p['id']],
            'verified': is_verified(p, flags, kind),
            'data_quality': json.dumps(flags, ensure_ascii=False) if (flags or p['data_quality'] is not None) else None,
        }
        stats['verified'] += derived['verified']
        stats['per_100_ml'] += derived['per_100_unit'] == 'ml'
        derived['name'] = fam.display_name(p['name'], p['brand'], lines, short_brands)
        derived['brand'] = fam.tidy_brand(p['brand'], short_brands)
        vals = [derived[c] if c in derived else p[_SHARD_NAME.get(c, c)] for c in PRODUCT_COLUMNS]
        search = _dedupe_words(normalise(' '.join(x for x in (p['name'], p['brand'], p['flavour'], extra_search.get(p['id'])) if x)))
        rows.append(vals + [search])
    db.executemany('insert into products values (%s)' % ','.join('?' * (len(PRODUCT_COLUMNS) + 1)), rows)

    # Every barcode a product is known by, canonical. Two products may not share one.
    owner = {}
    pairs = [(e['product_id'], e['ean']) for e in read_shard(data_dir, manifest, 'product_eans')]
    pairs += [(pid, p['ean']) for pid, p in kept.items()]
    for pid, raw in pairs:
        pid = moved.get(pid, pid)
        if pid not in kept:
            continue
        ean = canonical_ean(raw)
        if ean is None:
            continue
        if owner.setdefault(ean, pid) != pid:
            raise ValueError('barcode %s belongs to both %s and %s' % (ean, owner[ean], pid))
    db.executemany('insert into product_eans values (?, ?)', sorted((pid, ean) for ean, pid in owner.items()))

    # Merged products: old id -> final kept id. Targets that are not in this database are dropped.
    redirects = {}
    for old, new in merged.items():
        seen = {old}
        while new in merged and new not in seen:
            seen.add(new)
            new = merged[new]
        new = moved.get(new, new)
        if new in kept:
            redirects[old] = new
    redirects.update(moved)

    # Ids that were in the previous release and are gone now, with no successor: record them,
    # so an old favourite or log entry can tell "gone" from "unknown id".
    removed = set()
    if previous:
        prev = sqlite3.connect(previous)
        try:
            old_ids = {r[0] for r in prev.execute('select id from products')}
            old_ids |= {r[0] for r in prev.execute('select old_id from redirects')}
            old_ids |= {r[0] for r in prev.execute('select id from removed')}
        finally:
            prev.close()
        for oid in old_ids:
            if oid not in kept and oid not in redirects:
                removed.add(oid)
    db.executemany('insert into redirects values (?, ?)', sorted(redirects.items()))
    db.executemany('insert into removed values (?)', [(i,) for i in sorted(removed)])
    stats['removed'] = len(removed)

    db.executescript("""
create unique index ux_product_eans_ean on product_eans(ean);
create virtual table products_fts using fts5(
  search_text, content='products', content_rowid='rowid', tokenize='unicode61', prefix='2 3');
insert into products_fts(rowid, search_text) select rowid, search_text from products;
insert into products_fts(products_fts) values('optimize');
""")
    meta = {
        'db_version': db_version,
        'schema_version': str(SCHEMA_VERSION),
        'variant': variant,
        'product_count': str(len(kept)),
        'built_at': built_at,
        'source_commit': source_commit,
    }
    if variant == 'open':
        meta['open_sources'] = ','.join(OPEN_SOURCES)
    db.executemany('insert into meta values (?, ?)', sorted(meta.items()))
    db.execute('pragma user_version = %d' % SCHEMA_VERSION)
    db.commit()
    db.execute('vacuum')
    db.close()
    stats['products'] = len(kept)
    return len(kept)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--data', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--db-version', required=True)
    ap.add_argument('--variant', default='full', choices=('full', 'open'))
    ap.add_argument('--previous')
    ap.add_argument('--built-at', default='')
    ap.add_argument('--source-commit', default='')
    a = ap.parse_args(argv)
    stats = {}
    n = build(a.data, a.out, a.db_version, a.variant, a.previous, a.built_at, a.source_commit, stats)
    print('%s: %d products, %.1f MB' % (a.out, n, os.path.getsize(a.out) / 1e6))
    print(json.dumps(stats, sort_keys=True))


if __name__ == '__main__':
    sys.exit(main())
