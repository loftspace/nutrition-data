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
| `tools/load_sqlite.py` | Rebuilds `products.sqlite` (with full-text search) from the shards |
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

## Rebuilding
The scrapers and build scripts were run from a local working folder that also held the raw scraper output (about 1.4 GB, not in git). Paths inside the scripts point at that folder. All scrapers follow the rules in `COVERAGE.md`: honour robots.txt, one request per second per host, honest user agent, no CAPTCHA or login bypass, no images.

## Known limits
- Many supplement pages show one nutrition table for several flavours. We assume the flavours share nutrition (`flavour_nutrition_shared_assumed`).
- Roughly 20% of products have no nutrition data at all (listings without a table).
- Kassalapp is only partly covered, Kiwi, Oda, Rema 1000 and Coop are not.
- Categories come from a model. About 10,000 products with low confidence have `category_review = 1`.
