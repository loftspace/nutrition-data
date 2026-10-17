"""fix-flavours pass (2026-10-16): re-parse existing raw data into ONE record per page (no network requests).

Reads data/raw/{tights,gymgrossisten,bodystore,proteinfabrikken,bulk}, writes data/raw/<source>-v2/products.jsonl
(gymgrossisten-v2 also nutrition_rows.jsonl). Rules (Max, 2026-10-16): one product per page, nutrition from the
default (unflavoured/natural) table else the first table, all flavours assumed to share it
(flag flavour_nutrition_shared_assumed), flavour names in `flavours`, page EAN kept. Implausible vitamin/mineral/unit
values are moved out of the mapped fields into `implausible_values` (+ flag implausible_value). Non-food dropped.
Old folders are never modified.
"""
import json
import os
import re
import sys
import collections

ROOT = 'C:/Users/Admin/Documents/Claude/zz-Misc/macro-library'
RAW = ROOT + '/data/raw/'
LOG = ROOT + '/logs/fix-flavours-v2.log'
sys.path.insert(0, ROOT + '/scrapers')
import tights_parse as P  # noqa: E402
import tights_post as TP  # noqa: E402

DEFAULT_RE = re.compile(r'\b(naturell|natural|natur|uten smak|unflavou?red|plain|neutral|smakl[oø]s|no flavou?r|ikke smaksatt|original)\b', re.I)
FLAV = 'flavour_nutrition_shared_assumed'
IMPL = 'implausible_value'

NONFOOD_RE = re.compile(
    r'\b(shaker|shakers|flaske|bottle|water bottle|sports?[- ]?bra|bralette|bra|tights|leggings|shorts|joggers|hoodie|t-?shirt|t-skjorte|tee|singlet|tank|'
    r'sweater|genser|jakke|jacket|bukse|pants|brief|boxer|sokker|socks|lue|hansker|gloves|belt|belte|straps?|wraps?|sleeves?|knee|backpack|ryggsekk|'
    r'sekk|veske|bag|h[aå]ndkle|towel|hoppetau|resistance bands?|strikk|yoga|massasje|massage|roller|foam|kettlebell|manualer|dumbbell|'
    r'barbell|pad|matte|promixx|selvtest|hurtigtest|tannkrem|deodorant|sjampo|shampo|tandkr[aä]m|tv[aå]l|s[aå]pe|badsalt|krukke|dispensing pump|crew|fleece|pullover|top|topper|crop|jogger|hettegenser)\b', re.I)
HARD_TOPS = {'treningsklær', 'utstyr & tilbehør', 'brands', 'skjønnhet', 'hjem og husholdninger', 'tilbehør & gadgets'}
FOOD_TOPS = {'matvarer', 'treningstilskudd', 'helsekost', 'drikkevarer', 'kosttilskudd', 'helse'}
SUB_NONFOOD_RE = re.compile(r'kl[æa]r|utstyr|yoga|massasje|bevegelig|shakere|flasker|rengj|selvtest|tilbehør|hjem og trening', re.I)

MICRO_RE = re.compile(
    r'vitamin|\bvit\.?\s?[abcdek]\d*\b|folat|folsyre|folic|niacin|biotin|pantoten|riboflavin|tiamin|thiamin|kobalamin|cobalamin|pyridoksin|retinol|tokoferol|karoten|'
    r'kalsium|calcium|kalium|potassium|magnesium|jern|\biron\b|\bsink\b|zinc|fosfor|phosph|\bjod\b|iodine|selen|kobber|copper|mangan|\bkrom\b|chrom|molybd|'
    r'natrium|sodium|klorid|chlorid|fluor', re.I)
UNIT_G = {'g': 1.0, 'gram': 1.0, 'mg': 1e-3, 'ug': 1e-6, 'mcg': 1e-6, '\u00b5g': 1e-6, '\u03bcg': 1e-6, 'kg': 1e3}


def log(m):
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(m + '\n')


def jl(path):
    with open(path, encoding='utf-8') as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def dump(path, recs):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')


def to_g(v, u):
    if v is None or u is None:
        return None
    k = UNIT_G.get(str(u).strip().lower())
    return v * k if k else None


