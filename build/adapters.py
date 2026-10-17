"""Source adapters: raw JSONL -> normalised candidate dicts.

A candidate is one source's view of one product (or one flavour of a product):
  source, source_id, url, fetched_on, kind ('product'|'generic'), name, brand, ean(raw), pack_size, categories,
  ingredients, allergens {'contains': [], 'may_contain': []}, flavour, serving_g, serving_text,
  per100: [(label, value, unit, qual, key)], perserv: [...], flags: [...], extra: {}
"""
import collections
import json
import os
import re
import html

RAW = 'C:/Users/Admin/Documents/Claude/zz-Misc/macro-library/data/raw'

TAG = re.compile(r'<[^>]+>')


def clean(s):
    if s is None:
        return None
    if not isinstance(s, str):
        s = str(s)
    s = TAG.sub('', s)
    s = html.unescape(s)
    s = s.replace('\u00a0', ' ').replace('\ufffd', '')
    s = re.sub(r'\s+', ' ', s).strip()
    return s or None


# raw folders actually read in this run (build.py asserts the superseded folders are not among them)
READ = set()
# canonical shop -> raw folder to read; filled by build.py (RAW_FOLDERS config there)
FOLDERS = {}


def folder(name):
    return FOLDERS.get(name, name)


def jl(path):
    READ.add(os.path.basename(os.path.dirname(path.replace(chr(92), '/'))))
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def cand(source, source_id, **kw):
    c = dict(source=source, source_id=str(source_id) if source_id is not None else None, url=None, fetched_on=None, kind='product', name=None,
             brand=None, ean=None, pack_size=None, categories=[], ingredients=None, allergens=None, flavour=None, serving_g=None,
             serving_text=None, per100=[], perserv=[], flags=[], extra={}, region=None, nr=None, gone=False, eans_extra=[], country=None)
    c.update(kw)
    return c


def num(x):
    try:
        if x is None or isinstance(x, bool):
            return None
        return float(x)
    except Exception:
        return None


def serving_grams(text=None, size=None, unit=None):
    if size is not None and unit and str(unit).lower() in ('g', 'ml', 'gram'):
        return num(size)
    if text:
        m = re.search(r'(\d+(?:[.,]\d+)?)\s*(g|ml)\b', str(text).lower())
        if m:
            return float(m.group(1).replace(',', '.'))
    return None


STD_KEYS = {'energy_kj': 'kj', 'energy_kcal': 'kcal', 'fat': 'fat_g', 'saturated_fat': 'sat_fat_g', 'monounsaturated_fat': 'mono_fat_g',
            'polyunsaturated_fat': 'poly_fat_g', 'carbs': 'carbs_g', 'sugars': 'sugars_g', 'polyols': 'polyols_g', 'starch': 'starch_g',
            'fibre': 'fibre_g', 'protein': 'protein_g', 'salt': 'salt_g', 'sodium': 'sodium_mg', 'kcal': 'kcal', 'kj': 'kj'}
STD_UNIT_DEFAULT = {'kcal': 'kcal', 'kj': 'kj', 'sodium_mg': 'g'}


def keyed_entries(d, std=True):
    """{key: number | {value, unit, label, less_than|qualifier}} -> entries."""
    out = []
    if not d:
        return out
    for k, v in d.items():
        if k.startswith('_') or v is None:
            continue
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            if k in ('energy_kj', 'energy_kcal'):
                out.append((k, float(v), 'kj' if k == 'energy_kj' else 'kcal', None, k))
            continue
        if isinstance(v, dict):
            val = num(v.get('value'))
            if val is None:
                continue
            qual = '<' if (v.get('less_than') or v.get('qualifier') == '<' or v.get('lt')) else None
            lab = v.get('label') or k
            out.append((lab.replace('�', '') if isinstance(lab, str) else lab, val, v.get('unit'), qual, k))
    return out


def allergen_dict(contains=None, may=None):
    c = [clean(x).lower() for x in (contains or []) if clean(x)]
    m = [clean(x).lower() for x in (may or []) if clean(x)]
    if not c and not m:
        return None
    return {'contains': c, 'may_contain': m}


# ----------------------------------------------------------------------------
def a_matvaretabellen():
    for r in jl(RAW + '/matvaretabellen/products.jsonl'):
        c = cand('matvaretabellen', r['food_id'], url=r['source_url'], fetched_on=r['fetched_on'], kind='generic', name=clean(r['name']),
                 categories=r.get('food_group_path_nb') or [])
        c['extra'] = {'name_en': r.get('name_en'), 'latin_name': r.get('latin_name'), 'url_en': r.get('source_url_en'), 'edible_part_percent': r.get('edible_part_percent')}
        en = r.get('energy') or {}
        if (en.get('kcal') or {}).get('quantity') is not None:
            c['per100'].append(('Energi', float(en['kcal']['quantity']), 'kcal', None, 'kcal'))
        if (en.get('kj') or {}).get('quantity') is not None:
            c['per100'].append(('Energi', float(en['kj']['quantity']), 'kJ', None, 'kj'))
        for k, v in (r.get('nutrients') or {}).items():
            if v.get('value_per_100g') is None:
                continue
            c['per100'].append((v.get('label_nb') or k, float(v['value_per_100g']), v.get('unit'), None, k))
        yield c


def a_livsmedelsverket():
    for r in jl(RAW + '/livsmedelsverket/products.jsonl'):
        c = cand('livsmedelsverket', r['source_id'], url=r['source_url'], fetched_on=r['fetched_on'], kind='generic', name=clean(r['name']),
                 categories=[x for x in [r.get('project')] if x])
        c['extra'] = {'name_scientific': r.get('name_scientific'), 'food_type': r.get('food_type')}
        for k, v in (r.get('nutrients') or {}).items():
            if v.get('value') is None:
                continue
            c['per100'].append((v.get('label') or k, float(v['value']), v.get('unit'), None, k))
        yield c


def a_frida():
    for r in jl(RAW + '/frida-dk/products.jsonl'):
        c = cand('frida-dk', r['source_id'], url=r['source_url'], fetched_on=r['fetched_on'], kind='generic', name=clean(r['name_en'] or r['name']),
                 categories=[x for x in [r.get('food_group')] if x])
        c['extra'] = {'name_da': r.get('name'), 'name_scientific': r.get('name_scientific'), 'food_group_da': r.get('food_group_da')}
        for k, v in (r.get('nutrients') or {}).items():
            if v.get('value') is None:
                continue
            c['per100'].append((v.get('label') or k, float(v['value']), v.get('unit'), None, k))
        yield c


