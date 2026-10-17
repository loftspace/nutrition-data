"""Parsing helpers for tights.no product descriptions (HTML tables with Norwegian nutrient labels)."""
import re, html
from bs4 import BeautifulSoup

NUM = r'<?\s*[\d]+(?:[.,]\d+)?'
VAL_RE = re.compile(r'(?P<lt>[<≤]|(?:ca\.?|~)\s*)?\s*(?P<num>\d+(?:[.,]\d+)?)\s*(?P<unit>kcal|kJ|mcg|µg|μg|ug|mg|g|ml|IE|IU|%|NE|RE|TE|CFU|mikrogram)?', re.I)

LABELS = [  # (key, regex on lowercased label)
    ('energy', r'^(energi|energy|kalorier|energiinnhold)\b'),
    ('saturated_fat', r'(mettet|mettede|saturated)'),
    ('mono_fat', r'(enumettet|monounsaturated|enumettede)'),
    ('poly_fat', r'(flerumettet|polyunsaturated|flerumettede)'),
    ('fat', r'^(fett|fat|total fat)\b'),
    ('sugars', r'(sukkerarter|sukker\b|sugars?)'),
    ('polyols', r'(polyol|sukkeralkohol)'),
    ('starch', r'(stivelse|starch)'),
    ('carbs', r'^(karbohydrat|carbohydrate|karbo)'),
    ('fibre', r'(kostfiber|fiber|fibre)'),
    ('protein', r'^(protein|proteiner)\b'),
    ('salt', r'^(salt|salz)\b'),
    ('sodium', r'^(natrium|sodium)\b'),
]


def parse_value(s):
    """Parse a cell like '1511 kJ / 363 kcal', '<0,5 g', '0,4 mg (50 %)' -> list of dicts."""
    s = html.unescape(s).replace('\xa0', ' ').strip()
    out = []
    # strip trailing (xx % NRV) parenthesis, keep as nrv
    nrv = None
    m = re.search(r'\(\s*(\d+(?:[.,]\d+)?)\s*%[^)]*\)', s)
    if m:
        nrv = float(m.group(1).replace(',', '.'))
        s = (s[:m.start()] + s[m.end():]).strip()
    for m in VAL_RE.finditer(s):
        num = float(m.group('num').replace(',', '.'))
        unit = m.group('unit')
        if unit:
            unit = {'µg': 'ug', 'μg': 'ug', 'mcg': 'ug', 'mikrogram': 'ug'}.get(unit.lower(), unit)
            unit = 'kJ' if unit.lower() == 'kj' else ('kcal' if unit.lower() == 'kcal' else unit)
        out.append({'value': num, 'unit': unit, 'lt': bool(m.group('lt') and '<' in m.group('lt')) or None,
                    'approx': bool(m.group('lt') and not '<' in m.group('lt')) or None})
    if nrv is not None and out:
        out[0]['nrv_pct'] = nrv
    return out


def classify(label):
    l = label.lower().strip(' -–—·•\xa0:')
    l = re.sub(r'^(herav|hvorav|of which|-)\s*', '', l)
    for k, rx in LABELS:
        if re.search(rx, l):
            return k
    return None


def col_kind(h):
    h = h.lower()
    if re.search(r'(%|ri\b|nrv|referanse|rdi|dagsbehov|anbefalt dagsdose|\bad\b|\bnri\b)', h) and not re.search(r'100\s*g|porsjon|serving', h):
        return 'pct'
    if re.search(r'100\s*(g|ml)', h):
        return 'per100'
    if re.search(r'(porsjon|serving|dose|kapsel|tablett|scoop|skje|\bstk|bar\b|pose|dosering)', h):
        return 'serving'
    if re.search(r'(ferdig|tilberedt|prepared)', h):
        return 'prepared'
    return 'other'


def serving_size(h):
    m = re.search(r'\(?\s*(?:ca\.?\s*)?(\d+(?:[.,]\d+)?)\s*(g|ml)\b', h, re.I)
    if m:
        return {'size': float(m.group(1).replace(',', '.')), 'unit': m.group(2).lower(), 'label': h.strip()}
    return {'label': h.strip()}