def implausible(label, value, unit, basis):
    """Return reason string or None. basis: 'per100' | 'serving' | other."""
    if value is None:
        return None
    u = (str(unit).strip().lower() if unit else '')
    if u and (re.match(r'^[,\d]', u)):
        return 'unit_misparsed'
    lab = label or ''
    if basis == 'per100':
        if u == 'kcal' and value > 1000:
            return 'energy_over_1000_kcal_per_100g'
        if u == 'kj' and value > 4200:
            return 'energy_over_4200_kj_per_100g'
    g = to_g(value, u)
    if g is None:
        return None
    if basis == 'per100' and g > 100.0001:
        return 'over_100_g_per_100g'
    if MICRO_RE.search(lab) and g > 20:
        return 'vitamin_or_mineral_over_20_g'
    return None


def clean_name_flavour(name, flavours):
    if not name or len(flavours) < 2:
        return name
    for fl in sorted(flavours, key=len, reverse=True):
        f = re.sub(r'\s*-\s*new$', '', fl, flags=re.I).strip()
        if len(f) < 3:
            continue
        m = re.search(r'[\s,\-\u2013:/]*\(?' + re.escape(f) + r'\)?\s*$', name, re.I)
        if m and len(name[:m.start()].strip(' ,-')) >= 4:
            return name[:m.start()].strip(' ,-:')
    return name


def uniq(seq):
    out, seen = [], set()
    for s in seq:
        if not s:
            continue
        s = re.sub(r'\s+', ' ', str(s)).strip()
        k = s.lower()
        if s and k not in seen:
            seen.add(k)
            out.append(s)
    return out


def is_nonfood(name, cats, has_nutrition, has_ingredients):
    """Clothing, gear, beauty, household: only judged when the page has neither nutrition nor ingredients."""
    if has_nutrition or has_ingredients:
        return False
    cats = [c for c in (cats or []) if c]
    if cats and cats[0].strip().lower() in HARD_TOPS:
        return True
    if SUB_NONFOOD_RE.search(' '.join(cats[1:3])):
        return True
    if cats and cats[0].strip().lower() in FOOD_TOPS:
        return False
    return bool(NONFOOD_RE.search(name or ''))


def add_flag(r, f):
    if f not in r['flags']:
        r['flags'].append(f)


def energy_check(r, kcal, kj):
    if kcal and kj and kcal > 0:
        ratio = kj / kcal
        if not 3.8 < ratio < 4.5:
            add_flag(r, 'energy_kj_kcal_inconsistent')


# ----------------------------------------------------------------------------- tights
def tights_title(t):
    h = t.get('header') or []
    s = (h[0] if h else '') or ''
    s = re.sub(r'^\s*(n[\u00e6a]rings\w*|nutrition\w*|innhold\w*)\s*[:\-\u2013]?\s*', '', s, flags=re.I).strip()
    return s or None


