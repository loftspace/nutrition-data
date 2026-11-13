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
TOLERANCE = 0.10  # Max, 2026-11-08: flavours such as YT Proteinmelk Kakao (46) and Naturell (43) are one product
FLOOR = 0.3  # grams or kcal; 2.1 vs 2.6 g protein is a different product (third review, 2026-11-08)

_MARKS = re.compile(r'[®™©]')
_SMALL = frozenset(('og', 'av', 'med', 'i', 'pa', 'på', 'til', 'uten', 'fra', 'for', 'och', 'with', 'and', 'of', 'the', 'in', 'en', 'et'))
_SIZE = re.compile(
    r'(\d+\s*[x×]\s*)?\d+(?:[.,]\d+)?\s*(?:kg|g|gr|gram|grams|ml|cl|dl|l|ltr|liter|litre|stk|pk|pakk|pack)(?![a-zæøå])'
    r'|\btipakning\b|\b\d+\s*-?\s*pk\b|\b\d+\s*x\b|\bbig\s+buy\b|\bmix\s*&\s*match\b|\bpr\.?\s*kg\b|\benh\b'
    r'|\bfamiliepakn\w*|\bstorpakn\w*|\bstorpack\w*|\bdatodeal\b|\bkampanje\b|\btilbud\b|\bspecial\s+deal\b', re.I)
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


def display_name(name, brand, lines, short_brands=frozenset(), keep_tail=False):
    """The name shown in the app: tidied, without pack sizes or promo words, and without a maker
    tacked on at the end ("YT Protein Yoghurt Salt Karamell 200g Tine" -> "... Salt Karamell").
    The pack size stays in its own column. keep_tail: the name was checked (a label or a person gave it),
    so a brand at the end is the flavour ("McFlurry Oreo") and stays."""
    s = strip_sizes(tidy_name(name, brand, short_brands))
    s = re.sub(r'[,\s]+\d{4,}\b', '', s)  # article numbers such as ", 260201"
    raw = s.split(' ')
    own = set(words(brand))
    while len(raw) > 1 and not keep_tail:
        tail = tuple(words(raw[-1]))
        rest = set(words(' '.join(raw[:-1])))
        # Drop a maker tacked on at the end ("... 200g Tine"), but not when the rest is only the brand
        # itself ("Marabou Oreo" stays: Oreo is the product).
        if tail and any(b == tail for b in lines.brands) and not rest <= own:
            raw.pop()
            continue
        break
    s = ' '.join(raw).strip(' ,-–|')
    return s or tidy_name(name, brand, short_brands)


def strip_sizes(name):
    s = _SIZE.sub(' ', name or '')
    s = re.sub(r'\s*[-–,]\s*(?=$|[-–,])', ' ', s)
    s = re.sub(r'[\s,–-]+$', '', s)
    return re.sub(r'\s+', ' ', s).strip()


def words(name):
    return re.findall(r'[0-9a-z]+', fold(strip_sizes(_MARKS.sub('', name or ''))))


# Salt is tiny and often missing written as 0.0 (Open Food Facts "Protein Pudding" vs Tine's 0.31 g).
_FLOORS = {'salt_g': 0.5}


def close(a, b, tolerance=None):
    if a['kcal'] is None or b['kcal'] is None:
        return False
    for n in NUTRIENTS:
        x, y = a[n], b[n]
        if x is None or y is None:
            continue
        if abs(x - y) > max((tolerance or TOLERANCE) * max(abs(x), abs(y)), _FLOORS.get(n, FLOOR)):
            return False
    return True


