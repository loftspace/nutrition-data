"""Build the unified macro library.

python build.py            -> data/unified/{nutrient_dictionary.json, label_mappings.json, unmapped.json, products.jsonl, products.sqlite, stats.json}
COVERAGE.md is written by coverage.py (reads stats.json + the sqlite).
"""
import collections
import json
import math
import os
import re
import sqlite3
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adapters
import nutr

OUT = 'C:/Users/Admin/Documents/Claude/zz-Misc/macro-library/data/unified'
os.makedirs(OUT, exist_ok=True)

# ------------------------------------------------------------------ RAW FOLDER SWITCH (second pass, 2026-10-16)
# The flavour-fix collector wrote one record per page into *-v2 folders. These replace the first-pass folders, which stay on disk but are NOT read
# (reading both would count every product twice). Set USE_V2 = False to read the first-pass folders again (only useful for comparing counts; the old
# page_variant_split_by_flavour logic no longer exists in adapters.py).
USE_V2 = True
RAW_FOLDERS = {'tights': 'tights-v2', 'gymgrossisten': 'gymgrossisten-v2', 'bodystore': 'bodystore-v2', 'proteinfabrikken': 'proteinfabrikken-v2', 'bulk': 'bulk-v2'} if USE_V2 else {}
SUPERSEDED_FOLDERS = ['tights', 'gymgrossisten', 'bodystore', 'proteinfabrikken', 'bulk'] if USE_V2 else []
adapters.FOLDERS.update(RAW_FOLDERS)

RANK = {}
for s in ['tine', 'gilde', 'prior', 'q-meieriene', 'fjordland', 'grandiosa', 'nidar', 'saetre', 'toro', 'firstprice', 'eldorado', 'mills', 'ringnes', 'synnove', 'kavli',
          'hennig-olsen', 'tights', 'gymgrossisten', 'bodystore', 'proteinfabrikken', 'myprotein', 'bulk']:
    RANK[s] = 1           # pack label: producer or shop product page
for _name, _fn in adapters.SOURCES:
    RANK.setdefault(_name, 1)      # every shop / producer / brand page source is a pack-label source
RANK['brands'] = 1
RANK['kassalapp'] = 2
RANK['norgesgruppen'] = 3
RANK['openfoodfacts'] = 4
RANK['openfoodfacts-nordic-global'] = 4
RANK['usda-fdc'] = 5      # branded; USDA generic (foundation / sr_legacy) are 'generic' kind -> 6
GENERIC_RANK = 6

PROMOTE = {
    'basis_unverified_per_100g_or_per_serving': 'per100_basis_unverified',
    'per100_is_prepared_state': 'per100_is_prepared_state',
    'flavour_table_not_matched': 'flavour_table_not_matched',
    'flavour_table_ambiguous': 'flavour_table_ambiguous',
    'per100_derived_from_serving': 'per100_derived_from_serving',
    'per100_derived_from_serving_size': 'per100_derived_from_serving',
    'per100derived_from_serving_size': 'per100_derived_from_serving',
    'basis_not_stated_assumed_per_100g': 'per100_basis_assumed',
    'multiple_tables_variant_unidentified_first_used': 'variant_table_ambiguous',
    'bundle_or_multipack': 'bundle_or_multipack',
    'unit_inferred': 'unit_inferred_by_scraper',
    'gym_energy_guess': 'energy_unit_guessed',
    'gym_energy_unclear': 'energy_unit_unclear',
    'us_market_product': 'us_market_product',
    'variants_share_one_nutrition_table': 'variants_share_one_nutrition_table',
    'flavour_nutrition_shared_assumed': 'flavour_nutrition_shared_assumed',
    'nutrition_page_level_not_flavour_verified': 'flavour_nutrition_shared_assumed',
    'implausible_value': 'implausible_value_removed_by_collector',
    'energy_kj_kcal_inconsistent': 'scraper_flag_kj_kcal_ratio',
    'basis_unverified_assumed_per_100': 'per100_basis_assumed',
    'basis_not_printed_assumed_per_100g_or_100ml': 'per100_basis_assumed',
    'no_per_100_table_only_prepared': 'per100_is_prepared_state',
    'per100_prepared_state_only_not_mapped': 'per100_prepared_state_only',
    'gym_kj_dropped_inconsistent': 'kj_dropped_inconsistent_with_kcal',
    'multiple_tables_first_per100_used': 'variant_table_ambiguous',
    'ingredients_text_discarded_not_an_ingredient_list': 'ingredients_discarded_junk',
    'off_obsolete': 'off_obsolete',
    'per100_missing_serving_only': 'per_serving_only',
    'nutrition_image_only': 'nutrition_image_only',
    'nutrition_from_text_block': 'nutrition_text_only',
    'flavour_macros_may_differ_see_description': 'flavour_macros_may_differ',
    'no_nutrition_on_page': 'no_nutrition',
    'no_nutrition_in_off': 'no_nutrition',
    'text_only_no_table': 'nutrition_text_only',
    'macro_energy_mismatch': 'scraper_flag_macro_energy_mismatch',
    'kj_kcal_ratio_off': 'scraper_flag_kj_kcal_ratio',
}