def tights_v2():
    out, st = [], collections.Counter()
    for r in jl(RAW + 'tights/products.jsonl'):
        st['in'] += 1
        nut = [t for t in (r.get('nutrition_tables') or []) if t.get('nutritional', True)]
        if is_nonfood(r.get('name'), r.get('categories'), bool(nut), bool(r.get('ingredients'))):
            st['dropped_nonfood'] += 1
            continue
        flags = list(r.get('flags') or [])
        r['flags'] = flags
        variants = [(v.get('labels') or {}) for v in (r.get('variants') or [])]
        vlabels = uniq([x for d in variants for x in d.values()])
        titles = [tights_title(t) for t in nut]
        tl = uniq(titles)
        flavours = uniq(vlabels + tl) if (len(nut) >= 2 or vlabels) else []
        if len(nut) >= 2:
            flavours = [f for f in flavours if not re.match(r'^(per\b|innhold|\d)', f, re.I)]
        prim_i = next((i for i, t in enumerate(nut) if 'per100' in t['col_kinds']), 0) if nut else None
        ci = prim_i
        method = 'single'
        if len(nut) >= 2:
            di = next((i for i, t in enumerate(nut) if DEFAULT_RE.search(' '.join(x or '' for x in (t.get('header') or [])))), None)
            ci = di if di is not None else prim_i
            method = 'default_named' if di is not None else 'first'
        r['name_original'] = r['name']
        r['name'] = clean_name_flavour(r['name'], flavours)
        r['flavours'] = flavours
        r['nutrition_choice'] = {'method': method, 'n_tables': len(nut), 'chosen_index': ci, 'chosen_title': (titles[ci] if nut else None),
                                 'other_table_titles': [t for i, t in enumerate(titles) if i != ci]}
        if len(nut) >= 2 or len(flavours) >= 2:
            add_flag(r, FLAV)
        for f in ('no_per100_column', 'only_prepared_product_values', 'per100g_derived_from_serving_size', 'per_serving_only_no_gram_size',
                  'basis_per100g_taken_from_page_text', 'basis_unverified_per_100g_or_per_serving'):
            if f in flags:
                flags.remove(f)
        for k in ('nutrition_unverified_basis', 'derived_basis', 'nutrition_prepared'):
            r.pop(k, None)
        orig = (r.get('nutrition_per_100g'), r.get('nutrition_per_serving'), r.get('nutrition_per_100g_derived'))
        r.pop('nutrition_by_table', None)
        iv = []
        if nut:
            t = json.loads(json.dumps(nut[ci]))
            for row in t['rows']:
                for kind in list(row['cols'].keys()):
                    if kind not in ('per100', 'serving', 'unknown', 'prepared'):
                        continue
                    basis = 'per100' if kind == 'per100' else 'serving'
                    keep = []
                    for it in row['cols'][kind]:
                        why = implausible(row.get('label'), it.get('value'), it.get('unit'), basis)
                        if why:
                            iv.append({'where': 'table', 'basis': kind, 'label': row.get('label'), 'value': it.get('value'), 'unit': it.get('unit'), 'reason': why})
                        else:
                            keep.append(it)
                    if keep:
                        row['cols'][kind] = keep
                    else:
                        del row['cols'][kind]
            prim = t
            if prim.get('basis_from_page_text'):
                flags.append('basis_per100g_taken_from_page_text')
            if prim.get('basis_unverified'):
                flags.append('basis_unverified_per_100g_or_per_serving')
                r['nutrition_unverified_basis'] = P.flatten(prim, 'unknown') or None
            p100 = P.flatten(prim, 'per100') or None
            psv = P.flatten(prim, 'serving') or None
            r['nutrition_per_100g'], r['nutrition_per_serving'], r['serving'] = p100, psv, prim['serving']
            r['nutrition_per_100g_derived'] = None
            if not p100:
                pp = P.flatten(prim, 'prepared')
                if pp:
                    flags.append('only_prepared_product_values')
                    r['nutrition_prepared'] = pp
                g, basis = TP.unit_weight_g(r['name_original'], prim['serving'], r['weight_kg'])
                if psv and g:
                    r['nutrition_per_100g_derived'] = {k: round(v * 100.0 / g, 4) if isinstance(v, float) and not k.endswith('_lt') else v for k, v in psv.items()}
                    r['derived_basis'] = {'serving_g': g, 'from': basis}
                    flags.append('per100g_derived_from_serving_size')
                elif psv:
                    flags.append('per_serving_only_no_gram_size')
                elif not pp:
                    flags.append('no_per100_column')
            r['nutrition'] = {'per_100g': p100, 'per_serving': psv}
            r['nutrition_tables'] = [t]
            if p100:
                energy_check(r, p100.get('kcal'), p100.get('kj'))
            if ci == prim_i and not iv and len(nut) == 1:
                if (orig[0], orig[1], orig[2]) != (r['nutrition_per_100g'], r['nutrition_per_serving'], r['nutrition_per_100g_derived']):
                    st['recompute_mismatch_single'] += 1
            if iv:
                r['implausible_values'] = iv
                add_flag(r, IMPL)
                st['with_implausible'] += 1
        out.append(r)
        st['out'] += 1
        if FLAV in flags:
            st['flavour_shared_flag'] += 1
        if r.get('ean'):
            st['ean'] += 1
    return out, st


# ----------------------------------------------------------------------------- gymgrossisten
ENERGY_LABEL = re.compile(r'^\s*(energi|energy|kalori)', re.I)


