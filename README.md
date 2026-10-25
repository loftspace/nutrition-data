# nutrition-data

Food and supplement nutrition database for the Norwegian market, built for the Makro training and macro-tracking app (Max and Nima).

**Private repo.** Contains data scraped from shops and brand sites for personal and internal research. Do not publish the data or ship it in a public app until the licence question in `LICENSES.md` is settled.

## What is in it
About 186,000 products from 90+ sources, merged by barcode (EAN). 126,000 of them are Norway-relevant: sold in Norway, or in a Nordic, EU or UK shop that ships to Norway.

- Per-100 g macros (kcal, protein, fat, saturated fat, carbs, sugars, fibre, salt) and, where a source has them, vitamins, minerals, amino acids and fatty acids (192 nutrient codes).
- Barcodes, brand, pack size, flavour, ingredients, allergens, source URLs, discontinued flag.
- A food or supplement category for every Norway-relevant product (22 categories, assigned with Jev). Supplements include protein powder, bars, creatine, pre-workout, vitamins, amino acids and more.
- Every product keeps all its source entries, so disagreements between sources stay visible (`data_quality` flags tell you what to trust).
- Plain single-ingredient supplements (creatine monohydrate, beta-alanine, citrulline, glutamine, taurine, caffeine) are folded into one canonical `generic:` product each. The originals stay in the data, with `merged_into` set and `hidden = 1`.

See `COVERAGE.md` for exact counts per source, completeness, known gaps and quality flags.

## Layout
| Path | What |
|---|---|
| `data/*.jsonl.gz` | The database as compressed JSONL shards, one table per file group |
| `data/schema.sql`, `data/manifest.json` | Table definitions and row counts |
| `tools/load_sqlite.py` | Rebuilds the full 645 MB `products.sqlite` (with full-text search) from the shards |
| `tools/build_slim.py` | Builds the slim app database (full or open-sources-only variant) from the shards |
| `.github/workflows/` | `ci.yml` tests the builder; `release-db.yml` publishes a private release |
| `scrapers/` | One Python scraper per source |
| `build/` | Merge, nutrient dictionary, Jev categorization, post-processing, export |
| `data/jev/` | Raw Jev answers (category, confidence) for provenance |
| `LICENSES.md` | Source licences and what we may do with each |
| `COVERAGE.md` | Coverage report |

## Use it
```
python tools/load_sqlite.py data products.sqlite
sqlite3 products.sqlite "select name, brand, kcal, protein_g from products where category='protein_bar' and hidden=0 order by protein_g desc limit 10"
```

Search uses FTS5: `select name from products where rowid in (select rowid from products_fts where products_fts match 'barebells')`.

## The slim app database
`tools/build_slim.py` builds what the Makro iOS app bundles and the web app downloads: visible Norway-relevant food products (no `non_food`) with the macros only, an FTS5 search column normalised for Norwegian (ø to o, æ to ae, å to a), all barcodes in canonical form, and a redirect table so old product ids keep resolving. Contract: `packages/contracts/products-db.md` in `Maxaubert/Makro` (v1, `schema_version` 2).

| Variant | Products | Size | Sources |
|---|---|---|---|
| full | 116,033 | 43.8 MB (11.9 MB gzipped) | everything |
| open | 44,668 | 15.8 MB (4.8 MB gzipped) | only the open sources in `LICENSES.md` |

Measured on 2026-10-25. What the builder decides (all in `build_slim.py`):
- **Barcodes**: `canonical_ean` (digits only, pad to 13, drop the leading 0 of a 14-digit code). The build fails if two products share a canonical barcode. Golden cases: `tools/testdata/barcode.json`, a copy of Makro's `packages/contracts/search/barcode.json`.
- **`per_100_unit`**: `ml` when the pack size (or, failing that, a pack size written in the name) is in ml, cl, dl or l, otherwise `g`. Never from the category. The shards have no per-100 basis field, so this is the best signal there is.
- **`sources`**: `SOURCES` maps every source slug to a display name and a kind. A new source needs a line there or the build fails. A multi-brand shop is `shop` and is never verified.
- **`data_quality`**: a closed code list (`SUSPECT_FLAGS`, `INFO_FLAGS`, `filled_from_*`). An unknown code fails the build.
- **Zero kcal**: when kcal, protein, fat and carbs are all 0, the values become NULL and `no_nutrition` is added, unless the name says water, a sweetener or salt, or the product is a curated pure compound. The test fails if more than `MAX_ALL_ZERO` all-zero products remain (259 on 2026-10-25, from 1,198).
- **Open variant**: values that came from a non-open source (per the `nutrients` shard) are set to NULL, and their `filled_from_*` flags are dropped.

```
python tools/build_slim.py --data data --out products.sqlite --db-version 2026.10.18 --variant full
python -m unittest discover -s tools -v
```
Publish a release from the Actions tab: run `release-db` with a version like `2026.10.18`. It attaches both files and `checksums.txt` (sha256) to a private release. It builds each variant with `--previous` set to that variant's file in the latest release, so ids that vanished are listed in `removed`.

## Rebuilding
The scrapers and build scripts were run from a local working folder that also held the raw scraper output (about 1.4 GB, not in git). Paths inside the scripts point at that folder. All scrapers follow the rules in `COVERAGE.md`: honour robots.txt, one request per second per host, honest user agent, no CAPTCHA or login bypass, no images.

## Known limits
- Many supplement pages show one nutrition table for several flavours. We assume the flavours share nutrition (`flavour_nutrition_shared_assumed`).
- Roughly 20% of products have no nutrition data at all (listings without a table).
- Kassalapp is only partly covered, Kiwi, Oda, Rema 1000 and Coop are not.
- Categories come from a model. All ~10,300 low-confidence products were re-checked by Haiku agents. About 1,600 answers were still uncertain and keep `category_review = 1`.