def parse_tables(content_html):
    soup = BeautifulSoup(content_html, 'html.parser')
    tables = []
    for t in soup.find_all('table'):
        rows = []
        for tr in t.find_all('tr'):
            cells = [re.sub(r'\s+', ' ', c.get_text(' ', strip=True).replace('\xa0', ' ')).strip() for c in tr.find_all(['th', 'td'])]
            # some cells hold several lines separated by <br> (label cell and value cell in lockstep)
            multi = [[re.sub(r'\s+', ' ', x.replace('\xa0', ' ')).strip() for x in c.get_text('\n').split('\n') if x.strip()] for c in tr.find_all(['th', 'td'])]
            rows.append((cells, multi))
        if rows:
            tables.append(rows)
    return tables


def interpret_table(rows):
    """Return dict with columns and nutrients, or None if it does not look like a nutrient table."""
    # header detection: first row whose label cell looks like header and later cells contain 'per'/'100'
    hdr = None
    start = 0
    for i, (cells, _) in enumerate(rows[:3]):
        if len(cells) >= 2 and any(re.search(r'100\s*(g|ml)|porsjon|serving|per\b|dose|%', c, re.I) for c in cells[1:]) \
                and not any(re.search(r'\d+(?:[.,]\d+)?\s*(kcal|kj|mg|g)\b', c, re.I) and not re.search(r'porsjon|serving|per', c, re.I) for c in cells[1:]):
            hdr = cells
            start = i + 1
            break
    if hdr is None:
        hdr = [''] + ['per 100 g'] * (max(len(r[0]) for r in rows) - 1)  # headerless: assume per 100 g (flagged)
        assumed = True
    else:
        assumed = False
    kinds = [col_kind(h) for h in hdr[1:]]
    nutrients = []
    for cells, multi in rows[start:]:
        if len(cells) < 2:
            continue
        labels = multi[0] if multi and multi[0] else [cells[0]]
        # lockstep multi-line cells
        nvals = [m for m in multi[1:]]
        for li, lab in enumerate(labels):
            vals = []
            for ci, m in enumerate(nvals):
                if len(m) == len(labels):
                    vals.append(m[li])
                elif len(labels) == 1:
                    vals.append(' '.join(m))
                else:
                    vals.append(m[li] if li < len(m) else '')
            rec = {'label': lab, 'key': classify(lab), 'raw': vals, 'cols': {}}
            for ci, v in enumerate(vals):
                kind = kinds[ci] if ci < len(kinds) else 'other'
                pv = parse_value(v) if v else []
                if pv:
                    rec['cols'].setdefault(kind, pv)
            if rec['cols'] or lab:
                nutrients.append(rec)
    return {'header': hdr, 'col_kinds': kinds, 'headerless_assumed_per100': assumed, 'rows': nutrients,
            'serving': next((serving_size(h) for h, k in zip(hdr[1:], kinds) if k == 'serving'), None)}


def looks_nutritional(interp):
    keys = {r['key'] for r in interp['rows'] if r['key']}
    return len(keys & {'energy', 'protein', 'fat', 'carbs', 'fibre', 'salt'}) >= 3 or ('protein' in keys and len(keys) >= 2) or ('energy' in keys and len(keys) >= 2)


def pick(rows, key, kind):
    for r in rows:
        if r['key'] == key and kind in r['cols']:
            return r['cols'][kind]
    return None


def flatten(interp, kind):
    """Standard macros from a given column kind, values in g (kcal for energy)."""
    out = {}
    for r in interp['rows']:
        k = r['key']
        pv = r['cols'].get(kind)
        if not k or not pv or k in out:
            continue
        if k == 'energy':
            kc = next((x for x in pv if x['unit'] == 'kcal'), None)
            kj = next((x for x in pv if x['unit'] == 'kJ'), None)
            if kc: out['kcal'] = kc['value']
            if kj: out['kj'] = kj['value']
            continue
        x = pv[0]
        v = x['value']
        u = (x['unit'] or 'g')
        if u == 'mg': v /= 1000.0
        elif u == 'ug': v /= 1e6
        elif u not in ('g',): continue
        out[k] = round(v, 6)
        if x.get('lt'): out[k + '_lt'] = True
    return out
