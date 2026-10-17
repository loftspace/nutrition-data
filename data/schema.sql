CREATE TABLE nutrient_dictionary(code TEXT PRIMARY KEY, unit TEXT, grp TEXT, name_en TEXT, name_nb TEXT, aliases TEXT);

CREATE TABLE products(
  id TEXT PRIMARY KEY, name TEXT, brand TEXT, pack_size TEXT, ean TEXT, kind TEXT, flavour TEXT, categories TEXT, ingredients TEXT, allergens TEXT,
  serving_g REAL, primary_source TEXT, n_sources INTEGER, status TEXT, data_quality TEXT,
  region TEXT, regions TEXT, norway_relevant INTEGER, discontinued INTEGER, all_eans TEXT,
  kcal REAL, protein_g REAL, fat_g REAL, sat_fat_g REAL, carbs_g REAL, sugars_g REAL, fibre_g REAL, salt_g REAL, kj REAL, category TEXT, category_conf REAL, category_review INTEGER, is_supplement INTEGER, ingredient_group TEXT, merged_into TEXT, hidden INTEGER);

CREATE TABLE product_sources(
  product_id TEXT, source TEXT, source_id TEXT, url TEXT, fetched_on TEXT, is_primary INTEGER, kind TEXT, name TEXT, brand TEXT,
  region TEXT, norway_relevant INTEGER, page_gone INTEGER,
  kcal REAL, protein_g REAL, fat_g REAL, carbs_g REAL, per_100g_json TEXT, flags TEXT);

CREATE TABLE product_eans(product_id TEXT, ean TEXT);

CREATE TABLE nutrients(product_id TEXT, basis TEXT, code TEXT, value REAL, unit TEXT, qualifier TEXT, source TEXT);

CREATE INDEX ix_products_ean ON products(ean);

CREATE INDEX ix_products_region ON products(region, norway_relevant);

CREATE INDEX ix_pe_ean ON product_eans(ean);

CREATE INDEX ix_pe_product ON product_eans(product_id);

CREATE INDEX ix_products_brand ON products(brand);

CREATE INDEX ix_products_kind ON products(kind);

CREATE INDEX ix_products_src ON products(primary_source);

CREATE INDEX ix_ps_product ON product_sources(product_id);

CREATE INDEX ix_ps_source ON product_sources(source);

CREATE INDEX ix_nut_product ON nutrients(product_id);

CREATE INDEX ix_nut_code ON nutrients(code, basis, value);

CREATE INDEX ix_products_category on products(category, norway_relevant, hidden);