def a_usda():
    for ds in ('foundation', 'sr_legacy', 'branded_filtered'):
        for r in jl(RAW + '/usda-fdc/%s.jsonl' % ds):
            branded = ds == 'branded_filtered'
            c = cand('usda-fdc', '%s:%s' % (ds, r['source_id']), url=r['source_url'], fetched_on=r['fetched_on'], kind='product' if branded else 'generic',
                     name=clean(r['name']), brand=clean(r.get('brand') or r.get('brand_owner')), ean=r.get('ean'), pack_size=clean(r.get('pack_size')),
                     categories=[x for x in [r.get('category')] if x], ingredients=clean(r.get('ingredients')))
            c['extra'] = {'dataset': ds, 'market_country': r.get('market_country'), 'household_serving': r.get('household_serving'), 'brand_owner': r.get('brand_owner')}
            if branded:
                c['serving_g'] = serving_grams(None, r.get('serving_size'), r.get('serving_unit'))
                c['serving_text'] = r.get('household_serving')
                c['flags'].append('us_market_product')
            for k, v in (r.get('nutrients') or {}).items():
                if v.get('value') is None:
                    continue
                c['per100'].append((v.get('label') or k, float(v['value']), v.get('unit'), None, k))
            yield c




def a_kassalapp():
    for r in jl(RAW + '/kassalapp/products.jsonl'):
        al = None
        if r.get('allergens'):
            al = allergen_dict([a['name'] for a in r['allergens'] if a.get('code') == 'JA'], [a['name'] for a in r['allergens'] if a.get('code') == 'KAN'])
        ps = None
        if r.get('weight'):
            ps = '%s %s' % (r['weight'], r.get('weight_unit') or '')
        c = cand('kassalapp', r['product_id'], url=r['source_url'], fetched_on=r['fetched_on'], name=clean(r['name']), brand=clean(r.get('brand')),
                 ean=r.get('ean'), pack_size=clean(ps), categories=r.get('category') or [], ingredients=clean(r.get('ingredients')), allergens=al)
        c['extra'] = {'vendor': r.get('vendor'), 'stores': r.get('stores'), 'labels': [l.get('name') for l in (r.get('labels') or [])]}
        for v in ((r.get('nutrition') or {}).get('raw') or []):
            if v.get('amount') is None:
                continue
            c['per100'].append((v['name'], float(v['amount']), v.get('unit'), None, None))
        yield c


NG_NONFOOD = {'Personlige artikler', 'Personlige Artikler', 'Hus & hjem', 'Hus og hjem', 'Hus/Hjem Artikler', 'Dyr', 'Apotekvarer', 'Blomster og planter', 'Hygiene og helse', 'Kioskvarer'}


def a_ng():
    drop = 0
    for r in jl(RAW + '/norgesgruppen/products.jsonl'):
        nu = r.get('nutrition')
        if not nu and r.get('category') in NG_NONFOOD:
            drop += 1
            continue
        al = allergen_dict(r.get('allergens'))
        c = cand('norgesgruppen', r['ean'], url=r['source_url'], fetched_on=r['fetched_on'], name=clean(r['name']), brand=clean(r.get('brand')), ean=r['ean'],
                 pack_size=clean(r.get('pack_size')), categories=[x for x in [r.get('category')] if x], ingredients=clean(r.get('ingredients')), allergens=al)
        c['extra'] = {'chains': r.get('chains'), 'subtitle': r.get('subtitle'), 'vendor': r.get('vendor'), 'country_of_origin': r.get('country_of_origin'),
                      'organic': r.get('organic'), 'urls': r.get('source_urls')}
        if r.get('nutrition_flag'):
            c['flags'].append('no_nutrition_data')
        for k, v in (nu or {}).items():
            if v.get('amount') is None:
                continue
            c['per100'].append((v.get('label') or k, float(v['amount']), v.get('unit'), None, None))
        yield c
    a_ng.dropped = drop




# ============================================================================
# 2026-10-16 second pass: v2 folders, discontinued, Nordic and UK/US/EU sources.
# ============================================================================

# ------------------------------------------------------------ source meta
# (region, norway_relevant). region: NO SE DK UK US EU other.
# norway_relevant: a Norwegian source, or a Nordic / EU / UK online shop Max can buy from.
# False: USDA branded, Frida, Livsmedelsverket (tables only) and US brand sites (no Norwegian shop behind them).
_NO = ('NO', True)
_SE = ('SE', True)
_DK = ('DK', True)
SOURCE_META = {}
for _s in ['matvaretabellen', 'openfoodfacts', 'kassalapp', 'norgesgruppen', 'tights', 'tights-discontinued', 'gymgrossisten', 'gymgrossisten-discontinued',
           'bodystore', 'bodystore-discontinued', 'proteinfabrikken', 'proteinfabrikken-discontinued', 'myprotein', 'myprotein-discontinued',
           'apex-no', 'bodylab-no', 'coore-no', 'diggbox-no', 'helsekost-no', 'kost1-no', 'life-no', 'life-no-discontinued', 'nordicpower-no',
           'sportylab-no', 'barebells-no', 'proteincompany-no',
           'gilde', 'prior', 'q-meieriene', 'fjordland', 'tine', 'grandiosa', 'nidar', 'saetre', 'toro', 'firstprice', 'eldorado', 'mills', 'ringnes',
           'synnove', 'kavli', 'hennig-olsen']:
    SOURCE_META[_s] = _NO
for _s in ['gymgrossisten-se', 'bodystore-se', 'tillskottsbolaget', 'bodylab-se', 'proteinbolaget', 'goldenathlete', 'mmsports', 'sportkost', 'bodypower',
           'tyngre', 'life-se', 'halsokostbolaget', 'halsafitnessbutiken', 'barebells', 'nocco', 'starnutrition-se', 'kungmarkatta', 'ica-se']:
    SOURCE_META[_s] = _SE
for _s in ['bodylab-dk', 'bodystore-dk', 'matas-dk', 'helsam-dk', 'nutramino-dk']:
    SOURCE_META[_s] = _DK