# -------------------------------------------------------------------- EAN
def gtin_canon(raw):
    if raw is None:
        return None, None
    d = re.sub(r'\D', '', str(raw))
    if not d or len(d) > 14 or len(d) < 8:
        return None, 'ean_malformed' if d else None
    if len(d) in (9, 10, 11):
        return None, 'ean_malformed'
    d14 = d.zfill(14)
    digs = [int(x) for x in d14]
    s = sum(digs[i] * (3 if i % 2 == 0 else 1) for i in range(13))
    chk = (10 - s % 10) % 10
    if chk != digs[13]:
        return None, 'ean_checksum_invalid'
    if d14[0] == '0':
        return d14[1:], None
    return d14, None


# --------------------------------------------------------------- mapping
LABEL_MAP = collections.defaultdict(collections.Counter)     # (source, norm label, unit) -> code counts
UNMAPPED = collections.Counter()                              # (source, norm label, unit, reason)
UNMAPPED_EX = {}
IGNORED = collections.Counter()
UNIT_ASSUMED = collections.Counter()


def map_entries(entries, source, ctx):
    """-> (codes {code: [value, qual]}, other [(label, value, unit)])"""
    codes = {}
    other = []
    ents = entries
    if source == 'usda-fdc':
        def sk(e):
            try:
                return float(e[4])
            except Exception:
                return 9e9
        ents = sorted(entries, key=sk)
    for (label, val, unit, qual, key) in ents:
        code, factor, why = nutr.map_label(label, unit, key=key, source=source)
        if code is None:
            if why.startswith('ignored'):
                IGNORED[(source, nutr.norm_label(label), why)] += 1
            else:
                k = (source, nutr.norm_label(label) or str(label), nutr.norm_unit(unit), why)
                UNMAPPED[k] += 1
                UNMAPPED_EX.setdefault(k, label)
                other.append((label, val, unit))
            continue
        if why == 'unit_assumed':
            if code == 'sodium_mg':
                factor = 1000.0 if abs(val) <= 5 else 1.0
                ctx.setdefault('flags', set()).add('sodium_unit_assumed')
            elif nutr.DICT[code]['group'] not in ('macro', 'energy'):
                ctx.setdefault('flags', set()).add('unit_assumed')
        v = val * factor
        if code in ('kcal', 'kj', 'salt_g', 'sodium_mg') or True:
            v = round(v, 6)
        LABEL_MAP[(source, nutr.norm_label(label), nutr.norm_unit(unit))][code] += 1
        if code in codes:
            continue
        codes[code] = [v, qual]
    return codes, other


