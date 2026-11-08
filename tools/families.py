"""Display tidying and flavour families for the slim database (Makro#46 follow-up, 2026-11-08).

Tidying: ALL-CAPS names and brands become Title Case, trademark signs and a repeated
"- BRAND" tail go. Mixed-case names are left as the source wrote them.

Families: the same product sold in several flavours, pack sizes or shops ("YT Proteinpudding
Mango 190g", "... Vanilje 190g", "... Sjokolade 10x190g - TIPAKNING") becomes one product.
A family is a candidate only when (Max's rule, 2026-11-08):
  - the first two name words (sizes stripped) and the per-100 unit are the same,
  - the brands agree (or one is missing),
  - every nutrient both members know is within 5% (at least 0.5 g / 0.5 kcal), for every pair.
Candidates whose names differ by more than size or case were checked with Jev
(build/jev_families.py); the accepted families are committed in data/families.json and the
slim build applies them. The family keeps the numbers of its best member, never an average.

Usage (writes data/families_candidates.json from the shards):
  python -I tools/families.py --data data
"""
import argparse
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict

NUTRIENTS = ('kcal', 'protein_g', 'fat_g', 'sat_fat_g', 'carbs_g', 'sugars_g', 'fibre_g', 'salt_g')
TOLERANCE = 0.05
FLOOR = 0.5

_MARKS = re.compile(r'[®™©]')
_SMALL = frozenset(('og', 'av', 'med', 'i', 'pa', 'på', 'til', 'uten', 'fra', 'for', 'och', 'with', 'and', 'of', 'the', 'in', 'en', 'et'))
_SIZE = re.compile(
    r'(\d+\s*[x×]\s*)?\d+(?:[.,]\d+)?\s*(?:kg|g|gr|gram|grams|ml|cl|dl|l|ltr|liter|litre|stk|pk|pakk|pack)(?![a-zæøå])'
    r'|\btipakning\b|\b\d+\s*-?\s*pk\b|\b\d+\s*x\b|\bbig\s+buy\b|\bmix\s*&\s*match\b|\bpr\.?\s*kg\b|\benh\b'
    r'|\bfamiliepakn\w*|\bstorpakn\w*|\bstorpack\w*', re.I)
_LETTERS = {'ø': 'o', 'æ': 'ae', 'å': 'a', 'ä': 'a', 'ö': 'o', 'ü': 'u', 'ß': 'ss'}


def fold(text):
    text = (text or '').lower()
    for k, v in _LETTERS.items():
        text = text.replace(k, v)
    text = unicodedata.normalize('NFKD', text)
    return ''.join(ch for ch in text if not unicodedata.combining(ch))


def _all_caps(text):
    letters = [ch for ch in text if ch.isalpha()]
    return len(letters) > 3 and all(ch.isupper() for ch in letters)


def _cap(word):
    # Capitalise each part of a hyphenated word: HENNIG-OLSEN -> Hennig-Olsen.
    return '-'.join(w[:1].upper() + w[1:].lower() for w in word.split('-'))


def capital_brands(brands):
    """Brands of two or three letters that the sources mostly write in capitals (YT, ICA, ESN), lowercased.
    Short brands that are mostly written as words (Bob, Max, One) are left out."""
    spellings = defaultdict(lambda: defaultdict(int))
    for b in brands:
        b = _MARKS.sub('', b or '').strip()
        if re.fullmatch(r'[^\W\d_]{2,3}', b):
            spellings[b.lower()][b] += 1
    return frozenset(k for k, v in spellings.items() if max(v, key=v.get).isupper())


def tidy_brand(brand, short_brands=frozenset()):
    if brand is None:
        return None
    b = re.sub(r'\s+', ' ', _MARKS.sub('', brand)).strip()
    if not b:
        return None
    if b.lower() in short_brands:
        return b.upper()
    if b.islower() or b.isupper():
        return ' '.join(_cap(w) for w in b.split(' '))
    return b