SOURCE_META.update({
    'bulk': ('EU', True), 'bulk-discontinued': ('EU', True),
    'myprotein-uk': ('UK', True), 'grenade': ('UK', True), 'applied-nutrition': ('UK', True), 'reflex': ('UK', True),
    'fulfil': ('EU', True), 'esn': ('EU', True), 'weider': ('EU', True), 'scitec': ('EU', True), 'optimum-nutrition': ('EU', True),
    'quest': ('US', False), 'cellucor': ('US', False), 'muscletech': ('US', False), 'ghost': ('US', False), 'transparent-labs': ('US', False),
    'gorilla-mind': ('US', False), 'legion': ('US', False), 'bodybuilding': ('US', False), 'dymatize': ('US', False), 'usda-fdc': ('US', False),
    'livsmedelsverket': ('SE', False), 'frida-dk': ('DK', False),
    'openfoodfacts-nordic-global': (None, None),   # decided per record from countries_tags
})
COUNTRY_REGION = {'NO': 'NO', 'SE': 'SE', 'DK': 'DK', 'GB': 'UK', 'UK': 'UK', 'US': 'US', 'IE': 'EU', 'DE': 'EU', 'HU': 'EU', 'FR': 'EU', 'NL': 'EU', 'EU': 'EU'}
OFF_EU = {'france', 'germany', 'netherlands', 'belgium', 'spain', 'italy', 'austria', 'poland', 'ireland', 'portugal', 'finland', 'czech-republic', 'hungary', 'greece',
          'romania', 'slovakia', 'slovenia', 'croatia', 'bulgaria', 'lithuania', 'latvia', 'estonia', 'luxembourg', 'malta', 'cyprus'}
OFF_NORDIC = {'norway', 'sweden', 'denmark', 'finland', 'iceland'}


def finalize(c):
    """Fill region and norway_relevant from the source table unless the adapter set them."""
    reg, nr = SOURCE_META.get(c['source'], (None, None))
    if c.get('region') is None:
        c['region'] = reg or COUNTRY_REGION.get((c.get('country') or '').upper(), 'other')
    if c.get('nr') is None:
        c['nr'] = bool(nr)
    return c


# -------------------------------------------------------------- non-food
NONFOOD_RE = re.compile(
    r"\b(shaker\w*|drikkeflaske\w*|water\s*bottle\w*|vannflaske\w*|vattenflaska\w*|t-?skjorte\w*|t-?shirt\w*|hoodie\w*|genser\w*|bukse\w*|byxor|shorts|leggings?|sport-?bh|t-?back|tank\s*top|singlet|sweatshirt|joggers?|sweatpants|beanie|stringer|pants|"
    r"luer|hansker?|handskar|gloves?|belte\w*|b[äa]lte\w*|lifting\w*|ryggsekk\w*|ryggs[äa]ck\w*|treningsbag\w*|gymbag\w*|sportsbag\w*|h[åa]ndkle\w*|handduk\w*|towel\w*|"
    r"yogamatte\w*|treningsmatte\w*|hantel\w*|dumbbell\w*|kettlebell\w*|motstandsb[åa]nd|sokker?|strumpor|socks?|jakke\w*|jacket\w*|treningst[øo]y|tr[äa]ningskl[äa]der|"
    r"sjampo|shampoo|schampo|balsam|dusjs[åa]pe|s[åa]pe|sæbe|tv[åa]l|deodorant|tannkrem|tandkr[äa]m|tandpasta|tannb[øo]rste|ansiktskrem|dagkrem|nattkrem|kroppskrem|hudkrem|lotion|"
    r"parfyme|parfym|maskara|neglelakk|vaskemiddel|tv[äa]ttmedel|toalettpapir|bleier?|bl[öo]jor|bleer|oppvask\w*|kattemat|hundemat|dyremat|hundefoder|kattemad|hundmat|kattmat|"
    r"batteri\w*|batterier|lyspære|kosmetikk|kosmetik|sminke\w*|h[åa]rfarge|barberh[øo]vel|rakhyvel|gaveeske|gavekort|presentkort)\b", re.I)
# first three category levels; substring match on the lower-cased level
NONFOOD_CAT_PARTS = ['klær', 'kläder', 'kleding', 'utrustning', 'utstyr', 'udstyr', 'redskap', 'treningsutstyr', 'yoga', 'massage', 'vikter', 'skönhet', 'skjønnhet', 'kroppsvård', 'kroppspleie',
                     'ansiktsvård', 'hårvård', 'hudvård', 'hudpleje', 'makeup', 'hjem og husholdning', 'hem och', 'personlige', 'hus & hjem', 'hus og hjem', 'apotekvarer',
                     'blomster', 'kioskvarer', 'träningskläder', 'treningsklær', 'træningstøj']
NONFOOD_CAT_EXACT = {'dyr', 'tilbehør', 'tillbehör', 'hygiene og helse'}


def is_nonfood(name, cats):
    if NONFOOD_RE.search(name or ''):
        return True
    for x in (cats or [])[:3]:
        if not isinstance(x, str):
            continue
        t = x.strip().lower()
        if t in NONFOOD_CAT_EXACT or any(p in t for p in NONFOOD_CAT_PARTS):
            return True
    return False


# ------------------------------------------------------------- helpers
JUNK_ING = re.compile(r'(Gratis frakt|Org\.? ?nr|Bestill før|nyhetsbrev|Fri frakt|Fri fragt|Gratis frakt|Cookies|personvern)', re.I)


def _first(r, *keys):
    for k in keys:
        v = r.get(k)
        if v not in (None, '', [], {}):
            return v
    return None


def _cats(r):
    for k in ('breadcrumbs', 'breadcrumb', 'categories', 'category_path'):
        v = r.get(k)
        if isinstance(v, list) and v:
            out = [x for x in v if isinstance(x, str) and x.strip().lower() not in ('home', 'hjem', 'forside', 'start')]
            nm = (r.get('name') or '').strip().lower()
            if out and out[-1].strip().lower() == nm:
                out = out[:-1]
            return out
        if isinstance(v, str) and v:
            return [x.strip() for x in re.split(r'\s*[>/|#;]\s*', v) if x.strip()]
    v = r.get('category')
    return [v] if isinstance(v, str) and v else []


def _allergens(r):
    a = r.get('allergens')
    if isinstance(a, list):
        return allergen_dict(a)
    if isinstance(a, dict):
        return allergen_dict(a.get('contains'), a.get('may_contain'))
    t = clean(a) if isinstance(a, str) else clean(_first(r, 'allergens_text', 'allergen_text'))
    if t:
        return {'contains': [], 'may_contain': [], 'text': t}
    return None


def strip_flavour(name, flavour):
    name = clean(name)
    fl = clean(flavour)
    if not name or not fl:
        return name
    n2 = re.sub(r'[\s\-–:,|/]+' + re.escape(fl) + r'\s*$', '', name, flags=re.I)
    return n2 if n2 and n2 != name else name


def page_key(r):
    return re.sub(r'[?#].*$', '', r.get('page_url') or r.get('source_url') or '')


def derive_per100(perserv, serving_g):
    """Scale per-serving entries to per 100 g (only called for products with energy and a gram/ml serving)."""
    out = []
    for (lab, val, unit, qual, key) in perserv:
        if str(unit or '').strip().startswith('%') or val is None:
            continue
        out.append((lab, val * 100.0 / serving_g, unit, qual, key))
    return out