def derive(codes, flags):
    """kcal from kJ; salt <-> sodium. Marks derived codes."""
    derived = {}
    if 'kcal' not in codes and 'kj' in codes:
        codes['kcal'] = [round(codes['kj'][0] / 4.184, 1), None]
        derived['kcal'] = 'kj/4.184'
    if 'salt_g' not in codes and 'sodium_mg' in codes:
        codes['salt_g'] = [round(codes['sodium_mg'][0] * 2.5 / 1000, 3), codes['sodium_mg'][1]]
        derived['salt_g'] = 'sodium_mg*2.5/1000'
    if 'sodium_mg' not in codes and 'salt_g' in codes:
        codes['sodium_mg'] = [round(codes['salt_g'][0] * 400, 1), codes['salt_g'][1]]
        derived['sodium_mg'] = 'salt_g*400'
    return derived


def g(codes, c):
    v = codes.get(c)
    return v[0] if v else None


def quality(codes, derived):
    """Return list of data_quality strings for a per-100 dict {code: [value, qual]}."""
    fl = []
    if not codes:
        return ['no_nutrition']
    kcal, kj = g(codes, 'kcal'), g(codes, 'kj')
    p, f, c = g(codes, 'protein_g'), g(codes, 'fat_g'), g(codes, 'carbs_g')
    if kcal is None:
        fl.append('missing_kcal')
    if kcal is not None and (p is None or f is None or c is None):
        fl.append('missing_macros:' + ','.join(n for n, v in (('protein', p), ('fat', f), ('carbs', c)) if v is None))
    if kcal is not None and g(codes, 'salt_g') is None and g(codes, 'sodium_mg') is None:
        fl.append('missing_salt')
    if kcal is not None and g(codes, 'fibre_g') is None:
        fl.append('missing_fibre')
    if kcal is not None and 'kcal' not in derived and kj is not None and kcal > 5:
        r = kj / (kcal * 4.184)
        if r < 0.88 or r > 1.12:
            fl.append('kj_kcal_mismatch: kj %.0f vs kcal %.0f' % (kj, kcal))
    if kcal is not None and p is not None and f is not None and c is not None:
        exp = 4 * p + 4 * c + 9 * f + 2 * (g(codes, 'fibre_g') or 0) + 7 * (g(codes, 'alcohol_g') or 0) + 2.4 * (g(codes, 'polyols_g') or 0)
        exp4 = 4 * p + 4 * c + 9 * f
        diff = min(abs(kcal - exp), abs(kcal - exp4))
        if diff > 20 and diff > 0.15 * max(kcal, exp, 1):
            fl.append('kcal_macro_mismatch: kcal %.0f vs 4/4/9 estimate %.0f' % (kcal, exp4))
    if p is not None and f is not None and c is not None and p + f + c > 105:
        fl.append('macros_sum_over_100g: %.0f g (per-100 g may be per-serving or wrong unit)' % (p + f + c))
    if kcal is not None and kcal > 910:
        fl.append('kcal_implausible_high: %.0f' % kcal)
    sf = g(codes, 'sat_fat_g')
    if sf is not None and f is not None and sf > f + 0.5:
        fl.append('sat_fat_exceeds_fat')
    sg = g(codes, 'sugars_g')
    if sg is not None and c is not None and sg > c + 0.5:
        fl.append('sugars_exceed_carbs')
    if 'salt_g' not in derived and 'sodium_mg' not in derived and g(codes, 'salt_g') is not None and g(codes, 'sodium_mg') is not None:
        s_, n_ = g(codes, 'salt_g'), g(codes, 'sodium_mg')
        if s_ > 0.05 and (n_ * 2.5 / 1000 > s_ * 1.4 or n_ * 2.5 / 1000 < s_ * 0.6):
            fl.append('salt_sodium_mismatch')
    for k in ('protein_g', 'fat_g', 'carbs_g'):
        v = g(codes, k)
        if v is not None and v > 100.5:
            fl.append('%s_over_100g' % k.split('_')[0])
    return fl


