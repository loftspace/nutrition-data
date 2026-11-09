"""Clean-up rules for the slim database (Max, 2026-11-09: "go through the db of foods and do more clean up").

Pure functions, called from build_slim.build. Names and brands are repaired, never invented. A value that cannot
be true becomes unknown, and a product whose main numbers cannot be true is left out: scanning it then offers
a custom food, which is better than logging 55,948 kcal per 100 g.
"""
import collections
import html
import re

import families as fam

MAX_KCAL = 930  # pure fat is about 900; labels round up a little (coconut oil at 915)
MAX_MACRO = 100.5
MAX_MACRO_SUM = 105
_CLOSE = {'kcal': 1.0, 'protein_g': .3, 'fat_g': .3, 'carbs_g': .3, 'sat_fat_g': .5, 'sugars_g': .5, 'fibre_g': .5, 'salt_g': .5}
_MACROS = ('kcal', 'protein_g', 'fat_g', 'carbs_g')
_SIDE = ('sat_fat_g', 'sugars_g', 'fibre_g', 'salt_g')

# Greek, Cyrillic, Hebrew, Arabic, Thai, Japanese, Chinese, Korean: not products a Norwegian shop sells.
_FOREIGN = re.compile('[Ͱ-ϿЀ-ԯ֐-ۿ฀-๿぀-ヿ㐀-鿿가-힯]')
_LEGAL = re.compile(r'^(.*\S)[\s,]+(?:a/s|as|asa|ab|aps|sa|gmbh|ltd|llc|inc|oy|bv|srl|s\.l\.?|s\.a\.?|a\.s\.?)\.?$', re.I)
_ALIASES = {'bamadagligvare': 'Bama', 'hennigolsenis': 'Hennig-Olsen', 'santamarianorge': 'Santa Maria', 'nicks': "Nick's",
            '711': '7-Eleven', 'pataks': "Patak's", 'unclebens': "Uncle Ben's", 'benjerrys': "Ben & Jerry's",
            'terrasana': 'TerraSana', 'powerbar': 'PowerBar', 'bodyfuel': 'BodyFuel', 'ohyeah': 'Oh Yeah!', 'hellofresh': 'HelloFresh',
            'dahls': 'Dahls', 'toms': 'Toms'}
_TAIL = re.compile(r'[,\s]+(?:c\.?a\.?|m\.|m/|med|og)$|[\s,;:/–-]+$|\.$', re.I)
_HAS_SIZE = re.compile(r'\d\s*(?:g|gr|gram|kg|ml|cl|dl|l|ltr|liter|litre|stk|st|pk|pakk|pos|bx|biter|oz|fl|porsjoner|portioner|servings|eggs?|kapsler|tabletter|pcs|pieces?|c)\b', re.I)
_SALES_UNIT = re.compile(r'\bpr\.?\s*(?:kg|stk|stykk)\b\.?|\bstykk\b|\bstk\b|\bhusets\b|\bbestilles\b', re.I)
_TRAILING_UNIT = re.compile(r'\s*pr\.?\s*(?:kg|stk|stykk)\.?\s*$', re.I)  # also glued on: "Ferrarinipr Kg"
_ONLY_SIZE = re.compile(r'^\d+(?:[.,]\d+)?\s*(?:g|kg|ml|cl|dl|l)$', re.I)
_ONE_ITEM = re.compile(r'^1\s*(?:stk|st|pcs|piece|c|pk|pakke)$', re.I)
_SWEETENERS = ('sukrin', 'sukkr', 'sukkererstatning', 'sugar free', 'sukkerfri', 'sockerfri', 'polyol', 'erythrit', 'erytrit', 'stevi', 'sukralose', 'sucralose', 'sweet', 'sotstoff', 'xylitol')
_SUPPLEMENTS = frozenset(('amino_acids', 'creatine', 'collagen_joint', 'vitamin_mineral', 'herbal_other_supplement',
                          'pre_workout', 'fat_burner_weight_loss'))


