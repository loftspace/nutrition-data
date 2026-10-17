"""Export products.sqlite as gzip JSONL shards (each well under GitHub's 100 MB file limit) plus schema.sql, into <target>/data/.
Usage: python -I build/export_repo.py <target repo dir>
Reload with tools/load_sqlite.py in the repo."""
import gzip, json, os, sqlite3, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = ROOT + '/data/unified/products.sqlite'
SHARD_BYTES = 180 * 1024 * 1024   # uncompressed bytes per shard; gzip makes it about 15 to 30 MB
TABLES = [('nutrient_dictionary', None), ('products', 'id'), ('product_eans', None), ('product_sources', None), ('nutrients', None)]


def main(target):
    out = os.path.join(target, 'data')
    os.makedirs(out, exist_ok=True)
    for f in os.listdir(out):
        if f.endswith('.jsonl.gz') or f == 'schema.sql':
            os.remove(os.path.join(out, f))
    c = sqlite3.connect('file:%s?mode=ro' % DB, uri=True)
    schema = [s for (s,) in c.execute("select sql from sqlite_master where type in ('table','index') and name not like 'products_fts%' and name!='sqlite_stat1' and sql is not null")]
    open(os.path.join(out, 'schema.sql'), 'w', encoding='utf-8').write(';\n\n'.join(schema) + ';\n')
    manifest = {}
    for t, order in TABLES:
        cols = [r[1] for r in c.execute('pragma table_info(%s)' % t)]
        cur = c.execute('select * from %s%s' % (t, ' order by ' + order if order else ''))
        shard, size, n, files = 0, 0, 0, []
        f = None

        def open_shard():
            name = '%s-%03d.jsonl.gz' % (t, shard)
            files.append(name)
            return gzip.open(os.path.join(out, name), 'wt', encoding='utf-8', compresslevel=9)
        f = open_shard()
        f.write(json.dumps({'columns': cols}) + '\n')
        for row in cur:
            line = json.dumps(list(row), ensure_ascii=False, separators=(',', ':')) + '\n'
            f.write(line); size += len(line); n += 1
            if size >= SHARD_BYTES:
                f.close(); shard += 1; size = 0
                f = open_shard()
                f.write(json.dumps({'columns': cols}) + '\n')
        f.close()
        manifest[t] = {'rows': n, 'files': files, 'columns': cols}
        print(t, n, files, flush=True)
    json.dump(manifest, open(os.path.join(out, 'manifest.json'), 'w'), indent=1)
    tot = sum(os.path.getsize(os.path.join(out, f)) for f in os.listdir(out))
    print('data folder MB:', round(tot / 1e6, 1), 'largest file MB:', round(max(os.path.getsize(os.path.join(out, f)) for f in os.listdir(out)) / 1e6, 1))


if __name__ == '__main__':
    main(sys.argv[1])