# ---------------------------------------------------------------- load
t0 = time.time()
cands = []
per_source_raw = collections.Counter()
for name, fn in adapters.SOURCES:
    n = 0
    for c in fn():
        n += 1
        adapters.finalize(c)
        cands.append(c)
        per_source_raw[c['source']] += 1
    print('loaded', name, n, round(time.time() - t0), 's', flush=True)
# guard: the superseded first-pass folders must not have been read
bad = [f for f in SUPERSEDED_FOLDERS if f in adapters.READ]
assert not bad, 'superseded raw folders were read: %s' % bad
print('raw folders read:', len(adapters.READ), 'superseded and skipped:', SUPERSEDED_FOLDERS, flush=True)
dropped = collections.defaultdict(dict)
for (s_, why), n_ in sorted(adapters.Drops.counts.items()):
    dropped[s_][why] = n_
dropped['norgesgruppen']['nonfood_no_nutrition'] = getattr(adapters.a_ng, 'dropped', 0)
dropped = {k: v for k, v in dropped.items() if v}
print('candidates', len(cands), {k: sum(v.values()) for k, v in dropped.items()}, flush=True)

# ------------------------------------------------------- map each candidate
for c in cands:
    ctx = {}
    c['codes100'], c['other100'] = map_entries(c['per100'], c['source'], ctx)
    c['derived100'] = derive(c['codes100'], ctx)
    c['codes_s'], c['other_s'] = map_entries(c['perserv'], c['source'], ctx)
    c['derived_s'] = derive(c['codes_s'], ctx)
    c['ean_c'], ean_flag = gtin_canon(c['ean'])
    c['eans_c'] = []
    for e_ in [c['ean']] + list(c.get('eans_extra') or []):
        ec, _f = gtin_canon(e_)
        if ec and ec not in c['eans_c']:
            c['eans_c'].append(ec)
    if c['eans_c'] and not c['ean_c']:
        c['ean_c'] = c['eans_c'][0]
        ean_flag = None
    c['q'] = []
    if ean_flag:
        c['q'].append(ean_flag)
    c['q'] += sorted(ctx.get('flags', []))
    c['q'] += [PROMOTE[f] for f in c['flags'] if f in PROMOTE]
    c['q'] += quality(c['codes100'], c['derived100'])
    if not c['codes100'] and c['codes_s']:
        c['q'].append('per_serving_only')
    for k in ('per100', 'perserv'):
        pass
print('mapped', round(time.time() - t0), 's', flush=True)


def ncodes(c):
    return len(c['codes100'])


def eligible(c):
    return 'kcal' in c['codes100']


def sortkey(c):
    r = GENERIC_RANK if c['kind'] == 'generic' else RANK.get(c['source'], 1)
    bad = sum(1 for q in c['q'] if q.startswith(('kcal_macro_mismatch', 'macros_sum_over_100g', 'kj_kcal_mismatch', 'per100_basis_unverified', 'per100_derived', 'kcal_implausible')))
    return (0 if eligible(c) else 1, 1 if c.get('gone') else 0, r, bad, -ncodes(c))


# ------------------------------------------------------------------ group
# EAN merge across shops AND countries; a candidate may carry several EANs (flavours / sizes of one page): union-find over candidates
uf = list(range(len(cands)))


def find(x):
    while uf[x] != x:
        uf[x] = uf[uf[x]]
        x = uf[x]
    return x


first_by_ean = {}
for i, c in enumerate(cands):
    for e_ in c['eans_c']:
        if e_ in first_by_ean:
            a_, b_ = find(i), find(first_by_ean[e_])
            if a_ != b_:
                uf[max(a_, b_)] = min(a_, b_)
        else:
            first_by_ean[e_] = i
groups = collections.OrderedDict()
for i, c in enumerate(cands):
    key = ('ean', find(i)) if c['eans_c'] else ('src', c['source'], c['source_id'])
    groups.setdefault(key, []).append(c)
print('groups', len(groups), flush=True)


def agree(a, b, code):
    x, y = g(a['codes100'], code), g(b['codes100'], code)
    return x, y


def pick_first(cs, field):
    for c in cs:
        v = c.get(field)
        if v:
            return v, c['source']
    return None, None