def _has_energy(entries):
    for (lab, val, unit, qual, key) in entries:
        if key in ('energy_kcal', 'energy_kj', 'kcal', 'kj') or str(unit or '').lower() in ('kcal', 'kj'):
            return True
        if re.match(r'^(energi|energy|energie)\b', str(lab or ''), re.I):
            return True
    return False


class Drops:
    """Counts records not turned into candidates, by source and reason (reported in stats.json / COVERAGE.md)."""
    counts = collections.Counter()
    samples = collections.defaultdict(list)

    @classmethod
    def add(cls, source, reason, name=None, url=None):
        cls.counts[(source, reason)] += 1
        if len(cls.samples[(source, reason)]) < 5:
            cls.samples[(source, reason)].append([name, url])


# ------------------------------------------------- generic keyed (nutrition.per_100) shops
def a_pages(fkey, source=None, merge_extra=False, one_per_record=False):
    """Records with nutrition = {per_100: {...}, per_serving: {...}} (nogen / bulk / Swedish / UK-US brand shape).
    Variant / offer / page records of one page are collapsed to ONE product per page (flavours share nutrition, as decided);
    every EAN of the page's variants is kept in eans_extra so the product answers to all of them."""
    fold = folder(fkey)
    source = source or fkey
    path = RAW + '/%s/products.jsonl' % fold
    if not os.path.exists(path):
        return
    groups = collections.OrderedDict()
    for i, r in enumerate(jl(path)):
        if r.get('record_type') in ('variant', 'page', 'offer') and not one_per_record:
            k = ('g', page_key(r))
        else:
            k = ('s', i)
        groups.setdefault(k, []).append(r)
    for k, grp in groups.items():
        c = _page_cand(grp, source, merge_extra)
        if c is not None:
            yield c


def _nu_has(r, which):
    nu = r.get('nutrition')
    return bool(isinstance(nu, dict) and nu.get(which))


def _page_cand(grp, source, merge_extra):
    pages = [r for r in grp if r.get('record_type') == 'page']
    vars_ = [r for r in grp if r.get('record_type') != 'page']
    ordered = pages + vars_
    rep = next((r for r in ordered if _nu_has(r, 'per_100')), None) or next((r for r in ordered if _nu_has(r, 'per_100') or _nu_has(r, 'per_serving')), None) or ordered[0]
    base = pages[0] if pages else rep
    name = clean(base.get('name')) if pages else (clean(rep.get('product_name')) or (strip_flavour(rep.get('name'), rep.get('flavour')) if rep.get('record_type') in ('variant', 'offer') else clean(rep.get('name'))))
    if not name:
        Drops.add(source, 'no_name')
        return None
    flavours = []
    for r in ordered:
        for f in ([r.get('flavour')] + list(r.get('flavours') or []) + list(r.get('flavours_listed') or [])):
            f = clean(f) if f else None
            if f and f not in flavours:
                flavours.append(f)
    raw_eans = []

    def addean(e):
        if e not in (None, ''):
            s = str(e)
            if s not in raw_eans:
                raw_eans.append(s)
    addean(rep.get('ean'))
    for r in ordered:
        addean(r.get('ean'))
        addean(r.get('page_gtin'))
        for e in (r.get('eans') or []):
            addean(e.get('ean') if isinstance(e, dict) else e)
    nu = rep.get('nutrition') if isinstance(rep.get('nutrition'), dict) else {}
    per100 = keyed_entries(nu.get('per_100'))
    perserv = keyed_entries(nu.get('per_serving'))
    if merge_extra:
        for et in (base.get('extra_tables') or rep.get('extra_tables') or []):
            if isinstance(et, dict):
                per100 += keyed_entries(et.get('per_100'))
                perserv += keyed_entries(et.get('per_serving'))
    ss = nu.get('serving_size') if isinstance(nu.get('serving_size'), dict) else {}
    serving_g = serving_grams(nu.get('serving_label'), ss.get('value'), ss.get('unit'))
    cats = _cats(base) or _cats(rep)
    flags = []
    for src_ in (rep, base):
        for fl in list(src_.get('nutrition_flags') or []) + list(src_.get('flags') or []) + list((nu.get('flags') or []) if src_ is rep else []):
            if isinstance(fl, str) and fl not in flags:
                flags.append(fl)
        if src_.get('nutrition_flag') and src_['nutrition_flag'] not in flags:
            flags.append(src_['nutrition_flag'])
    if len(flavours) >= 2 and 'flavour_nutrition_shared_assumed' not in flags:
        flags.append('flavour_nutrition_shared_assumed')
    if not per100 and nu.get('per_100_prepared'):
        flags.append('per100_prepared_state_only_not_mapped')
    if not per100 and perserv and serving_g and serving_g >= 5 and _has_energy(perserv):
        per100 = derive_per100(perserv, serving_g)
        flags.append('per100_derived_from_serving')
    if not per100 and not perserv and is_nonfood(name, cats):
        Drops.add(source, 'nonfood_no_nutrition', name, base.get('source_url'))
        return None
    ing = clean(_first(rep, 'ingredients', 'ingredients_text', 'ingredients_all_flavours') or _first(base, 'ingredients', 'ingredients_text', 'ingredients_all_flavours'))
    if rep.get('ingredients_by_flavour') and rep.get('flavour'):
        ing = clean(rep['ingredients_by_flavour'].get(rep['flavour'])) or ing
    if ing:
        ing = re.sub(r'^Ingredients\s+', '', ing)
        if len(ing) > 6000 or JUNK_ING.search(ing):
            flags.append('ingredients_text_discarded_not_an_ingredient_list')
            ing = None
    gone = base.get('page_status') == 'gone' or base.get('discontinued') is True
    pack = _first(base, 'pack_size_text', 'pack_size_raw') or _first(rep, 'pack_size_text', 'pack_size_raw')
    if not pack:
        pk = base.get('pack') if isinstance(base.get('pack'), dict) else rep.get('pack') if isinstance(rep.get('pack'), dict) else None
        pack = (pk or {}).get('size_text')
    prices = {k: base.get(k) if base.get(k) is not None else rep.get(k) for k in ('price_nok', 'price_sek', 'price_eur', 'price_eur_min', 'price_dkk', 'price', 'currency')}
    prices = {k: v for k, v in prices.items() if v is not None}
    c = cand(source, page_key(base) if base.get('record_type') else (base.get('source_url') or base.get('sku')), url=rep.get('source_url') or base.get('source_url'),
             fetched_on=rep.get('fetched_on'), name=name, brand=clean(_first(base, 'brand', 'brand_site') or _first(rep, 'brand', 'brand_site')),
             ean=raw_eans[0] if raw_eans else None, eans_extra=raw_eans[1:], pack_size=clean(pack), categories=cats, ingredients=ing, allergens=_allergens(base) or _allergens(rep),
             flavour=flavours[0] if len(flavours) == 1 else None, serving_g=serving_g, serving_text=nu.get('serving_label'), per100=per100, perserv=perserv,
             flags=flags, gone=gone, country=base.get('country') or rep.get('country'))
    c['extra'] = {'sku': _first(base, 'sku') or rep.get('sku'), 'flavours': flavours[:40] or None, 'sizes': base.get('sizes') or None, 'prices': prices or None,
                  'n_variant_records': len(vars_) if vars_ else None, 'page_status': base.get('page_status'), 'archive_timestamp': base.get('archive_timestamp'),
                  'redirect_to': base.get('redirect_to'), 'country_label_used': base.get('country_label_used')}
    c['extra'] = {k: v for k, v in c['extra'].items() if v is not None}
    return c


