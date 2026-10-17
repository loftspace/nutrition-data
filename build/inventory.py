import sys, collections, json, time
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, 'C:/Users/Admin/Documents/Claude/zz-Misc/macro-library/build')
import adapters, nutr
un = collections.Counter(); tot = collections.Counter(); mapped = collections.Counter()
only = sys.argv[1:] 
for name, fn in adapters.SOURCES:
    if only and name not in only: continue
    t = time.time(); n = 0
    for c in fn():
        n += 1
        for side in ('per100', 'perserv'):
            for (label, val, unit, q, key) in c[side]:
                code, f, why = nutr.map_label(label, unit, key=key, source=c['source'])
                tot[c['source']] += 1
                if code is None:
                    if why != 'ignored':
                        un[(c['source'], (nutr.norm_label(label) or str(label)), nutr.norm_unit(unit), why)] += 1
                else:
                    mapped[c['source']] += 1
    print(name, n, round(time.time() - t, 1), flush=True)
for s in tot: print(s, tot[s], mapped[s], round(100 * mapped[s] / tot[s], 1))
byl = collections.Counter()
for (s, l, u, w), c in un.items(): byl[(l, u, w)] += c
print(sum(un.values()))
for (l, u, w), c in byl.most_common(int(sys.argv[0] and 400)): print(c, repr(l), u, w)