# Words that mark a separate product the numbers cannot show (review of 200 families, 2026-11-08):
# lactose-free milk has the same macros as regular milk. Zero, light, sugar-free and fat-free are
# left to the numbers. Listings join a family only when they carry the same set. Folded spelling.
_VARIANT_WORDS = {
    'laktosfri': 'lactose_free', 'laktosefri': 'lactose_free', 'laktosfritt': 'lactose_free', 'laktosefritt': 'lactose_free',
    'lactosefree': 'lactose_free',
    'okologisk': 'organic', 'ekologisk': 'organic', 'oko': 'organic', 'eko': 'organic', 'organic': 'organic',
    'vegan': 'vegan', 'glutenfri': 'gluten_free', 'glutenfree': 'gluten_free', 'energy': 'energy',
    'rokt': 'smoked', 'urokt': 'unsmoked', 'marinert': 'marinated', 'marinerad': 'marinated', 'marinade': 'marinated',
    'grillmarinade': 'marinated', 'jomfru': 'virgin', 'virgin': 'virgin', 'kapsler': 'capsules', 'kapslar': 'capsules',
    'capsules': 'capsules', 'koffeinfri': 'decaf', 'decaf': 'decaf',
}
_VARIANT_PHRASES = {
    'lactose free': 'lactose_free', 'uten laktose': 'lactose_free',
    'hele bonner': 'whole_beans', 'helt bonner': 'whole_beans',
}
_BUNDLE = re.compile(r'\s\+\s*[A-Za-zÆØÅæøå]|\bshaker\b|\bgaveeske\b|\bgift\s*box\b', re.I)
NEAR_ZERO_KCAL = 5.0


_VARIANT_STEMS = (('royk', 'smoked'), ('rokt', 'smoked'), ('ekologisk', 'organic'), ('okologisk', 'organic'),
                  ('benfri', 'boneless'), ('utan ben', 'boneless'), ('premium', 'premium'), ('mariner', 'marinated'), ('marinad', 'marinated'), ('kryddad', 'seasoned'), ('krydret', 'seasoned'),
                  ('lagret', 'aged'), ('lagrad', 'aged'), ('fylt', 'filled'), ('fylld', 'filled'), ('morad', 'tenderised'))


def variant_marks(name, brand=None):
    toks = words(name) + words(brand)
    marks = {_VARIANT_WORDS[t] for t in toks if t in _VARIANT_WORDS}
    marks |= {m for t in toks for stem, m in _VARIANT_STEMS if stem in t}
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
    same_name = words(a['name']) == words(b['name'])
    same_words = same_name or ('_core' in a and '_core' in b and a['_core'] == b['_core'])  # any order, brand aside
    # Near-zero foods (diet drinks, coffee, tea) are always within 10%, so flavours must not decide.
    if max(a['kcal'], b['kcal']) < NEAR_ZERO_KCAL and not same_words:
        return False
    # Names that differ at all (beyond size and case): one known brand for both (third review,
    # 2026-11-08: "Pils", "Brie" and "Cheddar" from many makers; Tommi and Muscle NH2 whey).
    if not same_name:
        ka, kb = a.get('_bkey', _brand_key(a['brand'])), b.get('_bkey', _brand_key(b['brand']))
        if not ka or ka != kb:
            return False
    return True


REVIEWED_TOLERANCE = 0.15
_DIET = {'sukkerfri': 'sugar_free', 'sockerfri': 'sugar_free', 'sugarfree': 'sugar_free', 'zero': 'zero',
         'light': 'light', 'lett': 'light', 'latt': 'light', 'lite': 'light', 'fettfri': 'fat_free'}


def _diet_marks(r):
    return frozenset(_DIET[t] for t in words(r['name']) + words(r['brand']) if t in _DIET)


def reviewed_ok(a, rep):
    """May listing `a` join `rep` in a group a model read as one product (data/families_reviewed.json)?
    Same brand, same variant words, no bundle, and kcal and protein within 15% (at least 1 g)."""
    if not a.get('_bkey') or a.get('_bkey') != rep.get('_bkey'):
        return False
    if is_bundle(a['name']) or variant_marks(a['name'], a['brand']) != variant_marks(rep['name'], rep['brand']):
        return False
    if _diet_marks(a) != _diet_marks(rep):  # sugar-free / light versions (check of 150 merges, 2026-11-08)
        return False
    for n, floor in (('kcal', 1.0), ('protein_g', 1.0)):
        x, y = a[n], rep[n]
        if x is None or y is None:
            continue
        if abs(x - y) > max(REVIEWED_TOLERANCE * max(abs(x), abs(y)), floor):
            return False
    return True


