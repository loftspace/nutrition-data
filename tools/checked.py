"""Store-checked fixes (data/checked.json), applied by build_slim.py after every automatic rule.

Max, 2026-11-12: sample the products Norwegian food stores sell, check our rows against the label, and
rank how common each product is so search can put everyday foods first. Agents read the store pages
(Meny, Spar, Joker, Oda, Coop, Rema 1000, kassal.app); a second agent re-read the source for every fix
before it was written here. Nothing in this file is estimated: every number is copied from a label.

checked.json:
  fixes:  [{id, name?, category?, sizes?: ["150 g", "300 g"], nutrients?: {kcal: 268, fibre_g: null, ...}, source_url}]
          a null nutrient means the label does not give it: the value becomes unknown, never 0
          add_eans: barcodes the shops sell this same product under that the data did not know (scanning finds it)
x
  drop:   [{id, why}]                  numbers that cannot be true (salt 12 g in fish cakes); the id goes to removed
  add:    [{id, name, brand, category, unit, sizes, eans, nutrients, source, source_url, serving_g?, derived?, menu?}]
          menu: true for a restaurant menu item (no barcode)
          serving_g: one portion in grams (a restaurant item); derived: true when the per-100 values were
          worked out in code from the portion values and the portion weight (flag per100_derived_from_serving).
          eans may be empty for a restaurant item that has no barcode
  common: {id: 1 | 2 | 3}              3 = staple most households buy often, 2 = common, 1 = regular
"""
import json
import os

CATEGORIES = frozenset((
    'dairy_eggs', 'meat_fish', 'bread_cereal_grain', 'fruit_vegetables', 'drinks', 'snacks_sweets',
    'ready_meals_sauces', 'protein_drink_or_dessert', 'other_food', 'protein_bar', 'protein_powder',
    'energy_gel_sports_drink',
))
NUTRIENTS = ('kcal', 'protein_g', 'fat_g', 'sat_fat_g', 'carbs_g', 'sugars_g', 'fibre_g', 'salt_g')
FLAG = 'corrected_from_store'
MAX_SIZES = 6


def load(data_dir):
    path = os.path.join(data_dir, 'checked.json')
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def validate(checked):
    """Raise ValueError on anything the build must not guess about."""
    for f in checked.get('fixes', ()):
        if not f.get('source_url'):
            raise ValueError('fix without source_url: %s' % f.get('id'))
        if 'category' in f and f['category'] not in CATEGORIES:
            raise ValueError('unknown category %r for %s' % (f['category'], f['id']))
        for k, v in (f.get('nutrients') or {}).items():
            if k not in NUTRIENTS or (v is not None and (not isinstance(v, (int, float)) or v < 0)):
                raise ValueError('bad nutrient %s=%r for %s' % (k, v, f['id']))
        if len(f.get('sizes') or ()) > MAX_SIZES:
            raise ValueError('more than %d sizes for %s' % (MAX_SIZES, f['id']))
    for a in checked.get('add', ()):
        n = a.get('nutrients') or {}
        if not a.get('source_url') or not (a.get('eans') or a.get('serving_g') or a.get('menu')) or any(n.get(k) is None for k in ('kcal', 'protein_g', 'fat_g', 'carbs_g')):
            raise ValueError('add needs source_url, eans (or menu: true for a restaurant item) and the four main numbers: %s' % a.get('id'))
        if a.get('serving_g') is not None and not (0 < a['serving_g'] < 3000):
            raise ValueError('add %s: serving_g out of range' % a.get('id'))
        if a.get('category') not in CATEGORIES or a.get('unit') not in ('g', 'ml'):
            raise ValueError('add %s: bad category or unit' % a.get('id'))
    for v in checked.get('common', {}).values():
        if v not in (1, 2, 3):
            raise ValueError('common must be 1, 2 or 3')