def gym_energy_fix(x):
    """Re-read kJ / kcal from the raw Energi line (thousands separator spaces broke the old parse)."""
    fixed = False
    for ln in x.get('lines') or []:
        if ENERGY_LABEL.match(ln.get('label') or '') and ln.get('raw'):
            raw = re.sub(r'(?<=\d)\s*,\s*(?=\d{3}(?!\d))', '', ln['raw'])
            raw = re.sub(r'(?<=\d)[\s\u00a0]+(?=\d)', '', raw)
            kj = re.search(r'(\d+(?:[.,]\d+)?)\s*kj', raw, re.I)
            kc = re.search(r'(\d+(?:[.,]\d+)?)\s*kcal', raw, re.I)
            m = x.setdefault('macro', {})
            if kj:
                v = float(kj.group(1).replace(',', '.'))
                if ln.get('kj') != v or m.get('kj') != v:
                    fixed = True
                ln['kj'] = v
                m['kj'] = v
            if kc:
                v = float(kc.group(1).replace(',', '.'))
                if ln.get('kcal') != v or m.get('kcal') != v:
                    fixed = True
                ln['kcal'] = v
                m['kcal'] = v
            break
    return fixed


def row_labels(x):
    s = {re.sub(r'[^a-z\u00e6\u00f8\u00e5]', '', (l.get('label') or '').lower()) for l in x.get('lines') or []}
    s |= {k for k in (x.get('macro') or {}) if not k.endswith('_lt')}
    s.discard('')
    return s


def has_energy(x):
    m = x.get('macro') or {}
    return bool(m.get('kcal') or m.get('kj'))


def gym_choose(rs):
    nutr = [x for x in rs if x['section'] == 'tab_nutrition'] or rs
    named = uniq([x['variant'] for x in nutr if x.get('variant')])
    groups = collections.OrderedDict()
    for x in nutr:
        groups.setdefault(x.get('variant'), []).append(x)
    keys = list(groups.keys())
    pick = next((k for k in keys if k and DEFAULT_RE.search(k)), None)
    method = 'default_named' if pick else 'first'
    if pick is None:
        pick = next((k for k in keys if any(x['basis'] == 'per_100' and has_energy(x) for x in groups[k])), None)
    if pick is None and keys:
        pick = next((k for k in keys if any(has_energy(x) for x in groups[k])), keys[0])
    pool = groups.get(pick, [])
    chosen, alt = [], 0
    for x in pool:
        lab = row_labels(x)
        hit = None
        for ci_, c in enumerate(chosen):
            if c['basis'] != x['basis']:
                continue
            lc = row_labels(c)
            if (lab and lc and len(lab & lc) / float(min(len(lab), len(lc))) >= 0.5) or (not lab and not lc):
                hit = ci_
                break
        if hit is None:
            chosen.append(x)
        else:
            alt += 1
            if has_energy(x) and not has_energy(chosen[hit]):
                chosen[hit] = x
    if not alt and len(keys) <= 1:
        method = 'single'
    return chosen, named, pick, method, alt, len(pool)


