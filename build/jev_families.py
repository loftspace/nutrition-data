"""Check candidate flavour families with Jev, then write data/families.json for the slim build.
Approved by Max on 2026-11-08: one batch of up to 2,689 calls (one per candidate family whose names differ).

Usage:  python -I tools/families.py --data data --out data/jev/families_candidates.json
        python -I build/jev_families.py run        # Jev calls (resumes), data/jev/families.jsonl
        python -I build/jev_families.py write      # data/families.json from candidates + answers

Sends per family: each member's name, brand and per-100 kcal and protein (at most 40 members).
Key from env TYPESAFE_API_KEY, never printed. A family Jev rejects is split into its members
whose names differ only by size or case (the same product from several shops), which need no check.
"""
import json, os, sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT + '/tools')
sys.path.insert(0, ROOT + '/build')
import families as fam  # noqa: E402

CANDIDATES = ROOT + '/data/jev/families_candidates.json'
ANSWERS = ROOT + '/data/jev/families.jsonl'
OUT = ROOT + '/data/families.json'
ACCEPT = 0.6

Q = {'same_product': {'type': 'noul', 'instructions': (
    'These listings already have nearly identical nutrition per 100 g. Are they one product line sold in different '
    'flavours, pack sizes, multipacks or shops (for example "YT Proteinpudding Mango" and "YT Proteinpudding Vanilje", '
    'or "Barebells Protein Bar Caramel" and "Barebells Protein Bar Cookies")? Different flavours count as yes. '
    'Answer no only if a listing is a different kind of food or a separate line within the brand, such as zero, '
    'light, lactose-free, organic versus regular, or a different brand.')}}


def state_for(members):
    return {'listings': [{k: v for k, v in (('name', m['name'][:150]), ('brand', m['brand']),
                                            ('kcal_per_100', m['kcal']), ('protein_per_100', m['protein_g'])) if v is not None}
                         for m in members[:40]]}


def load_answers():
    """Jev answers keyed by the exact set of listings asked about."""
    out = {}
    if os.path.exists(ANSWERS):
        for l in open(ANSWERS, encoding='utf-8'):
            r = json.loads(l)
            out[frozenset(r['members'])] = r['same_product']
    return out


def lookup(answered, members):
    """Jev's answer for this exact set, or the answer of an accepted family that contains it; else None."""
    m = frozenset(members)
    if m in answered:
        return answered[m]
    hits = [p for s, p in answered.items() if p >= ACCEPT and m <= s]
    return max(hits) if hits else None


def run():
    import jev_categorize as jc
    if not jc.KEY:
        sys.exit('TYPESAFE_API_KEY not set')
    rows = {r['id']: r for r in fam.load_rows(ROOT + '/data')}
    cands = [c for c in json.load(open(CANDIDATES, encoding='utf-8')) if c['needs_check']]
    answered = load_answers()
    todo = [c for c in cands if lookup(answered, c['members']) is None]
    print('to do', len(todo), 'already answered', len(answered), flush=True)
    from concurrent.futures import ThreadPoolExecutor
    f = open(ANSWERS, 'a', encoding='utf-8')

    def work(c):
        d = jc.call(state_for([rows[i] for i in c['members']]), Q)
        if 'answers' not in d:
            return
        rec = {'key': c['members'][0], 'members': c['members'], 'same_product': round(d['answers']['same_product'].get('noul', 0), 3)}
        with jc.lock:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
            f.flush()

    with ThreadPoolExecutor(jc.WORKERS) as ex:
        list(ex.map(work, todo))
    f.close()
    print('finished', dict(jc.usage), flush=True)


def write():
    rows = {r['id']: r for r in fam.load_rows(ROOT + '/data')}
    lines = fam.Lines(list(rows.values()))
    answered = load_answers()
    out, missing, rejected = [], 0, 0
    for c in json.load(open(CANDIDATES, encoding='utf-8')):
        m = c['members']
        if not c['needs_check']:
            out.append({'members': m, 'jev': None})
            continue
        p = lookup(answered, m)
        if p is None:
            missing += 1
        if p is not None and p >= ACCEPT:
            out.append({'members': m, 'jev': p})
            continue
        rejected += p is not None
        # Not accepted: keep only the plain duplicates (same words in any order, brand and size aside).
        by_name = defaultdict(list)
        for i in m:
            by_name[lines.core(rows[i]['name'], rows[i]['brand'])].append(i)
        out.extend({'members': g, 'jev': None} for g in by_name.values() if len(g) > 1)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump({'rule': 'tools/families.py, Jev accept >= %.1f' % ACCEPT, 'families': out}, f, ensure_ascii=False, indent=0)
    print('%d families, %d products, %d rejected by Jev, %d without an answer' % (
        len(out), sum(len(x['members']) for x in out), rejected, missing))


if __name__ == '__main__':
    {'run': run, 'write': write}[sys.argv[1]]()