products = []
used_ids = set()
dup_merged = 0
kcal_tol = lambda x, y: abs(x - y) <= max(20, 0.15 * max(x, y))
for key, cs in groups.items():
    cs.sort(key=sortkey)
    prim = cs[0]
    all_eans = []
    for c_ in cs:
        for e_ in ([c_['ean_c']] if c_['ean_c'] else []) + c_['eans_c']:
            if e_ not in all_eans:
                all_eans.append(e_)
    pid = ('ean:' + all_eans[0]) if all_eans else '%s:%s' % (prim['source'], prim['source_id'])
    if pid in used_ids:
        n = 2
        while '%s~%d' % (pid, n) in used_ids:
            n += 1
        pid = '%s~%d' % (pid, n)
    used_ids.add(pid)
    prov = {}
    rec = {'id': pid}
    for field in ('name', 'brand', 'pack_size', 'flavour'):
        v, s = pick_first(cs, field)
        rec[field] = v
        if s:
            prov[field] = s
    rec['ean'] = all_eans[0] if all_eans else None
    rec['all_eans'] = all_eans
    if rec['ean']:
        prov['ean'] = [c['source'] for c in cs if c['ean_c']][0]
    prio = ['NO', 'SE', 'DK', 'EU', 'UK', 'US', 'other']
    regs = sorted({c_['region'] for c_ in cs}, key=lambda x: prio.index(x) if x in prio else 99)
    rec['region'] = regs[0]
    rec['regions'] = regs
    rec['norway_relevant'] = any(c_['nr'] for c_ in cs)
    rec['norway_relevant_via'] = ('norwegian_source' if 'NO' in regs else 'nordic_source' if any(c_['nr'] and c_['region'] in ('SE', 'DK') for c_ in cs) else
                                  'eu_uk_online_shop_or_nordic_database' if rec['norway_relevant'] else 'none')
    rec['discontinued'] = all(c_.get('gone') for c_ in cs)
    cats, s = pick_first(cs, 'categories')
    rec['categories'] = cats or []
    ing, s = pick_first(cs, 'ingredients')
    rec['ingredients'] = ing
    if s:
        prov['ingredients'] = s
    al, s = pick_first(cs, 'allergens')
    rec['allergens'] = al
    if s:
        prov['allergens'] = s
    # serving + per_serving
    per_s = None
    for c in cs:
        if c['codes_s']:
            per_s = c
            break
    rec['serving_g'] = None
    rec['serving_text'] = None
    for c in ([per_s] if per_s else []) + cs:
        if c['serving_g']:
            rec['serving_g'] = c['serving_g']
            rec['serving_text'] = c['serving_text']
            prov['serving'] = c['source']
            break
    rec['per_100g'] = {code: v[0] for code, v in prim['codes100'].items()}
    quals = {code: v[1] for code, v in prim['codes100'].items() if v[1]}
    prov100 = {code: prim['source'] for code in rec['per_100g']}
    dq = list(prim['q'])
    # fill gaps from agreeing sources
    filled = collections.defaultdict(list)
    if 'kcal' in prim['codes100']:
        for o in cs[1:]:
            if 'kcal' in o['codes100'] and kcal_tol(prim['codes100']['kcal'][0], o['codes100']['kcal'][0]) and o['source'] != prim['source']:
                for code, v in o['codes100'].items():
                    if code not in rec['per_100g'] and code not in ('kj',) and not (code in o['derived100']):
                        rec['per_100g'][code] = v[0]
                        prov100[code] = o['source']
                        if v[1]:
                            quals[code] = v[1]
                        filled[o['source']].append(code)
    for s, codes in filled.items():
        dq.append('filled_from_%s:%s' % (s, ','.join(sorted(codes)[:12]) + ('...' if len(codes) > 12 else '')))
    prov['per_100g'] = prov100
    for code, how in prim['derived100'].items():
        prov['per_100g'][code] = '%s (derived: %s)' % (prim['source'], how)
    rec['per_100g_qualifiers'] = quals
    rec['per_serving'] = {code: v[0] for code, v in (per_s['codes_s'] if per_s else {}).items()}
    if per_s:
        prov['per_serving'] = per_s['source']
    rec['other_nutrients'] = [{'label': l, 'value': v, 'unit': u, 'basis': 'per_100g'} for (l, v, u) in prim['other100']][:60]
    if per_s:
        rec['other_nutrients'] += [{'label': l, 'value': v, 'unit': u, 'basis': 'per_serving'} for (l, v, u) in per_s['other_s']][:60]
    # cross-source disagreements
    dis = []
    if len(cs) > 1:
        for code, tol_abs, tol_rel in (('kcal', 20, 0.15), ('protein_g', 3, 0.25), ('fat_g', 3, 0.25), ('carbs_g', 3, 0.25)):
            vals = {}
            for c in cs:
                if code in c['codes100'] and code not in c['derived100']:
                    vals.setdefault(c['source'], c['codes100'][code][0])
            if len(vals) >= 2:
                mx, mn = max(vals.values()), min(vals.values())
                if mx - mn > tol_abs and (mx - mn) > tol_rel * max(mx, 1e-9):
                    dis.append({'code': code, 'values': vals})
        for d in dis:
            dq.append('sources_disagree:' + d['code'])
    rec['source_disagreements'] = dis
    # source entries
    srcs = []
    for c in cs:
        srcs.append({
            'source': c['source'], 'source_id': c['source_id'], 'url': c['url'], 'fetched_on': c['fetched_on'], 'is_primary': c is prim, 'kind': c['kind'],
            'region': c['region'], 'norway_relevant': c['nr'], 'page_gone': bool(c.get('gone')),
            'name': c['name'], 'brand': c['brand'],
            'per_100g': {code: v[0] for code, v in c['codes100'].items()},
            'per_100g_as_reported': [[l, v, u] + (['<'] if q else []) for (l, v, u, q, k) in c['per100']],
            'per_serving_as_reported': [[l, v, u] + (['<'] if q else []) for (l, v, u, q, k) in c['perserv']] if c['perserv'] else None,
            'flags': sorted(set(c['flags'] + c['q'])) if c is not prim else sorted(set(c['flags'])),
            'extra': c['extra'] or None,
        })
    rec['sources'] = srcs
    rec['field_provenance'] = prov
    rec['status'] = 'from_source'
    rec['kind'] = prim['kind']
    seen = set()
    rec['data_quality'] = [x for x in dq if not (x in seen or seen.add(x))]
    if len(cs) > 1:
        dup_merged += len(cs) - 1
    products.append(rec)