# ----------------------------------------------------------- proteinfabrikken (keyed, with category drop + extras)
def a_proteinfabrikken(fkey='proteinfabrikken', source='proteinfabrikken'):
    # same keyed shape as the generic adapter; extra_tables hold vitamins etc., so they are merged
    yield from a_pages(fkey, source, merge_extra=True, one_per_record=True)


# ------------------------------------------------------------------------ tights
def a_tights(fkey='tights', source='tights'):
    """tights-v2 holds one nutrition table per page; tights-discontinued may hold several (first per-100 table is used)."""
    path = RAW + '/%s/products.jsonl' % folder(fkey)
    if not os.path.exists(path):
        return
    for r in jl(path):
        name = clean(r.get('name'))
        if not name:
            Drops.add(source, 'no_name')
            continue
        al = {'contains': [], 'may_contain': [], 'text': clean(r['allergens'])} if r.get('allergens') else None
        gone = r.get('page_status') == 'gone' or r.get('discontinued') is True
        c = cand(source, r.get('source_id') or r['source_url'], url=r['source_url'], fetched_on=r['fetched_on'], name=name, brand=clean(r.get('brand')), ean=r.get('ean'),
                 categories=r.get('categories') or [], ingredients=clean(r.get('ingredients')), allergens=al, gone=gone)
        c['extra'] = {'sku': r.get('sku'), 'weight_kg': r.get('weight_kg'), 'flavours': (r.get('flavours') or None), 'page_status': r.get('page_status'),
                      'archive_timestamp': r.get('archive_timestamp'), 'redirect_to': r.get('redirect_to')}
        c['extra'] = {k: v for k, v in c['extra'].items() if v is not None}
        c['flags'] = list(r.get('flags') or [])
        sv = r.get('serving')
        if sv:
            c['serving_g'] = serving_grams(sv.get('label'), sv.get('size'), sv.get('unit'))
            c['serving_text'] = sv.get('label')
        tables = [t for t in (r.get('nutrition_tables') or []) if t.get('nutritional', True)]
        t = next((x for x in tables if 'per100' in (x.get('col_kinds') or [])), tables[0] if tables else None)
        if len(tables) > 1:
            c['flags'].append('multiple_tables_first_per100_used')
        if t:
            for row in t.get('rows') or []:
                for kind, items in (row.get('cols') or {}).items():
                    for it in items:
                        if it.get('value') is None:
                            continue
                        ent = (row.get('label'), float(it['value']), it.get('unit'), '<' if it.get('lt') else None, row.get('key'))
                        if kind == 'per100':
                            c['per100'].append(ent)
                        elif kind == 'serving':
                            c['perserv'].append(ent)
        if not c['per100'] and r.get('nutrition_per_100g_derived'):
            c['flags'].append('per100_derived_from_serving')
            for k, v in r['nutrition_per_100g_derived'].items():
                if k in STD_KEYS and num(v) is not None:
                    c['per100'].append((k, float(v), 'kcal' if k == 'kcal' else 'kj' if k == 'kj' else 'g', None, k))
        if not c['per100'] and not c['perserv'] and r.get('nutrition_per_serving'):
            for k, v in r['nutrition_per_serving'].items():
                if k in STD_KEYS and num(v) is not None and not k.endswith('_lt'):
                    c['perserv'].append((k, float(v), 'kcal' if k == 'kcal' else 'kj' if k == 'kj' else 'g', None, k))
        if not c['per100'] and not c['perserv'] and is_nonfood(name, c['categories']):
            Drops.add(source, 'nonfood_no_nutrition', name, r['source_url'])
            continue
        yield c


# -------------------------------------------------------------------- gymgrossisten family
_RAW_VAL = re.compile(r'^\s*([<>~]?)\s*(\d{1,3}(?:[  ]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)\s*([a-zA-Zµμ%]+)')


def _parse_raw(raw):
    m = _RAW_VAL.match(raw or '')
    if not m:
        return None, None
    try:
        return float(m.group(2).replace(' ', '').replace(' ', '').replace(',', '.')), m.group(3)
    except ValueError:
        return None, None


def energy_from_raw(raw):
    s = (raw or '').replace(' ', ' ')
    kj = kcal = None
    m = re.search(r'(\d{1,3}(?: \d{3})+|\d+)\s*kj\b', s, re.I)
    if m:
        kj = float(m.group(1).replace(' ', ''))
    m = re.search(r'(\d+(?:[.,]\d+)?)\s*kcal\b', s, re.I)
    if m:
        kcal = float(m.group(1).replace(',', '.'))
    return kj, kcal


def _ok_energy(kj, kcal):
    """True when kJ and kcal agree (kJ = 4.184 kcal within 12 %), or one is missing."""
    if kj is None or kcal is None:
        return True
    if kcal < 5:
        return True
    return 0.88 <= kj / (kcal * 4.184) <= 1.12


STD_GYM = {'fat_g': 'fat', 'saturated_fat_g': 'saturated_fat', 'carbs_g': 'carbs', 'sugars_g': 'sugars', 'fibre_g': 'fibre', 'protein_g': 'protein', 'salt_g': 'salt',
           'polyols_g': 'polyols', 'kcal': 'kcal', 'kj': 'kj'}