def apply(checked, kept, moved, extra_search, flags_by_id, units, stats, open_sources=None):
    """Change `kept` in place. Returns {id: sizes text} and {id: common tier} for the row writer.

    Ids name rows of the live database, so a fix whose row is gone (renamed id, dropped) is skipped and
    counted, never applied to a guess. `open_sources` is set for the open variant: label numbers and
    added products come from shop pages, which are not open, so they stay out of it.
    """
    validate(checked)
    skipped = []
    dropped = 0
    for d in checked.get('drop', ()):
        if kept.pop(d['id'], None) is None:
            skipped.append(d['id'])
            continue
        extra_search.pop(d['id'], None)
        for k in [k for k, v in moved.items() if v == d['id']]:
            del moved[k]  # listings folded into a dropped row are gone too, not redirected to nothing
        dropped += 1
    # Folds next, so a fix aimed at the kept row sees the final row.
    folded = 0
    for f in checked.get('fold', ()):
        old, new = f['id'], f['into']
        if old not in kept or new not in kept or old == new:
            skipped.append(old)
            continue
        p = kept.pop(old)
        words = [extra_search.get(new), extra_search.pop(old, None), p['name'], p['flavour']]
        extra_search[new] = ' '.join(x for x in words if x)
        for k, v in list(moved.items()):
            if v == old:
                moved[k] = new
        moved[old] = new
        folded += 1
    zero = []
    # One spelling per brand: an added product takes the spelling the file already uses.
    spelling = {}
    for p in kept.values():
        if p['brand']:
            spelling.setdefault(''.join(p['brand'].lower().split()), p['brand'])
    for a in checked.get('add', ()):
        if a['id'] in kept:
            skipped.append(a['id'])
            continue
        if open_sources is not None and a['source'] not in open_sources:
            continue
        n = a['nutrients']
        if all(n.get(k) == 0 for k in ('kcal', 'protein_g', 'fat_g', 'carbs_g')):
            zero.append(a['id'])  # all-zero means missing (Zero kcal rule): never add it from a label
            continue
        kept[a['id']] = {
            'id': a['id'], 'name': a['name'], 'pack_size': None,
            'brand': spelling.get(''.join((a.get('brand') or '').lower().split()), a.get('brand')),
            'ean': (a.get('eans') or [None])[0], 'flavour': None, 'category': a['category'], 'serving_g': a.get('serving_g'),
            'primary_source': a['source'], 'status': 'from_source', 'data_quality': None,
            **{k: n.get(k) for k in NUTRIENTS},
        }
        flags_by_id[a['id']] = ([] if n.get('fibre_g') is not None else ['missing_fibre']) + (['per100_derived_from_serving'] if a.get('derived') else [])
        units[a['id']] = a['unit']
        extra_search[a['id']] = ' '.join(a.get('also_known_as', ()))
    sizes = {a['id']: ', '.join(a['sizes']) for a in checked.get('add', ()) if a.get('sizes') and a['id'] in kept}
    fixed = 0
    for f in checked.get('fixes', ()):
        p = kept.get(f['id'])
        if p is None:
            skipped.append(f['id'])
            continue
        if f.get('name'):
            extra_search[f['id']] = ' '.join(x for x in (extra_search.get(f['id']), p['name']) if x)
            p['name'] = f['name']
        if f.get('category'):
            p['category'] = f['category']
        if f.get('add_eans'):
            p['extra_eans'] = list(p.get('extra_eans', ())) + list(f['add_eans'])
        if f.get('sizes'):
            sizes[f['id']] = ', '.join(f['sizes'])
        n = f.get('nutrients')
        if n and open_sources is not None:
            n = None
        if n and all(dict(p, **n).get(k) == 0 for k in ('kcal', 'protein_g', 'fat_g', 'carbs_g')):
            zero.append(f['id'])  # all-zero means missing (Zero kcal rule): never write it from a label
            n = None
        if n:
            for k, v in n.items():
                p[k] = v
            if FLAG not in flags_by_id[f['id']]:
                flags_by_id[f['id']].append(FLAG)
        fixed += 1
    common = {i: t for i, t in checked.get('common', {}).items() if i in kept}
    stats['checked_fixed'] = fixed
    stats['checked_folded'] = folded
    stats['checked_dropped'] = dropped
    stats['checked_added'] = sum(1 for a in checked.get('add', ()) if a['id'] in kept)
    stats['checked_common'] = len(common)
    stats['checked_skipped'] = len(skipped)
    stats['checked_all_zero_refused'] = len(zero)
    return sizes, common