def gym_v2():
    rows = collections.defaultdict(list)
    for x in jl(RAW + 'gymgrossisten/nutrition_rows.jsonl'):
        rows[x['source_url']].append(x)
    out, outrows, st = [], [], collections.Counter()
    for r in jl(RAW + 'gymgrossisten/products.jsonl'):
        st['in'] += 1
        rs = rows.get(r['source_url'], [])
        if is_nonfood(r.get('name'), r.get('categories'), bool(rs), bool(r.get('ingredients_text'))):
            st['dropped_nonfood'] += 1
            continue
        flags = []
        fl = {'flags': flags}
        chosen, named, pick, method, alt, pool_n = gym_choose(rs) if rs else ([], [], None, 'none', 0, 0)
        chosen = json.loads(json.dumps(chosen))
        iv = []
        for x in chosen:
            if gym_energy_fix(x):
                add_flag(fl, 'gym_energy_reparsed_from_raw')
                st['energy_reparsed_rows'] += 1
            basis = 'per100' if x['basis'] == 'per_100' else 'serving'
            m = x.get('macro') or {}
            for k in list(m.keys()):
                if k.endswith('_lt') or k in ('kcal_from_kj', 'energy_guess', 'energy_unclear'):
                    continue
                unit = 'kcal' if k == 'kcal' else 'kj' if k == 'kj' else 'g'
                why = implausible(k, m[k], unit, basis)
                if why:
                    iv.append({'where': 'macro', 'basis': x['basis'], 'label': k, 'value': m.pop(k), 'unit': unit, 'reason': why})
                    m.pop(k + '_lt', None)
            keep = []
            for ln in x.get('lines') or []:
                if ln.get('value') is not None:
                    why = implausible(ln.get('label'), ln['value'], ln.get('unit'), basis)
                    if why:
                        iv.append({'where': 'line', 'basis': x['basis'], 'label': ln.get('label'), 'raw': ln.get('raw'), 'value': ln['value'], 'unit': ln.get('unit'), 'reason': why})
                        continue
                keep.append(ln)
            x['lines'] = keep
            if x['basis'] == 'per_100':
                energy_check(fl, m.get('kcal'), m.get('kj'))
        fo = uniq([v for vs in (r.get('variant_options') or {}).values() for v in (vs if isinstance(vs, list) else [vs])])
        flavours = uniq(named + fo)
        r['name_original'] = r['name']
        r['name'] = clean_name_flavour(r['name'], flavours)
        r['flavours'] = flavours
        r['nutrition_choice'] = {'method': method, 'n_named_variants': len(named), 'chosen_variant': pick, 'tables_in_pool': pool_n,
                                 'tables_used': len(chosen), 'alternate_tables_ignored': alt}
        if len(flavours) >= 2 or alt > 0 or len(named) >= 2:
            flags.append(FLAV)
        if r.get('is_bundle'):
            flags.append('bundle_or_multipack')
        if not chosen:
            flags.append('no_nutrition_table')
        if iv:
            r['implausible_values'] = iv
            flags.append(IMPL)
            st['with_implausible'] += 1
        r['flags'] = flags
        for k in ('raw_nutrition_html', 'tables', 'tables_raw'):
            r.pop(k, None)
        out.append(r)
        outrows.extend(chosen)
        st['out'] += 1
        if FLAV in flags:
            st['flavour_shared_flag'] += 1
    return out, outrows, st


# ----------------------------------------------------------------------------- bodystore
def bs_suffix(t):
    h = (t.get('header') or [''])[0] or t.get('heading') or ''
    m = re.match(r'^\s*(?:n[\u00e6a]rings\w*|nutrition\w*|innhold\w*)\s*[:\-\u2013]\s*(.+?)\s*$', h, re.I)
    return m.group(1) if m else None


def bs_has_energy(t):
    return any(re.match(r'^\s*(energi|energy|kalori)', (i.get('label') or ''), re.I) for i in t.get('items') or [])


def bs_labels(t):
    return {re.sub(r'[^a-z\u00e6\u00f8\u00e5]', '', (i.get('label') or '').lower()) for i in t.get('items') or []} - {''}