def _gym_table_entries(tables, basis):
    """Fallback for pages with `tables` but no nutrition_rows: first table of the basis, first column (flavours share nutrition)."""
    for t in tables or []:
        if t.get('basis') != basis:
            continue
        cols = t.get('columns') or []
        if not cols:
            continue
        out = []
        flags = []
        for n in cols[0].get('nutrients') or []:
            if n.get('kcal') is not None or n.get('kj') is not None or re.match(r'^energi', str(n.get('label') or ''), re.I) and n.get('raw'):
                kj, kcal = energy_from_raw(n.get('raw'))
                if kcal is None:
                    kcal = n.get('kcal')
                if kj is None:
                    kj = n.get('kj')
                if not _ok_energy(kj, kcal):
                    kj = None
                    flags.append('gym_kj_dropped_inconsistent')
                if kcal is not None:
                    out.append(('Energi', float(kcal), 'kcal', None, 'kcal'))
                if kj is not None:
                    out.append(('Energi', float(kj), 'kJ', None, 'kj'))
            elif n.get('value') is not None:
                val, unit = n['value'], n.get('unit')
                if unit is None:
                    v2, u2 = _parse_raw(n.get('raw'))
                    if v2 is not None:
                        val, unit = v2, u2
                out.append((n['label'], float(val), unit, None, None))
        return out, t, flags, len(cols)
    return [], None, [], 0


def a_gym(fkey='gymgrossisten', source='gymgrossisten'):
    """gymgrossisten-v2 / -se: nutrition_rows.jsonl (keyed by source_url, first variant only); -discontinued / bodystore-dk: `tables` fallback."""
    d = RAW + '/%s' % folder(fkey)
    rows = {}
    rp = d + '/nutrition_rows.jsonl'
    if os.path.exists(rp):
        for r in jl(rp):
            rows.setdefault(r.get('source_url') or r.get('sku'), []).append(r)
    for r in jl(d + '/products.jsonl'):
        name = clean(r.get('name'))
        if not name:
            Drops.add(source, 'no_name')
            continue
        rs = rows.get(r['source_url'], [])
        variants = []
        for x in rs:
            if x.get('variant') not in variants:
                variants.append(x.get('variant'))
        grp = [x for x in rs if x.get('variant') == variants[0]] if variants else []
        gone = r.get('page_status') == 'gone' or r.get('discontinued') is True
        price = r.get('price_nok') if r.get('price_nok') is not None else r.get('price_sek') if r.get('price_sek') is not None else r.get('price')
        c = cand(source, r['source_url'], url=r['source_url'], fetched_on=r['fetched_on'], name=name, brand=clean(r.get('brand')), pack_size=clean(r.get('pack_size_text')),
                 ean=r.get('ean'), categories=r.get('categories') or [], ingredients=clean(r.get('ingredients_text')), gone=gone, country=r.get('country'))
        c['extra'] = {'sku': r.get('sku'), 'is_bundle': r.get('is_bundle'), 'flavours': r.get('flavours') or None, 'price': price, 'currency': r.get('currency'),
                      'page_status': r.get('page_status'), 'archive_timestamp': r.get('archive_timestamp'), 'redirect_to': r.get('redirect_to')}
        c['extra'] = {k: v for k, v in c['extra'].items() if v is not None}
        c['flags'] = list(r.get('flags') or [])
        if r.get('nutrition_flag') and r['nutrition_flag'] not in c['flags']:
            c['flags'].append(r['nutrition_flag'])
        if r.get('flavour_nutrition_shared_assumed') and 'flavour_nutrition_shared_assumed' not in c['flags']:
            c['flags'].append('flavour_nutrition_shared_assumed')
        if len([v for v in variants if v]) >= 2 and 'flavour_nutrition_shared_assumed' not in c['flags']:
            c['flags'].append('flavour_nutrition_shared_assumed')
        if r.get('is_bundle'):
            c['flags'].append('bundle_or_multipack')
        if grp:
            for x in grp:
                macro = x.get('macro') or {}
                tgt = c['per100'] if x['basis'] == 'per_100' else c['perserv'] if x['basis'] == 'per_serving' else None
                if tgt is None:
                    continue
                if x['basis'] == 'per_serving' and not c['serving_g']:
                    ba = x.get('basis_amount') or {}
                    c['serving_g'] = serving_grams(None, ba.get('value'), ba.get('unit'))
                    if ba.get('value'):
                        c['serving_text'] = '%s %s' % (ba.get('value'), ba.get('unit'))
                mk, mc = num(macro.get('kj')), num(macro.get('kcal'))
                drop_kj = not _ok_energy(mk, mc)
                if drop_kj:
                    c['flags'].append('gym_kj_dropped_inconsistent')
                for k, val in macro.items():
                    if k.endswith('_lt') or k in ('kcal_from_kj', 'energy_guess', 'energy_unclear') or num(val) is None:
                        continue
                    if k == 'kj' and drop_kj:
                        continue
                    qual = '<' if macro.get(k + '_lt') else None
                    unit = 'kcal' if k == 'kcal' else 'kj' if k == 'kj' else 'g'
                    tgt.append((k, float(val), unit, qual, STD_GYM.get(k)))
                for k in ('kcal_from_kj', 'energy_guess', 'energy_unclear'):
                    if macro.get(k):
                        c['flags'].append('gym_' + k)
                for ln in x.get('lines') or []:
                    if ln.get('value') is None:
                        continue
                    val, unit = ln['value'], ln.get('unit')
                    if unit is None:
                        v2, u2 = _parse_raw(ln.get('raw'))
                        if v2 is not None:
                            val, unit = v2, u2
                    tgt.append((ln['label'], float(val), unit, None, None))
        elif r.get('tables'):
            e100, t100, f1, ncols = _gym_table_entries(r['tables'], 'per_100')
            esrv, tsrv, f2, ncols2 = _gym_table_entries(r['tables'], 'per_serving')
            c['per100'], c['perserv'] = e100, esrv
            c['flags'] += f1 + f2
            if max(ncols, ncols2) >= 2 and 'flavour_nutrition_shared_assumed' not in c['flags']:
                c['flags'].append('flavour_nutrition_shared_assumed')
            if tsrv and tsrv.get('basis_amount'):
                ba = tsrv['basis_amount']
                c['serving_g'] = serving_grams(None, ba.get('value'), ba.get('unit'))
        else:
            c['flags'].append('no_nutrition_table')
        if not c['per100'] and not c['perserv'] and is_nonfood(name, c['categories']):
            Drops.add(source, 'nonfood_no_nutrition', name, r['source_url'])
            continue
        yield c


