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


def run():
    import jev_categorize as jc
    if not jc.KEY:
        sys.exit('TYPESAFE_API_KEY not set')
    rows = {r['id']: r for r in fam.load_rows(ROOT + '/data')}
    cands = [c for c in json.load(open(CANDIDATES, encoding='utf-8')) if c['needs_check']]
    done = set()
    if os.path.exists(ANSWERS):
        done = {json.loads(l)['key'] for l in open(ANSWERS, encoding='utf-8')}
    todo = [c for c in cands if c['members'][0] not in done]
    print('to do', len(todo), 'already', len(done), flush=True)
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
    answers, approved = {}, {}
    if os.path.exists(ANSWERS):
        for l in open(ANSWERS, encoding='utf-8'):
            r = json.loads(l)
            answers[r['key']] = r['same_product']
            if r['same_product'] >= ACCEPT:
                for i in r['members']:
                    approved[i] = (frozenset(r['members']), r['same_product'])
    out, missing, rejected = [], 0, 0
    for c in json.load(open(CANDIDATES, encoding='utf-8')):
        m = c['members']
        if not c['needs_check']:
            out.append({'members': m, 'jev': None})
            continue
        p = answers.get(m[0])
        if p is None and m[0] in approved and set(m) <= approved[m[0]][0]:
            p = approved[m[0]][1]  # part of a family Jev already accepted
        if p is None:
            missing += 1
        if p is not None and p >= ACCEPT:
            out.append({'members': m, 'jev': p})
            continue
        rejected += p is not None
        # Not accepted: keep only the plain duplicates (same name apart from size or case).
        by_name = defaultdict(list)
        for i in m:
            by_name[' '.join(fam.words(rows[i]['name']))].append(i)
        out.extend({'members': g, 'jev': None} for g in by_name.values() if len(g) > 1)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump({'rule': 'tools/families.py, Jev accept >= %.1f' % ACCEPT, 'families': out}, f, ensure_ascii=False, indent=0)
    print('%d families, %d products, %d rejected by Jev, %d without an answer' % (
        len(out), sum(len(x['members']) for x in out), rejected, missing))


if __name__ == '__main__':
    {'run': run, 'write': write}[sys.argv[1]]()