print('products', len(products), 'merged dupes', dup_merged, round(time.time() - t0), 's', flush=True)

# ------------------------------------------------------------ dictionary
used_codes = collections.Counter()
for r in products:
    for c in r['per_100g']:
        used_codes[c] += 1
    for c in r['per_serving']:
        used_codes[c] += 1
alias_by_code = collections.defaultdict(list)
for a, cs_ in nutr.ALIAS.items():
    for c in cs_:
        alias_by_code[c].append(a)
dict_out = []
for code, spec in sorted(nutr.DICT.items(), key=lambda kv: (kv[1]['group'], kv[0])):
    dict_out.append(dict(spec, aliases=sorted(alias_by_code.get(code, [])), products_with_value=used_codes.get(code, 0)))
json.dump({'generated': time.strftime('%Y-%m-%d'), 'note': 'Canonical nutrient codes. unit is the unit values are stored in. Values per 100 g (or 100 ml) unless the field is per_serving. Source labels are matched after lower-casing, folding nordic letters and removing bullets / "of which" prefixes.',
           'nutrients': dict_out}, open(OUT + '/nutrient_dictionary.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
lm = collections.defaultdict(dict)
for (s, l, u), cnt in LABEL_MAP.items():
    lm[s]['%s|%s' % (l, u or '')] = dict(cnt)
json.dump(lm, open(OUT + '/label_mappings.json', 'w', encoding='utf-8'), ensure_ascii=False)
um = [{'source': s, 'label': UNMAPPED_EX.get((s, l, u, w), l), 'normalised': l, 'unit': u, 'reason': w, 'count': n} for (s, l, u, w), n in UNMAPPED.most_common()]
json.dump({'note': 'Labels no rule maps with certainty. Never guessed. The values are kept in products.jsonl under other_nutrients (primary source only) and per source in per_100g_as_reported.',
           'distinct_label_unit_pairs': len(um), 'total_occurrences': sum(UNMAPPED.values()), 'unmapped': um,
           'deliberately_ignored': [{'source': s, 'label': l, 'reason': w, 'count': n} for (s, l, w), n in IGNORED.most_common()]},
          open(OUT + '/unmapped.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
print('dictionary written; unmapped distinct', len(um), flush=True)

# ---------------------------------------------------------------- jsonl
with open(OUT + '/products.jsonl', 'w', encoding='utf-8') as f:
    for r in products:
        f.write(json.dumps(r, ensure_ascii=False, separators=(',', ':')) + '\n')
print('jsonl written', os.path.getsize(OUT + '/products.jsonl') // 1e6, 'MB', round(time.time() - t0), 's', flush=True)

# ---------------------------------------------------------------- sqlite
db_path = OUT + '/products.sqlite'
if os.path.exists(db_path):
    os.remove(db_path)
db = sqlite3.connect(db_path)
db.executescript("""
PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;
CREATE TABLE nutrient_dictionary(code TEXT PRIMARY KEY, unit TEXT, grp TEXT, name_en TEXT, name_nb TEXT, aliases TEXT);
CREATE TABLE products(
  id TEXT PRIMARY KEY, name TEXT, brand TEXT, pack_size TEXT, ean TEXT, kind TEXT, flavour TEXT, categories TEXT, ingredients TEXT, allergens TEXT,
  serving_g REAL, primary_source TEXT, n_sources INTEGER, status TEXT, data_quality TEXT,
  region TEXT, regions TEXT, norway_relevant INTEGER, discontinued INTEGER, all_eans TEXT,
  kcal REAL, protein_g REAL, fat_g REAL, sat_fat_g REAL, carbs_g REAL, sugars_g REAL, fibre_g REAL, salt_g REAL, kj REAL);
CREATE TABLE product_sources(
  product_id TEXT, source TEXT, source_id TEXT, url TEXT, fetched_on TEXT, is_primary INTEGER, kind TEXT, name TEXT, brand TEXT,
  region TEXT, norway_relevant INTEGER, page_gone INTEGER,
  kcal REAL, protein_g REAL, fat_g REAL, carbs_g REAL, per_100g_json TEXT, flags TEXT);
CREATE TABLE product_eans(product_id TEXT, ean TEXT);
CREATE TABLE nutrients(product_id TEXT, basis TEXT, code TEXT, value REAL, unit TEXT, qualifier TEXT, source TEXT);
""")
db.executemany('INSERT INTO nutrient_dictionary VALUES (?,?,?,?,?,?)', [(d['code'], d['unit'], d['group'], d['name_en'], d['name_nb'], ', '.join(d['aliases'])) for d in dict_out])
P, S, N = [], [], []
for r in products:
    p100 = r['per_100g']
    prim = next(s for s in r['sources'] if s['is_primary'])
    P.append((r['id'], r['name'], r['brand'], r['pack_size'], r['ean'], r['kind'], r['flavour'], json.dumps(r['categories'], ensure_ascii=False), r['ingredients'],
              json.dumps(r['allergens'], ensure_ascii=False) if r['allergens'] else None, r['serving_g'], prim['source'], len(r['sources']), r['status'],
              json.dumps(r['data_quality'], ensure_ascii=False), r['region'], ','.join(r['regions']), 1 if r['norway_relevant'] else 0, 1 if r['discontinued'] else 0,
              json.dumps(r['all_eans']), p100.get('kcal'), p100.get('protein_g'), p100.get('fat_g'), p100.get('sat_fat_g'), p100.get('carbs_g'),
              p100.get('sugars_g'), p100.get('fibre_g'), p100.get('salt_g'), p100.get('kj')))
    for s in r['sources']:
        sp = s['per_100g']
        S.append((r['id'], s['source'], s['source_id'], s['url'], s['fetched_on'], 1 if s['is_primary'] else 0, s['kind'], s['name'], s['brand'],
                  s['region'], 1 if s['norway_relevant'] else 0, 1 if s['page_gone'] else 0, sp.get('kcal'),
                  sp.get('protein_g'), sp.get('fat_g'), sp.get('carbs_g'), json.dumps(sp, ensure_ascii=False), json.dumps(s['flags'], ensure_ascii=False)))
    for code, v in p100.items():
        pv = r['field_provenance']['per_100g'].get(code, prim['source'])
        N.append((r['id'], 'per_100g', code, v, nutr.DICT[code]['unit'], r['per_100g_qualifiers'].get(code), pv.split(' ')[0]))
    for code, v in r['per_serving'].items():
        N.append((r['id'], 'per_serving', code, v, nutr.DICT[code]['unit'], None, r['field_provenance'].get('per_serving')))
    if len(N) > 400000:
        db.executemany('INSERT INTO nutrients VALUES (?,?,?,?,?,?,?)', N)
        N = []
db.executemany('INSERT INTO products VALUES (' + ','.join('?' * 29) + ')', P)
db.executemany('INSERT INTO product_sources VALUES (' + ','.join('?' * 18) + ')', S)
db.executemany('INSERT INTO product_eans VALUES (?,?)', [(r['id'], e) for r in products for e in r['all_eans']])
db.executemany('INSERT INTO nutrients VALUES (?,?,?,?,?,?,?)', N)
db.executescript("""
CREATE INDEX ix_products_ean ON products(ean);
CREATE INDEX ix_products_region ON products(region, norway_relevant);
CREATE INDEX ix_pe_ean ON product_eans(ean);
CREATE INDEX ix_pe_product ON product_eans(product_id);
CREATE INDEX ix_products_brand ON products(brand);
CREATE INDEX ix_products_kind ON products(kind);
CREATE INDEX ix_products_src ON products(primary_source);
CREATE INDEX ix_ps_product ON product_sources(product_id);
CREATE INDEX ix_ps_source ON product_sources(source);
CREATE INDEX ix_nut_product ON nutrients(product_id);
CREATE INDEX ix_nut_code ON nutrients(code, basis, value);
CREATE VIRTUAL TABLE products_fts USING fts5(name, brand, flavour, categories, content='products', content_rowid='rowid', tokenize='unicode61 remove_diacritics 2');
INSERT INTO products_fts(rowid, name, brand, flavour, categories) SELECT rowid, name, brand, flavour, categories FROM products;
INSERT INTO products_fts(products_fts) VALUES('optimize');
""")
db.commit()
db.execute('ANALYZE')
db.commit()
db.close()
print('sqlite written', os.path.getsize(db_path) // 1e6, 'MB', round(time.time() - t0), 's', flush=True)

# ---------------------------------------------------------------- stats
st = {'raw_records_per_source': dict(per_source_raw), 'dropped_non_food_no_nutrition': dropped, 'candidates': len(cands), 'products': len(products), 'merged_duplicates': dup_merged,
      'superseded_folders_skipped': SUPERSEDED_FOLDERS, 'raw_folders_read': sorted(adapters.READ), 'drop_samples': {'%s|%s' % k: v for k, v in adapters.Drops.samples.items()},
      'unmapped_distinct': len(um), 'unmapped_occurrences': sum(UNMAPPED.values()), 'nutrient_codes_defined': len(nutr.DICT), 'nutrient_codes_used': len(used_codes)}
json.dump(st, open(OUT + '/stats.json', 'w'), indent=1)
print(st)