def bodystore_v2():
    out, st = [], collections.Counter()
    for r in jl(RAW + 'bodystore/products.jsonl'):
        st['in'] += 1
        bc = r.get('breadcrumb') or []
        top = bc[0] if bc else None
        nu = r.get('nutrition') or {}
        tables = nu.get('tables') or []
        has_n = bool(r.get('nutrients_flat'))
        if is_nonfood(r.get('name'), bc, has_n, bool(r.get('ingredients'))):
            st['dropped_nonfood'] += 1
            continue
        flags = [r['nutrition_flag']] if r.get('nutrition_flag') else []
        et = [i for i, t in enumerate(tables) if bs_has_energy(t)]
        method = 'single'
        chosen_flav = None
        if len(et) >= 2:
            di = next((i for i in et if DEFAULT_RE.search(' '.join(x or '' for x in (tables[i].get('header') or [])))), None)
            ci = di if di is not None else et[0]
            method = 'default_named' if di is not None else 'first'
            chosen_flav = bs_suffix(tables[ci])
            sel = []
            for i, t in enumerate(tables):
                if i == ci:
                    sel.append(i)
                elif i in et:
                    continue
                else:
                    sf = bs_suffix(t)
                    if sf is None or (chosen_flav and sf.lower() == chosen_flav.lower()):
                        sel.append(i)
        else:
            sel = list(range(len(tables)))
        keep, seen = [], []
        for i in sel:
            lab = bs_labels(tables[i])
            if lab and any(len(lab & s) / float(min(len(lab), len(s))) >= 0.8 for s in seen):
                continue
            seen.append(lab)
            keep.append(i)
        chosen_tables = [json.loads(json.dumps(tables[i])) for i in keep]
        flat = {}
        iv = []
        for t in chosen_tables:
            for it in t.get('items') or []:
                lab = it.get('label')
                for col, v in list((it.get('values') or {}).items()):
                    if col == 'pct_ri':
                        continue
                    basis = 'per100' if col == 'per100' else 'serving'
                    for unit_key, val in (('kcal', v.get('kcal')), ('kj', v.get('kj'))):
                        if val is not None:
                            why = implausible('Energi', val, unit_key, basis)
                            if why:
                                iv.append({'where': 'table', 'basis': col, 'label': lab, 'raw': v.get('raw'), 'value': val, 'unit': unit_key, 'reason': why})
                                v['implausible'] = why
                    if v.get('value') is not None:
                        why = implausible(lab, v['value'], v.get('unit'), basis)
                        if why:
                            iv.append({'where': 'table', 'basis': col, 'label': lab, 'raw': v.get('raw'), 'value': v['value'], 'unit': v.get('unit'), 'reason': why})
                            v['implausible'] = why
        for t in chosen_tables:
            for it in t.get('items') or []:
                lab = it.get('label')
                if lab in flat:
                    continue
                vals = {c: v for c, v in (it.get('values') or {}).items() if not v.get('implausible')}
                if vals:
                    flat[lab] = vals
        suffixes = uniq([bs_suffix(t) for t in tables])
        vv = [v for v in (r.get('variant_values') or []) if isinstance(v, str)]
        flavours = uniq(suffixes + vv)
        r['name_original'] = r['name']
        r['name'] = clean_name_flavour(r['name'], flavours)
        r['flavours'] = flavours
        r['nutrition_choice'] = {'method': method, 'n_tables': len(tables), 'n_energy_tables': len(et), 'tables_used': len(chosen_tables), 'chosen_flavour': chosen_flav}
        if len(et) >= 2 or len(flavours) >= 2:
            flags.append(FLAV)
        p = (flat.get('Energi') or {}).get('per100') or {}
        energy_check({'flags': flags}, p.get('kcal'), p.get('kj'))
        if iv:
            r['implausible_values'] = iv
            flags.append(IMPL)
            st['with_implausible'] += 1
        if chosen_tables:
            r['nutrition'] = {'tables': chosen_tables}
            r['nutrients_flat'] = flat
        r['flags'] = flags
        out.append(r)
        st['out'] += 1
        if FLAV in flags:
            st['flavour_shared_flag'] += 1
        if r.get('ean'):
            st['ean'] += 1
    return out, st


# ----------------------------------------------------------------------------- keyed nutrition (proteinfabrikken, bulk)
def sanitize_keyed(nu, iv, where):
    """Move implausible entries of a keyed nutrition dict (per_100 / per_serving) into iv."""
    if not nu:
        return
    for col, basis in (('per_100', 'per100'), ('per_serving', 'serving')):
        d = nu.get(col)
        if not d:
            continue
        for k in list(d.keys()):
            v = d[k]
            if k.startswith('_'):
                continue
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                unit = 'kj' if k == 'energy_kj' else 'kcal' if k == 'energy_kcal' else None
                why = implausible(k, v, unit, basis)
                if why:
                    iv.append({'where': where, 'basis': col, 'label': k, 'value': v, 'unit': unit, 'reason': why})
                    del d[k]
            elif isinstance(v, dict):
                why = implausible(v.get('label') or k, v.get('value'), v.get('unit'), basis)
                if why:
                    iv.append({'where': where, 'basis': col, 'label': v.get('label') or k, 'raw': v.get('raw'), 'value': v.get('value'), 'unit': v.get('unit'), 'reason': why})
                    del d[k]


COLHEAD_RE = re.compile(r'^\s*(%|per\b|pr\b|pr\.|\d|bar\b|dri|innhold)|dri\b|%|per\s|pr\.\s|\d+\s*(g|ml)\b', re.I)