# ------------------------------------------------------------------ bodystore family
def a_bodystore(fkey='bodystore', source='bodystore'):
    path = RAW + '/%s/products.jsonl' % folder(fkey)
    for r in jl(path):
        bc = r.get('breadcrumb') or []
        flat = r.get('nutrients_flat') or {}
        name = clean(r.get('name'))
        if not name:
            Drops.add(source, 'no_name')
            continue
        if not flat and is_nonfood(name, bc):
            Drops.add(source, 'nonfood_no_nutrition', name, r.get('source_url'))
            continue
        gone = r.get('page_status') == 'gone' or r.get('discontinued') is True
        c = cand(source, r['sku'], url=r['source_url'], fetched_on=r['fetched_on'], name=name, brand=clean(r.get('brand')), ean=r.get('ean'),
                 categories=bc, ingredients=clean(r.get('ingredients')), pack_size=clean((r.get('pack_size') or {}).get('raw')), gone=gone, country=r.get('country'))
        c['extra'] = {'sku': r['sku'], 'price': r.get('price'), 'currency': r.get('currency'), 'servings_per_pack': r.get('servings_per_pack'), 'flavours': r.get('flavours') or None,
                      'page_status': r.get('page_status'), 'archive_timestamp': r.get('archive_timestamp')}
        c['extra'] = {k: v for k, v in c['extra'].items() if v is not None}
        fl = list(r.get('flags') or []) + list(r.get('nutrition_flags') or [])
        if r.get('nutrition_flag'):
            fl.append(r['nutrition_flag'])
        c['flags'] = list(dict.fromkeys(f for f in fl if f))
        for label, vals in flat.items():
            for col, v in vals.items():
                if col == 'pct_ri':
                    continue
                if v.get('implausible'):
                    continue
                tgt = c['per100'] if col == 'per100' else c['perserv'] if col == 'perserving' else None
                if tgt is None:
                    continue
                if col == 'perserving' and not c['serving_g']:
                    c['serving_g'] = serving_grams(v.get('col'))
                    c['serving_text'] = v.get('col')
                qual = '<' if v.get('qualifier') == '<' else None
                if v.get('kcal') is not None or v.get('kj') is not None:
                    if v.get('kcal') is not None:
                        tgt.append(('Energi', float(v['kcal']), 'kcal', qual, None))
                    if v.get('kj') is not None:
                        tgt.append(('Energi', float(v['kj']), 'kJ', qual, None))
                elif v.get('value') is not None:
                    tgt.append((label, float(v['value']), v.get('unit'), qual, None))
        yield c


# --------------------------------------------------------------------- Open Food Facts
def _off_region(r):
    ct = {t.split(':', 1)[-1] for t in (r.get('countries_tags') or [])}
    if 'norway' in ct:
        reg = 'NO'
    elif 'sweden' in ct:
        reg = 'SE'
    elif 'denmark' in ct:
        reg = 'DK'
    elif ct & {'finland', 'iceland'}:
        reg = 'other'
    elif ct & OFF_EU:
        reg = 'EU'
    elif 'united-kingdom' in ct:
        reg = 'UK'
    elif 'united-states' in ct:
        reg = 'US'
    else:
        reg = 'other'
    return reg, bool(ct & OFF_NORDIC)


def a_off(fkey='openfoodfacts', source='openfoodfacts'):
    glob = source == 'openfoodfacts-nordic-global'
    for r in jl(RAW + '/%s/products.jsonl' % folder(fkey)):
        name = clean(r.get('name')) or clean((r.get('names_by_lang') or {}).get('main')) or clean(r.get('generic_name'))
        brand = clean(r.get('brand'))
        if brand and ',' in brand:
            brand = clean(brand.split(',')[0])
        ing = r.get('ingredients_text')
        if not ing and r.get('ingredients_by_lang'):
            ibl = r['ingredients_by_lang']
            ing = ibl.get('nb') or ibl.get('no') or ibl.get('sv') or ibl.get('da') or ibl.get('main')
        cats = [t.split(':', 1)[-1] for t in (r.get('categories_tags') or [])][:12]
        al = allergen_dict([t.split(':', 1)[-1] for t in (r.get('allergens_tags') or [])], [t.split(':', 1)[-1] for t in (r.get('traces_tags') or [])])
        c = cand(source, r['ean'], url=r['source_url'], fetched_on=r['fetched_on'], name=name, brand=brand, ean=r['ean'],
                 pack_size=clean(r.get('pack_size')), categories=cats, ingredients=clean(ing), allergens=al,
                 serving_g=num(r.get('serving_quantity')), serving_text=clean(r.get('serving_size')))
        c['extra'] = {'nutriscore_grade': r.get('nutriscore_grade'), 'nova_group': r.get('nova_group'), 'completeness': r.get('completeness'),
                      'product_quantity': r.get('product_quantity'), 'product_quantity_unit': r.get('product_quantity_unit'), 'last_modified_t': r.get('last_modified_t'),
                      'countries': [t.split(':', 1)[-1] for t in (r.get('countries_tags') or [])][:12] or None, 'selection': r.get('selection')}
        c['extra'] = {k: v for k, v in c['extra'].items() if v is not None}
        if glob:
            c['region'], c['nr'] = _off_region(r)
        if r.get('obsolete'):
            c['gone'] = True
            c['flags'].append('off_obsolete')
        if r.get('flag'):
            c['flags'].append(r['flag'])
        nu = r.get('nutrition') or {}
        have_kj = 'energy-kj' in nu
        for k, v in nu.items():
            val = num(v.get('per_100g'))
            if val is None:
                continue
            u = (v.get('unit') or '').strip()
            if k.startswith(('fruits', 'nova', 'nutrition-score', 'carbon', 'cocoa', 'new_')) or u == '% DV':
                continue
            if k == 'energy-kcal':
                c['per100'].append(('energy-kcal', val, 'kcal', None, 'kcal'))
            elif k == 'energy-kj':
                c['per100'].append(('energy-kj', val, 'kJ', None, 'kj'))
            elif k == 'energy':
                if not have_kj:
                    c['per100'].append(('energy-kj', val, 'kJ', None, 'kj'))
            elif k == 'alcohol':
                if u.startswith('% vol') or u == '%':
                    c['per100'].append(('alcohol vol', val, '%vol', None, 'alcohol_vol_pct'))
            elif u.startswith('%'):
                continue
            else:
                c['per100'].append((k.replace('-', ' '), val, 'g', None, None))   # OFF stores everything in g per 100 g
        yield c


# ------------------------------------------------------------------ tine-style producers and DK/SE grocery
BRANDS = ['gilde', 'prior', 'q-meieriene', 'fjordland', 'tine', 'grandiosa', 'nidar', 'saetre', 'toro', 'firstprice', 'eldorado', 'mills', 'ringnes', 'synnove', 'kavli', 'hennig-olsen',
          'bodylab-dk', 'helsam-dk', 'matas-dk', 'nutramino-dk', 'ica-se']