def tidy_name(name, brand, short_brands=frozenset()):
    s = re.sub(r'\s+', ' ', _MARKS.sub('', name or '')).strip()
    b = re.sub(r'\s+', ' ', _MARKS.sub('', brand or '')).strip()
    if b:
        s = re.sub(r'\s*[-–]\s*' + re.escape(b) + r'\s*$', '', s, flags=re.I).strip() or s
    first, _, rest = s.partition(' ')
    if first.lower() in short_brands and not first.isupper():
        s = (first.upper() + ' ' + rest).strip()
    if not _all_caps(s):
        return s
    brand_words = {w.lower() for w in b.split()}
    out = []
    for i, w in enumerate(s.split(' ')):
        lw = w.lower()
        if any(ch.isdigit() for ch in w):
            out.append(lw)
        elif lw in brand_words and len([c for c in w if c.isalpha()]) <= 3:
            out.append(w.upper())
        elif i > 0 and lw in _SMALL:
            out.append(lw)
        else:
            out.append(_cap(w))
    return ' '.join(out)


def strip_sizes(name):
    s = _SIZE.sub(' ', name or '')
    s = re.sub(r'\s*[-–,]\s*(?=$|[-–,])', ' ', s)
    s = re.sub(r'[\s,–-]+$', '', s)
    return re.sub(r'\s+', ' ', s).strip()


def words(name):
    return re.findall(r'[0-9a-z]+', fold(strip_sizes(_MARKS.sub('', name or ''))))


def close(a, b):
    if a['kcal'] is None or b['kcal'] is None:
        return False
    for n in NUTRIENTS:
        x, y = a[n], b[n]
        if x is None or y is None:
            continue
        if abs(x - y) > max(TOLERANCE * max(abs(x), abs(y)), FLOOR):
            return False
    return True


# Words that mark a separate product, not a flavour (review of 200 families, 2026-11-08).
# Listings join a family only when they carry the same set. Folded spelling (see fold()).
_VARIANT_WORDS = {
    'laktosfri': 'lactose_free', 'laktosefri': 'lactose_free', 'laktosfritt': 'lactose_free', 'laktosefritt': 'lactose_free',
    'lactosefree': 'lactose_free', 'zero': 'zero', 'light': 'light', 'lett': 'light', 'latt': 'light', 'lite': 'light',
    'sukkerfri': 'sugar_free', 'sockerfri': 'sugar_free', 'sugarfree': 'sugar_free', 'usotet': 'sugar_free', 'osotad': 'sugar_free',
    'okologisk': 'organic', 'ekologisk': 'organic', 'oko': 'organic', 'eko': 'organic', 'organic': 'organic',
    'vegan': 'vegan', 'glutenfri': 'gluten_free', 'glutenfree': 'gluten_free', 'energy': 'energy',
    'rokt': 'smoked', 'urokt': 'unsmoked', 'marinert': 'marinated', 'marinerad': 'marinated', 'marinade': 'marinated',
    'grillmarinade': 'marinated', 'jomfru': 'virgin', 'virgin': 'virgin', 'kapsler': 'capsules', 'kapslar': 'capsules',
    'capsules': 'capsules', 'koffeinfri': 'decaf', 'decaf': 'decaf', 'fettfri': 'fat_free', 'mager': 'lean',
}
_VARIANT_PHRASES = {
    'u sukker': 'sugar_free', 'uten sukker': 'sugar_free', 'utan socker': 'sugar_free', 'no sugar': 'sugar_free',
    'sugar free': 'sugar_free', 'fat free': 'fat_free', 'lactose free': 'lactose_free', 'uten laktose': 'lactose_free',
    'hele bonner': 'whole_beans', 'helt bonner': 'whole_beans',
}
_BUNDLE = re.compile(r'\s\+\s*[A-Za-zÆØÅæøå]|\bshaker\b|\bgaveeske\b|\bgift\s*box\b', re.I)
NEAR_ZERO_KCAL = 5.0


def variant_marks(name, brand=None):
    toks = words(name) + words(brand)
    marks = {_VARIANT_WORDS[t] for t in toks if t in _VARIANT_WORDS}
    text = ' ' + ' '.join(toks) + ' '
    marks |= {m for ph, m in _VARIANT_PHRASES.items() if ' ' + ph + ' ' in text}
    return frozenset(marks)