def _tidy_text(text):
    text = fam._MARKS.sub('', html.unescape(text or '')).replace('\ufffd', ' ')  # marks first: "(®)" becomes empty brackets
    text = re.sub(r'\s*Â\s+', ' ', text)
    text = re.sub(r'\(\s*\)', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def no_empty_brackets(name):
    """Taking the size out of "Carbo Recovery (1 kg)" leaves empty brackets behind."""
    return re.sub(r'\s+', ' ', re.sub(r'\(\s*\)', ' ', name)).strip()


def _key(text):
    return re.sub(r'[\W_]+', '', fam.fold(text))


def _case(name):
    letters = [c for c in name if c.isalpha()]
    if not letters:
        return name
    if name.islower():
        return name[0].upper() + name[1:]
    if len(letters) > 3 and not name.isupper() and sum(c.isupper() for c in letters) / len(letters) > .7:  # all caps: families.tidy_name
        return ' '.join(w.capitalize() if len(w) >= 4 and w.isalpha() and w.isupper() else w for w in name.split(' '))
    return name


def clean_name(name, source):
    """Repair a name: stray characters, empty brackets, words cut off at the end, shouting."""
    s = _tidy_text(name)
    if source == 'apex-no':  # this shop writes `|` as a capital I: "ABE I PUMP Shot I Stim-Free I"
        s = re.sub(r'\s+I(?=\s|$)', '', s)
    while True:
        cut = _TAIL.sub('', s).strip()
        if cut == s or not cut:
            break
        s = cut
    return _case(s)


def clean_brand(brand):
    """A brand without company form (AS, AB, GmbH), or None when it has no letters."""
    b = _tidy_text(brand).replace('’', "'").rstrip('.').strip()
    if not any(c.isalpha() or c in '0123456789' for c in b):
        return None
    m = _LEGAL.match(b)
    while m:  # "Staur Fjellbakeri As As"
        b = m.group(1).rstrip(' ,.')
        m = _LEGAL.match(b)
    return _ALIASES.get(_key(b), b)


_SMALL_WORDS = frozenset(('og', 'and', 'i', 'of', 'the', 'de', 'la', 'le', 'av', 'på'))


def _capitalised(brand):
    if re.search(r'\S&\S', brand):
        return False
    return all(not w[0].isalpha() or w.lower() in _SMALL_WORDS or (w[0].isupper() and not (len(w) >= 4 and w.isupper()))
               for w in re.split(r'[\s-]+', brand) if w)


def _not_shouting(brand):
    letters = [c for c in brand if c.isalpha()]
    return ' '.join(w.capitalize() if len(w) >= 2 else w for w in brand.split(' ')) if len(letters) > 3 and brand.isupper() else brand


class BrandBook:
    """One spelling per brand. A spelling that keeps `&` or an apostrophe has lost nothing, so it comes before a
    plainer one; then capitalised words, Norwegian and Swedish letters, and the most common."""

    def __init__(self, brands):
        counts = collections.Counter(c for c in map(clean_brand, brands) if c)
        by_key = collections.defaultdict(list)
        for b, n in counts.items():
            by_key[_key(b)].append(('&' in b, _capitalised(b), bool(set(b.lower()) & set('æøå')), bool(set(b.lower()) & set('äöü')), "'" in b, n, b))
        self.best = {k: _not_shouting(max(v)[-1]) for k, v in by_key.items()}

    def canon(self, brand):
        c = clean_brand(brand)
        return self.best.get(_key(c), c) if c else None


def rename_brand(name, old, new):
    """A name that starts with the old spelling of the brand starts with the new one."""
    if not old or not new or old == new or not name.lower().startswith(old.lower()):
        return name
    rest = name[len(old):]
    return new + rest if not rest or not rest[0].isalnum() else name


def brand_in_name(brand, name):
    """True when the name already holds the brand, however it is split ("Biotech Usa" for BioTechUSA)."""
    return _key(brand) in _key(name)


def swapped_fields(brand, pack):
    """Brand and size written in each other's field: brand "600 G", size "Coop"."""
    if brand and pack and _ONLY_SIZE.match(brand.strip()) and not any(c.isdigit() for c in pack):
        return pack, brand
    return brand, pack


def counter_pack(name, pack):
    """Deli counter rows hold the rest of the name in the size field ("Kylling" / "Indisk Punjabi Varm pr Kg")."""
    name = _TRAILING_UNIT.sub('', name).strip() or name
    if not pack or _HAS_SIZE.search(pack):
        return name, pack
    rest = _SALES_UNIT.sub(' ', _TRAILING_UNIT.sub('', pack))
    rest = re.sub(r'\s+', ' ', rest).strip(' .,')
    if sum(c.isalpha() for c in rest) >= 3 and fam.fold(rest) not in fam.fold(name):
        name = '%s %s' % (name, rest)
    return name, None


def size_text(pack):
    """The size field as written, when no size could be read from it. None when it says nothing about size."""
    if not pack or not any(c.isdigit() for c in pack) or not any(c.isalpha() for c in pack) or _SALES_UNIT.search(pack):
        return None
    return None if _ONE_ITEM.match(pack.strip()) else pack


def percent_name(name, brand):
    """A name that is only a percentage needs its brand ("70%" from Marabou)."""
    if brand and '%' in name and not any(c.isalpha() for c in name):
        return '%s %s' % (brand, name)
    return name


def unusable(p):
    """Rows nobody in Norway can read or find: foreign scripts, and names that are only digits."""
    if _FOREIGN.search(p['name']) or (p['brand'] and _FOREIGN.search(p['brand'])):
        return True
    return not any(c.isalpha() for c in p['name'])


def impossible(p):
    """True when the main numbers per 100 cannot be true (kJ written as kcal, values per item or per pack)."""
    kcal = p['kcal']
    macros = [p[c] for c in ('protein_g', 'fat_g', 'carbs_g')]
    if kcal is not None and kcal > MAX_KCAL:
        return True
    if any(v is not None and v > MAX_MACRO for v in macros):
        return True
    if all(v is not None for v in macros) and sum(macros) > MAX_MACRO_SUM:
        return True
    if kcal == 0 and p['category'] not in _SUPPLEMENTS and not any(w in fam.fold(p['name']) for w in _SWEETENERS):
        protein, fat, carbs = ((v or 0) for v in macros)
        return 4 * protein + 4 * carbs + 9 * fat > 20
    return False


def _flag(flags, code):
    if code not in flags:
        flags.append(code)


def tidy_nutrients(p, flags):
    """A side value that cannot be true becomes unknown. The product stays."""
    for c in _SIDE:
        if p[c] is not None and p[c] > MAX_MACRO:
            p[c] = None
    if p['sugars_g'] is not None and p['carbs_g'] is not None and p['sugars_g'] > p['carbs_g'] + .5:
        p['sugars_g'] = None
        _flag(flags, 'sugars_exceed_carbs')
    if p['sat_fat_g'] is not None and p['fat_g'] is not None and p['sat_fat_g'] > p['fat_g'] + .5:
        p['sat_fat_g'] = None
        _flag(flags, 'sat_fat_exceeds_fat')
    if p['serving_g'] is not None and not 0 < p['serving_g'] <= 2000:
        p['serving_g'] = None


def _close(a, b):
    for c, floor in _CLOSE.items():
        x, y = a[c], b[c]
        if x is None or y is None:
            if c in _MACROS:
                return False
            continue
        if abs(x - y) > max(floor, .1 * max(x, y)):
            return False
    return True


def same_products(rows):
    """{folded id: kept id} for rows with one name, brand, flavour and unit and numbers within 10%. Rows come best first."""
    groups = collections.defaultdict(list)
    for p in rows:
        if p['brand']:
            groups[(' '.join(fam.words(p['name'])), _key(p['brand']), _key(p['flavour'] or ''), p.get('unit'))].append(p)
    folded = {}
    for key, members in groups.items():
        if not key[0]:
            continue
        keepers = []
        for p in members:
            home = next((k for k in keepers if _close(k, p)), None)
            if home:
                folded[p['id']] = home['id']
            else:
                keepers.append(p)
    return folded