def a_brands():
    for src in BRANDS:
        p = RAW + '/%s/products.jsonl' % folder(src)
        if not os.path.exists(p):
            continue
        for r in jl(p):
            url = r.get('source_url')
            al = None
            if isinstance(r.get('allergens_raw'), dict):
                al = allergen_dict([k for k, v in r['allergens_raw'].items() if str(v).lower() in ('ja', 'yes', 'true')])
            elif r.get('allergens_contained'):
                al = allergen_dict([x for x in r['allergens_contained'] if not str(x).endswith(':')])
            elif r.get('allergens_status'):
                al = allergen_dict([k for k, v in r['allergens_status'].items() if v == 'contains'], [k for k, v in r['allergens_status'].items() if v in ('may_contain', 'traces')])
            elif isinstance(r.get('allergens_raw'), str):
                al = {'contains': [], 'may_contain': [], 'text': clean(r['allergens_raw'])}
            elif isinstance(r.get('allergens'), list):
                al = allergen_dict(r['allergens'])
            elif isinstance(r.get('allergens'), str):
                al = {'contains': [], 'may_contain': [], 'text': clean(r['allergens'])}
            ps = r.get('pack_size_raw') or (('%g g' % r['pack_size_g']) if r.get('pack_size_g') else None)
            name = clean(r.get('name'))
            if not name:
                continue
            cats = r.get('categories') if isinstance(r.get('categories'), list) else [x for x in [r.get('category')] if x]
            if r.get('subcategory'):
                cats = cats + [r['subcategory']]
            c = cand(src, url or name, url=url, fetched_on=r.get('fetched_on'), name=name, brand=clean(r.get('brand')), ean=r.get('ean'), pack_size=clean(ps),
                     categories=cats, ingredients=clean(r.get('ingredients')), allergens=al)
            c['extra'] = {k: r.get(k) for k in ('tine_sku', 'material_number', 'origin_country', 'supplier', 'packagings', 'abv_raw', 'brand_line', 'sku', 'price_dkk', 'price_sek', 'serving_text',
                                                'flavours', 'varenummer') if r.get(k) is not None}
            c['flags'] += [f for f in (r.get('quality_flags') or [])]
            nf = r.get('nutrition_flag')
            if nf:
                c['flags'].append(nf)
                if 'all_zero' in str(nf):
                    Drops.add(src, 'all_zero_placeholder', name, url)
                    continue
            if r.get('per100_is_prepared'):
                c['flags'].append('per100_is_prepared_state')
            if r.get('flavours') and len(r['flavours']) >= 2:
                c['flags'].append('flavour_nutrition_shared_assumed')
            if r.get('nutrition_basis_note'):
                c['extra']['basis_note'] = r['nutrition_basis_note']
            c['per100'] = keyed_entries(r.get('nutrition_per100'))
            for t in ((r.get('nutrition') or {}).get('tables') or []):
                if t.get('basis') == 'per_serving' and not c['perserv']:
                    c['perserv'] = keyed_entries(t.get('values'))
                    c['serving_text'] = t.get('header')
                    c['serving_g'] = serving_grams(t.get('header'))
            if not c['per100'] and not c['perserv'] and is_nonfood(name, cats):
                Drops.add(src, 'nonfood_no_nutrition', name, url)
                continue
            yield c


# --------------------------------------------------------------------------- sources
# Folder keys go through folder(): build.py's RAW_FOLDERS decides which raw folder is read (v2 instead of the old ones).
SOURCES = [
    ('matvaretabellen', a_matvaretabellen), ('frida-dk', a_frida), ('livsmedelsverket', a_livsmedelsverket), ('usda-fdc', a_usda),
    ('openfoodfacts', lambda: a_off('openfoodfacts', 'openfoodfacts')),
    ('openfoodfacts-nordic-global', lambda: a_off('openfoodfacts-nordic-global', 'openfoodfacts-nordic-global')),
    ('kassalapp', a_kassalapp), ('norgesgruppen', a_ng),
    ('tights', lambda: a_tights('tights', 'tights')), ('tights-discontinued', lambda: a_tights('tights-discontinued', 'tights-discontinued')),
    ('gymgrossisten', lambda: a_gym('gymgrossisten', 'gymgrossisten')), ('gymgrossisten-discontinued', lambda: a_gym('gymgrossisten-discontinued', 'gymgrossisten-discontinued')),
    ('gymgrossisten-se', lambda: a_gym('gymgrossisten-se', 'gymgrossisten-se')), ('bodystore-dk', lambda: a_gym('bodystore-dk', 'bodystore-dk')),
    ('bodystore', lambda: a_bodystore('bodystore', 'bodystore')), ('bodystore-discontinued', lambda: a_bodystore('bodystore-discontinued', 'bodystore-discontinued')),
    ('bodystore-se', lambda: a_bodystore('bodystore-se', 'bodystore-se')),
    ('proteinfabrikken', lambda: a_proteinfabrikken('proteinfabrikken', 'proteinfabrikken')),
    ('proteinfabrikken-discontinued', lambda: a_proteinfabrikken('proteinfabrikken-discontinued', 'proteinfabrikken-discontinued')),
    ('bulk', lambda: a_pages('bulk', 'bulk', merge_extra=True)), ('bulk-discontinued', lambda: a_pages('bulk-discontinued', 'bulk-discontinued', merge_extra=True)),
    ('myprotein', lambda: a_pages('myprotein', 'myprotein')), ('myprotein-discontinued', lambda: a_pages('myprotein-discontinued', 'myprotein-discontinued')),
    ('myprotein-uk', lambda: a_pages('myprotein-uk', 'myprotein-uk')),
    ('brands', a_brands),
] + [(s, (lambda s=s: a_pages(s, s))) for s in [
    # Norwegian shops (nogen shape)
    'apex-no', 'bodylab-no', 'coore-no', 'diggbox-no', 'helsekost-no', 'kost1-no', 'life-no', 'life-no-discontinued', 'nordicpower-no', 'sportylab-no', 'barebells-no', 'proteincompany-no',
    # Swedish shops (variants share nutrition; extra_tables are other flavours, not merged)
    'tillskottsbolaget', 'bodylab-se', 'proteinbolaget', 'goldenathlete', 'mmsports', 'sportkost', 'bodypower', 'tyngre', 'life-se', 'halsokostbolaget', 'halsafitnessbutiken',
    'barebells', 'nocco', 'starnutrition-se', 'kungmarkatta',
    # UK / US / EU brand sites
    'quest', 'fulfil', 'reflex', 'esn', 'grenade', 'cellucor', 'muscletech', 'applied-nutrition', 'weider', 'gorilla-mind', 'ghost', 'transparent-labs', 'optimum-nutrition',
    'dymatize', 'legion', 'bodybuilding']] + [('scitec', lambda: a_pages('scitec', 'scitec', merge_extra=True))]