def is_bundle(name):
    return bool(_BUNDLE.search(name or ''))


def compatible(a, b):
    """True when two listings may be one product (the family rule, see the module docstring)."""
    if not close(a, b) or not brands_agree(a, b):
        return False
    if is_bundle(a['name']) or is_bundle(b['name']):
        return False
    if variant_marks(a['name'], a['brand']) != variant_marks(b['name'], b['brand']):
        return False
    # Near-zero foods (diet drinks, coffee, tea) are always within 5%, so flavours must not decide.
    if max(a['kcal'], b['kcal']) < NEAR_ZERO_KCAL and words(a['name']) != words(b['name']):
        return False
    return True


def _brand_key(brand):
    w = words(brand)
    return w[0] if w else None


def brands_agree(a, b):
    ka, kb = _brand_key(a['brand']), _brand_key(b['brand'])
    return ka is None or kb is None or ka == kb or ka in words(b['name']) or kb in words(a['name'])


def candidates(rows):
    """Lists of product ids that pass the family rule. Rows need id, name, brand, unit and the nutrients."""
    groups = defaultdict(list)
    for r in rows:
        w = words(r['name'])
        if w and r['kcal'] is not None:
            groups[(w[0], w[1] if len(w) > 1 else '', r['unit'])].append(r)
    out = []
    for key in sorted(groups):
        left = sorted(groups[key], key=lambda r: r['id'])
        while left:
            fam = [left.pop(0)]
            for r in left[:]:
                if all(compatible(r, m) for m in fam):
                    fam.append(r)
                    left.remove(r)
            if len(fam) > 1:
                out.append([m['id'] for m in fam])
    return out


def names_differ(names):
    """True when the names differ by more than sizes, case and punctuation."""
    return len({' '.join(words(n)) for n in names}) > 1


def family_name(rep_name, names, brand=None):
    """The words every member shares, in the representative's order; else the representative without sizes."""
    rep = strip_sizes(rep_name)
    common = set(words(names[0]))
    for n in names[1:]:
        common &= set(words(n))
    kept = [w for w in re.findall(r'\S+', rep) if words(w) and all(x in common for x in words(w))]
    while kept and (fold(kept[-1]).strip('/&,') in _SMALL or kept[-1] in ('m/', 'u/', 'w/', '&', '+', '-')):
        kept.pop()  # no dangling "med", "og" or "&" at the end
    brand_only = set(words(' '.join(kept))) <= set(words(brand))
    if kept and not brand_only:
        return ' '.join(kept).strip(' ,-–')
    return rep


def load_rows(data_dir):
    """The products the full slim build keeps, with the fields the family rule needs."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import build_slim
    with open(os.path.join(data_dir, 'manifest.json'), encoding='utf-8') as f:
        manifest = json.load(f)
    rows = []
    for p in build_slim.read_shard(data_dir, manifest, 'products'):
        if p['merged_into'] or not p['norway_relevant'] or p['hidden'] or not (p['name'] or '').strip():
            continue
        if p['category'] == 'non_food':
            continue
        r = {k: p[k] for k in ('id', 'name', 'brand') + NUTRIENTS}
        r['unit'] = build_slim.per_100_unit(p['pack_size'], p['name'])
        rows.append(r)
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--data', required=True)
    ap.add_argument('--out', default=None)
    a = ap.parse_args(argv)
    rows = load_rows(a.data)
    by_id = {r['id']: r for r in rows}
    fams = candidates(rows)
    out = [{'members': f, 'needs_check': names_differ([by_id[i]['name'] for i in f])} for f in fams]
    path = a.out or os.path.join(a.data, 'families_candidates.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=0)
    print('%d candidate families, %d products, %d need a Jev check' % (
        len(out), sum(len(x['members']) for x in out), sum(x['needs_check'] for x in out)))


if __name__ == '__main__':
    sys.exit(main())
