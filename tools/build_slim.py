"""Build the slim app database (products.sqlite) from the JSONL shards.

The slim database is what the iOS app bundles and what the web app downloads.
Contract: Maxaubert/Makro, packages/contracts/products-db.md.

Usage:
  python tools/build_slim.py --data data --out products.sqlite --db-version 2026.10.18 \
      [--variant full|open] [--previous old.sqlite] [--built-at ISO] [--source-commit SHA]

Needs only products-000 and product_eans-000 from the shards, so it runs on a
fresh Linux checkout. The raw scraper output is not needed.
"""
import argparse
import gzip
import json
import os
import sqlite3
import sys
import unicodedata

SCHEMA_VERSION = 1

# Sources whose licences allow republishing (LICENSES.md, "open sources").
# The open variant keeps a product only if its primary source is in this set,
# because the numbers shown for a product come from its primary source.
OPEN_SOURCES = (
    'openfoodfacts',
    'openfoodfacts-nordic-global',
    'usda-fdc',
    'matvaretabellen',
    'frida-dk',
    'livsmedelsverket',
)

_LETTERS = {'ø': 'o', 'æ': 'ae', 'å': 'a', 'ä': 'a', 'ö': 'o', 'ü': 'u', 'ß': 'ss'}


def normalise(text):
    """Search normalisation. The app and the web app apply the same rule to the query.

    Lowercase, then ø->o, æ->ae, å->a (also ä, ö, ü, ß), then strip any other accents.
    """
    if not text:
        return ''
    text = text.lower()
    for k, v in _LETTERS.items():
        text = text.replace(k, v)
    text = unicodedata.normalize('NFKD', text)
    return ''.join(ch for ch in text if not unicodedata.combining(ch))


PRODUCT_COLUMNS = (
    'id', 'name', 'brand', 'pack_size', 'ean', 'flavour', 'category', 'serving_g',
    'source', 'status', 'data_quality',
    'kcal', 'protein_g', 'fat_g', 'sat_fat_g', 'carbs_g', 'sugars_g', 'fibre_g', 'salt_g',
)
# slim column -> shard column (only `source` is renamed)
_SHARD_NAME = {'source': 'primary_source'}


def read_shard(data_dir, manifest, table):
    info = manifest[table]
    cols = info['columns']
    for fn in info['files']:
        with gzip.open(os.path.join(data_dir, fn), 'rt', encoding='utf-8') as f:
            f.readline()  # header line with the column names
            for line in f:
                yield dict(zip(cols, json.loads(line)))


def build(data_dir, out, db_version, variant='full', previous=None, built_at='', source_commit=''):
    if variant not in ('full', 'open'):
        raise ValueError('variant must be full or open')
    with open(os.path.join(data_dir, 'manifest.json'), encoding='utf-8') as f:
        manifest = json.load(f)

    kept = {}
    merged = {}  # old id -> id it was merged into
    for p in read_shard(data_dir, manifest, 'products'):
        if p['merged_into']:
            merged[p['id']] = p['merged_into']
            continue
        if not p['norway_relevant'] or p['hidden']:
            continue
        if not (p['name'] or '').strip():
            continue
        if variant == 'open' and p['primary_source'] not in OPEN_SOURCES:
            continue
        kept[p['id']] = p

    if os.path.exists(out):
        os.remove(out)
    db = sqlite3.connect(out)
    db.executescript("""
create table products(
  id text primary key,
  name text not null,
  brand text,
  pack_size text,
  ean text,
  flavour text,
  category text,
  serving_g real,
  source text not null,
  status text,
  data_quality text,
  kcal real, protein_g real, fat_g real, sat_fat_g real, carbs_g real, sugars_g real, fibre_g real, salt_g real,
  search_text text not null
);
create table product_eans(product_id text not null, ean text not null);
create table redirects(old_id text primary key, new_id text not null);
create table removed(id text primary key);
create table meta(key text primary key, value text not null);
""")
    rows = []
    for p in kept.values():
        vals = [p[_SHARD_NAME.get(c, c)] for c in PRODUCT_COLUMNS]
        search = normalise(' '.join(x for x in (p['name'], p['brand'], p['flavour']) if x))
        rows.append(vals + [search])
    db.executemany('insert into products values (%s)' % ','.join('?' * (len(PRODUCT_COLUMNS) + 1)), rows)

    eans = [(e['product_id'], e['ean']) for e in read_shard(data_dir, manifest, 'product_eans')
            if e['product_id'] in kept and e['ean']]
    db.executemany('insert into product_eans values (?, ?)', eans)

    # Merged products: old id -> final kept id. Targets that are not in this database are dropped.
    redirects = {}
    for old, new in merged.items():
        seen = {old}
        while new in merged and new not in seen:
            seen.add(new)
            new = merged[new]
        if new in kept:
            redirects[old] = new

    # Ids that were in the previous release and are gone now, with no successor: record them,
    # so an old favourite or log entry can tell "gone" from "unknown id".
    removed = set()
    if previous:
        prev = sqlite3.connect(previous)
        try:
            old_ids = {r[0] for r in prev.execute('select id from products')}
            old_ids |= {r[0] for r in prev.execute('select old_id from redirects')}
            old_ids |= {r[0] for r in prev.execute('select id from removed')}
        finally:
            prev.close()
        for oid in old_ids:
            if oid not in kept and oid not in redirects:
                removed.add(oid)
    db.executemany('insert into redirects values (?, ?)', sorted(redirects.items()))
    db.executemany('insert into removed values (?)', [(i,) for i in sorted(removed)])

    db.executescript("""
create index ix_products_ean on products(ean);
create index ix_product_eans_ean on product_eans(ean);
create virtual table products_fts using fts5(
  search_text, content='products', content_rowid='rowid', tokenize='unicode61', prefix='2 3');
insert into products_fts(rowid, search_text) select rowid, search_text from products;
insert into products_fts(products_fts) values('optimize');
""")
    meta = {
        'db_version': db_version,
        'schema_version': str(SCHEMA_VERSION),
        'variant': variant,
        'product_count': str(len(kept)),
        'built_at': built_at,
        'source_commit': source_commit,
    }
    if variant == 'open':
        meta['open_sources'] = ','.join(OPEN_SOURCES)
    db.executemany('insert into meta values (?, ?)', sorted(meta.items()))
    db.execute('pragma user_version = %d' % SCHEMA_VERSION)
    db.commit()
    db.execute('vacuum')
    db.close()
    return len(kept)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--data', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--db-version', required=True)
    ap.add_argument('--variant', default='full', choices=('full', 'open'))
    ap.add_argument('--previous')
    ap.add_argument('--built-at', default='')
    ap.add_argument('--source-commit', default='')
    a = ap.parse_args(argv)
    n = build(a.data, a.out, a.db_version, a.variant, a.previous, a.built_at, a.source_commit)
    print('%s: %d products, %.1f MB' % (a.out, n, os.path.getsize(a.out) / 1e6))


if __name__ == '__main__':
    sys.exit(main())
