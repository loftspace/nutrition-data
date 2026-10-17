"""Rebuild products.sqlite (with FTS5 search) from the JSONL shards.
Usage: python tools/load_sqlite.py <data dir> <output.sqlite>"""
import gzip, json, os, sqlite3, sys

data, out = sys.argv[1], sys.argv[2]
manifest = json.load(open(os.path.join(data, 'manifest.json'), encoding='utf-8'))
if os.path.exists(out):
    os.remove(out)
c = sqlite3.connect(out)
c.executescript(open(os.path.join(data, 'schema.sql'), encoding='utf-8').read())
for table, info in manifest.items():
    cols = info['columns']
    sql = 'insert into %s(%s) values(%s)' % (table, ','.join(cols), ','.join('?' * len(cols)))
    for fn in info['files']:
        with gzip.open(os.path.join(data, fn), 'rt', encoding='utf-8') as f:
            f.readline()   # header line with the column names
            batch = []
            for line in f:
                batch.append(json.loads(line))
                if len(batch) >= 50000:
                    c.executemany(sql, batch); batch = []
            if batch:
                c.executemany(sql, batch)
    print(table, info['rows'], flush=True)
c.executescript("""
CREATE VIRTUAL TABLE products_fts USING fts5(name, brand, flavour, categories, content='products', content_rowid='rowid', tokenize='unicode61 remove_diacritics 2');
INSERT INTO products_fts(rowid, name, brand, flavour, categories) SELECT rowid, name, brand, flavour, categories FROM products;
INSERT INTO products_fts(products_fts) VALUES('optimize');
""")
c.commit()
print('done', out)