def pf_v2():
    out, st = [], collections.Counter()
    for r in jl(RAW + 'proteinfabrikken/products.jsonl'):
        st['in'] += 1
        bc = r.get('breadcrumbs') or []
        top = bc[0] if bc else None
        cands = r.get('nutrition_candidates') or []
        nu = r.get('nutrition')
        if not bc and not nu and not cands and not r.get('ean') and not r.get('price_nok'):
            st['dropped_non_product_page'] += 1
            continue
        if is_nonfood(r.get('name'), bc, bool(nu or cands), bool(r.get('ingredients_all_flavours'))):
            st['dropped_nonfood'] += 1
            continue
        flags = [f for f in (r.get('nutrition_flags') or []) if f != 'flavour_table_ambiguous']
        method = 'single' if nu else 'none'
        chosen_label = (nu or {}).get('flavour_label')
        flav = []
        if nu and nu.get('flavour_label'):
            flav.append(nu['flavour_label'])
        if cands:
            flav += [c['label'] for c in cands if c.get('label') and not COLHEAD_RE.search(c['label'])]
            di = next((i for i, c in enumerate(cands) if DEFAULT_RE.search(c.get('label') or '')), None)
            if di is None:
                di = next((i for i, c in enumerate(cands) if c.get('per_100') and (c['per_100'].get('energy_kcal') or c['per_100'].get('energy_kj'))), None)
                method = 'first'
            else:
                method = 'default_named'
            if di is None:
                di = next((i for i, c in enumerate(cands) if c.get('per_100') or c.get('per_serving')), 0)
            nu = json.loads(json.dumps(cands[di]))
            chosen_label = nu.get('label')
            nu['chosen_from_candidates'] = True
            flags.append('nutrition_from_default_candidate' if method == 'default_named' else 'nutrition_from_first_candidate')
            if not (nu.get('per_100') or nu.get('per_serving')):
                nu = None
                method = 'none'
        flavours = uniq(flav)
        r['name_original'] = r['name']
        m_ = re.match(r'^(.*?,\s*\d[\d.,]*\s*(?:kg|g|ml|l|stk|pk)\b[^,]*),\s*([^,]+)$', r['name'], re.I)
        if m_ and r.get('is_variant_group_page'):
            r['name'] = m_.group(1).strip()
            flavours = uniq(flavours + [m_.group(2)])
        r['name'] = clean_name_flavour(r['name'], flavours)
        r['flavours'] = flavours
        r['nutrition_choice'] = {'method': method, 'n_candidates': len(cands), 'chosen_label': chosen_label}
        if r.get('is_variant_group_page') or len(flavours) >= 2 or len(cands) >= 2:
            flags.append(FLAV)
        iv = []
        if nu:
            nu = json.loads(json.dumps(nu))
            sanitize_keyed(nu, iv, 'nutrition')
            p = nu.get('per_100') or {}
            energy_check({'flags': flags}, p.get('energy_kcal'), p.get('energy_kj'))
            r['nutrition'] = nu
        else:
            r['nutrition'] = None
        ets = []
        for et in (r.get('extra_tables') or []):
            et = json.loads(json.dumps(et))
            sanitize_keyed(et, iv, 'extra_table')
            ets.append(et)
        r['extra_tables'] = ets
        r.pop('nutrition_candidates', None)
        if iv:
            r['implausible_values'] = iv
            flags.append(IMPL)
            st['with_implausible'] += 1
        r['nutrition_flags'] = flags
        r['flags'] = flags
        out.append(r)
        st['out'] += 1
        if FLAV in flags:
            st['flavour_shared_flag'] += 1
        if method.startswith(('first', 'default')):
            st['from_candidates'] += 1
        if r['nutrition']:
            st['with_nutrition'] += 1
        if r.get('ean'):
            st['ean'] += 1
    return out, st