def _brand_key(brand):
    w = words(brand)
    return w[0] if w else None


def brands_agree(a, b):
    ka, kb = _brand_key(a['brand']), _brand_key(b['brand'])
    return ka is None or kb is None or ka == kb or ka in words(b['name']) or kb in words(a['name'])


def join_compounds(toks, vocab):
    """Join two neighbouring words when the joined word is used elsewhere: protein melk -> proteinmelk."""
    out, i = [], 0
    while i < len(toks):
        if i + 1 < len(toks) and toks[i] + toks[i + 1] in vocab:
            out.append(toks[i] + toks[i + 1])
            i += 2
        else:
            out.append(toks[i])
            i += 1
    return out


_DESCRIBING = frozenset((
    'lett', 'light', 'lite', 'latt', 'mager', 'sur', 'soft', 'crispy', 'cheesy', 'ny', 'nye', 'new', 'premium',
    'original', 'classic', 'klassisk', 'ekstra', 'extra', 'mini', 'maxi', 'big', 'stor', 'store', 'liten', 'sma',
    'fersk', 'frisk', 'frossen', 'fryst', 'dypfryst', 'hel', 'hele', 'grov', 'fin', 'rokt', 'roykt', 'varmrokt',
    'kaldrokt', 'gravet', 'tvadelad', 'zero', 'sukkerfri', 'fettfri', 'glutenfri', 'ekologisk', 'okologisk',
))


class Lines:
    """The product line of a listing: its first product word, ignoring sizes, brand words and how
    compound words are split. "YT® PROTEINMELK KAKAO - YT®", "Protein Melk" (brand YT) and
    "Yt Proteinmelk Fettfri 1l Tine" are all the line `proteinmelk` (Max, 2026-11-08)."""

    def __init__(self, rows):
        name_count = defaultdict(int)
        self.vocab = set()
        for r in rows:
            for t in words(r['name']):
                name_count[t] += 1
                if len(t) >= 4:
                    self.vocab.add(t)
        brand_count = defaultdict(int)
        for r in rows:
            w = tuple(words(r['brand']))
            if w:
                brand_count[w] += 1
        # A brand written at the start of names (YT, First Price). Food words that are also a brand
        # (Protein Company) are left alone: as a name word they are far more common than as a brand.
        self.brands = sorted((b for b, n in brand_count.items()
                              if n >= 3 and name_count[b[0]] <= 5 * n), key=len, reverse=True)

    def brand_key(self, name, brand):
        """The brand a listing is sold under: one named at the start of the name wins ("YT Proteinmelk",
        shop brand Tine, is YT), else the brand field. First word only; None when unknown."""
        b = self.brand_in_name(name) or ' '.join(words(brand))
        return b.split()[0] if b else None

    def core(self, name, brand):
        """The words of a name as a set, without brand words, sizes or word order, split words joined:
        "Laks Røkt" and "Røkt Laks", "Bodylab Clear Whey Blackcurrant 500g" and "Blackcurrant Clear Whey"."""
        bk = self.brand_key(name, brand)
        own = set(join_compounds(words(brand), self.vocab)) | ({bk} if bk else set())
        for b in self.brands:
            if b[0] == bk:
                own |= set(b)
        toks = join_compounds(words(tidy_name(name, brand)), self.vocab)
        return frozenset(t for t in toks if t not in own) or frozenset(toks)

    def brand_in_name(self, name):
        """The known brand a name starts with ("Yt Proteinpudding ..." -> "yt"), or None."""
        toks = join_compounds(words(name), self.vocab)
        for b in self.brands:
            if len(toks) > len(b) and tuple(toks[:len(b)]) == b:
                return ' '.join(b)
        return None

    def line(self, name, brand):
        own = set(join_compounds(words(brand), self.vocab))
        toks = join_compounds(words(name), self.vocab)
        core = [t for t in toks if t not in own] or toks[:1]  # "Lofotpils" by Lofotpils is its own line
        for _ in range(2):
            for b in self.brands:
                if len(core) > len(b) and tuple(core[:len(b)]) == b:
                    core = core[len(b):]
                    break
        # A describing word is not the product: "Grilstad Lett Gullsalami" is the line gullsalami.
        while len(core) > 1 and (core[0] in _DESCRIBING or core[0] in _VARIANT_WORDS):
            core = core[1:]
        return core[0] if core else None


def candidates(rows):
    """Lists of product ids that pass the family rule. Rows need id, name, brand, unit and the nutrients."""
    lines = Lines(rows)
    groups = defaultdict(list)
    for r in rows:
        r['_bkey'] = lines.brand_key(r['name'], r['brand'])
        r['_core'] = lines.core(r['name'], r['brand'])
        key = lines.line(r['name'], r['brand'])
        if key and r['kcal'] is not None:
            groups[key].append(r)
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
    # Second pass for the rows no family took: the same words in another order ("Indrefilet Pampas",
    # "Pampas Indrefilet") have different first words, so the line pass never compared them.
    taken = {i for f in out for i in f}
    by_core = defaultdict(list)
    for r in rows:
        if r['id'] not in taken and r['kcal'] is not None and r['_core']:
            by_core[r['_core']].append(r)
    for key in sorted(by_core, key=sorted):
        left = sorted(by_core[key], key=lambda r: r['id'])
        while left:
            fam = [left.pop(0)]
            for r in left[:]:
                if all(compatible(r, m) for m in fam):
                    fam.append(r)
                    left.remove(r)
            if len(fam) > 1:
                out.append([m['id'] for m in fam])
    return out


def names_differ_core(cores):
    """True when the word sets (see Lines.core) differ."""
    return len(set(cores)) > 1


def names_differ(names):
    """True when the names differ by more than sizes, case and punctuation."""
    return len({' '.join(words(n)) for n in names}) > 1


def family_name(rep_name, names, brand=None, strict=False):
    """The words every member shares, in the order of the member name that holds the most of them
    (the representative first on a tie); else the representative without sizes."""
    rep = strip_sizes(rep_name)
    vocab = {t for n in names + [rep] for t in words(n) if len(t) >= 4}
    common = set(join_compounds(words(names[0]), vocab))
    for n in names[1:]:
        common &= set(join_compounds(words(n), vocab))
    common |= set(words(brand))  # a listing may leave the brand out of its name ("Protein Melk", brand YT)

    def shared(base):
        raw = re.findall(r'\S+', strip_sizes(base))
        kept, i = [], 0
        while i < len(raw):
            w = words(raw[i])
            nxt = words(raw[i + 1]) if i + 1 < len(raw) else []
            if w and len(w) == 1 and len(nxt) == 1 and w[0] + nxt[0] in common:
                kept += raw[i:i + 2]
                i += 2
                continue
            if w and all(x in common for x in w):
                kept.append(raw[i])
            i += 1
        while kept and (fold(kept[-1]).strip('/&,') in _SMALL or kept[-1] in ('m/', 'u/', 'w/', '&', '+', '-')):
            kept.pop()  # no dangling "med", "og" or "&" at the end
        return kept

    best = max([rep_name] + list(names), key=lambda n: len(join_compounds(words(' '.join(shared(n))), vocab)))
    kept = shared(best)
    brand_only = set(words(' '.join(kept))) <= set(words(brand))
    if kept and not brand_only:
        return ' '.join(kept).strip(' ,-–')
    return None if strict else rep  # strict: no shared product word, so no family name


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
    out = [{'members': f, 'needs_check': names_differ_core([by_id[i]['_core'] for i in f])} for f in fams]
    path = a.out or os.path.join(a.data, 'families_candidates.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=0)
    print('%d candidate families, %d products, %d need a Jev check' % (
        len(out), sum(len(x['members']) for x in out), sum(x['needs_check'] for x in out)))


if __name__ == '__main__':
    sys.exit(main())