def bulk_v2():
    pages, offers = {}, collections.defaultdict(list)
    order = []
    for r in jl(RAW + 'bulk/products.jsonl'):
        if r.get('record_type') == 'page':
            pages[r['source_url']] = r
            order.append(r['source_url'])
        else:
            offers[r.get('page_url') or r['source_url']].append(r)
    out, st = [], collections.Counter()
    for u in order:
        st['in'] += 1
        pg = pages[u]
        os_ = offers.get(u, [])
        nu = pg.get('nutrition') or next((o.get('nutrition') for o in os_ if o.get('nutrition') and (o['nutrition'].get('per_100') or o['nutrition'].get('per_serving'))), None)
        has_n = bool(nu and (nu.get('per_100') or nu.get('per_serving')))
        if is_nonfood(pg.get('name'), [], has_n, bool(pg.get('ingredients'))):
            st['dropped_nonfood'] += 1
            continue
        flags = []
        flavours = uniq(pg.get('flavours') or [])
        default_flav = next((f for f in flavours if DEFAULT_RE.search(f)), None)
        eans = [{'sku': o['sku'], 'ean': o.get('ean'), 'price_eur': o.get('price_eur'), 'availability': o.get('availability'), 'sku_parts': o.get('sku_parts')} for o in os_]
        default_ean = None
        if default_flav:
            code = default_flav[:4].upper()
            default_ean = next((o['ean'] for o in os_ if o.get('ean') and ('-' + code + '-') in o['sku']), None)
        ean = default_ean or next((o['ean'] for o in os_ if o.get('ean')), None)
        iv = []
        nu = json.loads(json.dumps(nu)) if nu else None
        if nu:
            sanitize_keyed(nu, iv, 'nutrition')
            p = nu.get('per_100') or {}
            energy_check({'flags': flags}, p.get('energy_kcal'), p.get('energy_kj'))
        ets = []
        for et in (pg.get('extra_tables') or []):
            et = json.loads(json.dumps(et))
            sanitize_keyed(et, iv, 'extra_table')
            ets.append(et)
        if len(flavours) >= 2:
            flags.append(FLAV)
        if iv:
            flags.append(IMPL)
            st['with_implausible'] += 1
        for o in os_:
            for f in (o.get('nutrition_flags') or []):
                if f != 'nutrition_page_level_not_flavour_verified' and f not in flags:
                    flags.append(f)
        prices = [o['price_eur'] for o in os_ if o.get('price_eur') is not None]
        rec = {'record_type': 'product', 'source': 'bulk', 'source_url': u, 'page_url': u, 'fetched_on': pg.get('fetched_on'), 'sku': pg.get('sku'),
               'name': pg.get('name'), 'brand': pg.get('brand'), 'ean': ean, 'eans': eans, 'flavours': flavours, 'sizes': pg.get('sizes'),
               'price_eur_min': min(prices) if prices else None,
               'ingredients': pg.get('ingredients'), 'allergens': pg.get('allergens'), 'suitable_for': pg.get('suitable_for'), 'usage': pg.get('usage'),
               'nutrition': nu, 'extra_tables': ets, 'nutrition_note': pg.get('nutrition_note'), 'nutrition_flags': flags, 'flags': flags,
               'nutrition_choice': {'method': 'page_level_single_table', 'n_offers': len(os_)}}
        if iv:
            rec['implausible_values'] = iv
        if not has_n:
            flags.append('no_nutrition_table')
        out.append(rec)
        st['out'] += 1
        if FLAV in flags:
            st['flavour_shared_flag'] += 1
        if ean:
            st['ean'] += 1
        st['eans_total'] += len([e for e in eans if e['ean']])
    return out, st


def main():
    os.makedirs(ROOT + '/logs', exist_ok=True)
    log('fix-flavours v2 start (no network requests)')
    res = {}
    o, st = tights_v2()
    dump(RAW + 'tights-v2/products.jsonl', o)
    res['tights'] = st
    o, rows, st = gym_v2()
    dump(RAW + 'gymgrossisten-v2/products.jsonl', o)
    dump(RAW + 'gymgrossisten-v2/nutrition_rows.jsonl', rows)
    res['gymgrossisten'] = st
    o, st = bodystore_v2()
    dump(RAW + 'bodystore-v2/products.jsonl', o)
    res['bodystore'] = st
    o, st = pf_v2()
    dump(RAW + 'proteinfabrikken-v2/products.jsonl', o)
    res['proteinfabrikken'] = st
    o, st = bulk_v2()
    dump(RAW + 'bulk-v2/products.jsonl', o)
    res['bulk'] = st
    for k, v in res.items():
        log(k + ' ' + json.dumps(dict(v)))
        print(k, dict(v))


if __name__ == '__main__':
    main()
