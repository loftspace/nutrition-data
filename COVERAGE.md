# Macro library coverage

Built 2026-10-16 by `build/build.py` + `build/coverage.py`. Personal use only (ODbL / CC BY / USDA CC0 / store data: see `data/raw/*/LICENSE-NOTE.txt`).

Everything is **from_source**: values are what the sources published. Nothing is estimated, except three labelled derivations (`kcal` from kJ / 4.184, `salt_g` from sodium x 2.5, `sodium_mg` from salt x 400), which are marked in `field_provenance` as `derived`.

## Totals

| What | Count |
|---|---:|
| Raw records read (after dropping non-food without nutrition) | 251797 |
| **Unified products** | **186062** (first pass: 85553) |
| **Norway-relevant products** (a Norwegian source, or a Nordic / EU / UK online shop Max can buy from) | **126282** |
| Norway-relevant products with full macros (kcal + protein + fat + carbs) | 82255 |
| Norway-relevant, full macros, EAN and not discontinued | 68833 |
| Discontinued products (every source page gone) | 5494 |
| Products with more than one EAN (flavours / sizes of one page answer to all of them) | 954 |
| Duplicate source records merged into an existing product (same EAN) | 65735 |
| Products with an EAN (valid GTIN checksum) | 143162 |
| Products with several source entries | 26207 |
| Product source entries (product_sources rows) | 251797 |
| Nutrient codes defined / used | 192 / 187 |
| Distinct raw labels left unmapped (in `unmapped.json`) | 18565 (91333 occurrences) |
| Nutrient rows (long table) | 2543035 |

Records dropped before the merge (counted per source in the food vs non-food table below): norgesgruppen 10787, bodystore-se 2358, proteinfabrikken-discontinued 1002, bodystore-discontinued 996, halsokostbolaget 990, ica-se 421, bodystore 192, sportylab-no 152, helsekost-no 127, bodystore-dk 90, bodylab-no 82, scitec 71 ... Non-food = name or category says clothing, gear, shaker, cosmetics, pet food or household, AND the record has no nutrition. Nemlig all-zero placeholder rows are dropped too. Samples of every drop reason are in `stats.json` (`drop_samples`).

## Counts per source, before and after

`raw` is the number of records the collector saved, `read` what went into the merge (after dropping non-food without nutrition; variant rows of one page are collapsed to one candidate), `entries` the number of source entries kept in product_sources, `primary` how many products use this source as their primary (priority: pack label = producer or store page > Kassalapp > NorgesGruppen > Open Food Facts > USDA branded > generic tables; a live page beats a gone page; only a source that has kcal can win over one that has none). kcal/protein/fat/carbs/fibre/salt are counted over source entries with a per-100 g value. `entries before` is the first-pass build (85,553 products), `new` is entries now minus before. The first-pass folders of tights, gymgrossisten, bodystore, proteinfabrikken and bulk are replaced by their `-v2` folders (same shop, name kept).

| Source | region | NO-relevant | raw | read | entries | entries before | new | primary | kcal | protein | fat | carbs | fibre | salt | EAN | gone |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| openfoodfacts-nordic-global | mixed | yes | 68329 | 68329 | 68329 | 0 | +68329 | 65704 | 55333 | 54607 | 54396 | 54708 | 28146 | 47676 | 67143 | 0 |
| usda-fdc | US | no | 0 | 45310 | 45310 | 45310 | +0 | 16013 | 41637 | 41943 | 41594 | 41877 | 35469 | 41599 | 36745 | 0 |
| norgesgruppen | NO | yes | 39229 | 28442 | 28442 | 28442 | +0 | 25995 | 24171 | 24105 | 24099 | 24134 | 12500 | 24067 | 23321 | 0 |
| openfoodfacts | NO | yes | 27445 | 27445 | 27445 | 27445 | +0 | 18184 | 19490 | 19206 | 19175 | 19229 | 7842 | 15807 | 27160 | 0 |
| tights | NO | yes | 7584 | 7581 | 7581 | 7713 | -132 | 6859 | 2220 | 2404 | 2365 | 2345 | 1454 | 2369 | 5346 | 0 |
| kassalapp | NO | yes | 5994 | 5994 | 5994 | 856 | +5138 | 5350 | 5165 | 5160 | 5157 | 5155 | 2943 | 5160 | 4614 | 0 |
| ica-se | SE | yes | 5061 | 4640 | 4640 | 0 | +4640 | 4345 | 835 | 834 | 837 | 820 | 364 | 809 | 4640 | 0 |
| helsekost-no | NO | yes | 4637 | 4510 | 4510 | 0 | +4510 | 3393 | 2026 | 1984 | 1983 | 2001 | 462 | 1950 | 4452 | 0 |
| helsam-dk | DK | yes | 4188 | 4188 | 4188 | 0 | +4188 | 3855 | 2668 | 2676 | 2683 | 2683 | 1701 | 2653 | 4179 | 0 |
| bodystore-se | SE | yes | 5638 | 3280 | 3280 | 0 | +3280 | 474 | 784 | 783 | 785 | 785 | 652 | 764 | 3187 | 0 |
| proteincompany-no | NO | yes | 4404 | 3064 | 3064 | 0 | +3064 | 1367 | 627 | 815 | 812 | 813 | 608 | 780 | 2152 | 0 |
| bodystore-discontinued | NO | yes | 3840 | 2844 | 2844 | 0 | +2844 | 1455 | 719 | 718 | 721 | 719 | 538 | 707 | 2591 | 1690 |
| livsmedelsverket | SE | no | 2606 | 2606 | 2606 | 2606 | +0 | 2606 | 2606 | 2606 | 2606 | 2606 | 2606 | 2606 | 0 | 0 |
| gymgrossisten-se | SE | yes | 2500 | 2500 | 2500 | 0 | +2500 | 707 | 716 | 716 | 718 | 720 | 510 | 703 | 2290 | 0 |
| bodystore | NO | yes | 2672 | 2480 | 2480 | 2482 | -2 | 780 | 528 | 528 | 530 | 528 | 435 | 514 | 2411 | 0 |
| matvaretabellen | NO | yes | 2121 | 2121 | 2121 | 2121 | +0 | 2121 | 2118 | 2121 | 2121 | 2121 | 2121 | 2116 | 0 | 0 |
| life-no-discontinued | NO | yes | 2048 | 2013 | 2013 | 0 | +2013 | 1473 | 276 | 298 | 298 | 290 | 196 | 280 | 585 | 1422 |
| sportkost | SE | yes | 1938 | 1938 | 1938 | 0 | +1938 | 1897 | 1128 | 1059 | 1054 | 1081 | 489 | 1115 | 236 | 0 |
| proteinfabrikken-discontinued | NO | yes | 2867 | 1865 | 1865 | 0 | +1865 | 875 | 391 | 426 | 429 | 429 | 270 | 409 | 1472 | 1081 |
| halsokostbolaget | SE | yes | 2851 | 1861 | 1861 | 0 | +1861 | 880 | 232 | 233 | 227 | 231 | 99 | 231 | 1833 | 0 |
| gymgrossisten | NO | yes | 1854 | 1854 | 1854 | 2921 | -1067 | 1540 | 515 | 509 | 511 | 511 | 327 | 507 | 1684 | 0 |
| bodypower | SE | yes | 1767 | 1767 | 1767 | 0 | +1767 | 1704 | 1027 | 966 | 961 | 982 | 437 | 1014 | 70 | 0 |
| life-no | NO | yes | 1661 | 1635 | 1635 | 0 | +1635 | 665 | 192 | 191 | 192 | 190 | 128 | 184 | 1606 | 0 |
| bodystore-dk | DK | yes | 1539 | 1449 | 1449 | 0 | +1449 | 182 | 71 | 71 | 71 | 63 | 41 | 61 | 1280 | 0 |
| proteinbolaget | SE | yes | 2385 | 1418 | 1418 | 0 | +1418 | 225 | 369 | 368 | 361 | 367 | 218 | 336 | 1386 | 0 |
| frida-dk | DK | no | 1390 | 1390 | 1390 | 1390 | +0 | 1390 | 1390 | 1389 | 1390 | 1390 | 1390 | 1390 | 0 | 0 |
| tillskottsbolaget | SE | yes | 1402 | 1336 | 1336 | 0 | +1336 | 1161 | 423 | 411 | 385 | 391 | 214 | 390 | 444 | 0 |
| goldenathlete | SE | yes | 2921 | 1051 | 1051 | 0 | +1051 | 902 | 205 | 220 | 209 | 212 | 117 | 206 | 279 | 0 |
| tights-discontinued | NO | yes | 1047 | 1042 | 1042 | 0 | +1042 | 977 | 432 | 480 | 482 | 468 | 325 | 480 | 216 | 898 |
| gymgrossisten-discontinued | NO | yes | 976 | 970 | 970 | 0 | +970 | 481 | 90 | 89 | 90 | 89 | 44 | 88 | 782 | 602 |
| matas-dk | DK | yes | 956 | 956 | 956 | 0 | +956 | 520 | 507 | 452 | 408 | 444 | 301 | 445 | 914 | 0 |
| myprotein-discontinued | NO | yes | 2863 | 921 | 921 | 0 | +921 | 866 | 249 | 250 | 250 | 251 | 150 | 249 | 141 | 878 |
| bodybuilding | US | no | 2578 | 876 | 876 | 0 | +876 | 876 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 |
| life-se | SE | yes | 849 | 847 | 847 | 0 | +847 | 349 | 144 | 139 | 138 | 137 | 117 | 128 | 830 | 0 |
| kost1-no | NO | yes | 817 | 808 | 808 | 0 | +808 | 808 | 39 | 39 | 30 | 29 | 16 | 32 | 0 | 0 |
| halsafitnessbutiken | SE | yes | 761 | 761 | 761 | 0 | +761 | 761 | 89 | 93 | 89 | 89 | 47 | 88 | 0 | 0 |
| diggbox-no | NO | yes | 757 | 757 | 757 | 0 | +757 | 716 | 395 | 389 | 395 | 395 | 215 | 384 | 283 | 0 |
| mmsports | SE | yes | 703 | 703 | 703 | 0 | +703 | 606 | 222 | 222 | 222 | 222 | 128 | 223 | 299 | 0 |
| proteinfabrikken | NO | yes | 666 | 664 | 664 | 799 | -135 | 71 | 278 | 289 | 288 | 283 | 168 | 286 | 622 | 0 |
| coore-no | NO | yes | 605 | 605 | 605 | 0 | +605 | 495 | 107 | 103 | 98 | 115 | 55 | 94 | 456 | 0 |
| myprotein-uk | UK | yes | 2551 | 545 | 545 | 0 | +545 | 464 | 228 | 230 | 230 | 230 | 138 | 230 | 466 | 0 |
| eldorado | NO | yes | 396 | 396 | 396 | 396 | +0 | 395 | 394 | 394 | 394 | 394 | 394 | 394 | 396 | 0 |
| sportylab-no | NO | yes | 488 | 336 | 336 | 0 | +336 | 266 | 109 | 106 | 106 | 107 | 63 | 107 | 193 | 0 |
| gilde | NO | yes | 321 | 321 | 321 | 321 | +0 | 321 | 321 | 321 | 321 | 321 | 0 | 321 | 319 | 0 |
| apex-no | NO | yes | 318 | 309 | 309 | 0 | +309 | 303 | 123 | 122 | 122 | 118 | 73 | 119 | 51 | 0 |
| bodylab-no | NO | yes | 379 | 297 | 297 | 0 | +297 | 213 | 193 | 190 | 191 | 190 | 158 | 190 | 225 | 0 |
| bulk | EU | yes | 284 | 284 | 284 | 1638 | -1354 | 214 | 130 | 130 | 130 | 130 | 130 | 130 | 284 | 0 |
| firstprice | NO | yes | 294 | 279 | 279 | 294 | -15 | 279 | 199 | 187 | 187 | 187 | 187 | 187 | 279 | 0 |
| toro | NO | yes | 264 | 264 | 264 | 264 | +0 | 264 | 261 | 259 | 255 | 261 | 82 | 257 | 0 | 0 |
| ghost | US | no | 554 | 262 | 262 | 0 | +262 | 262 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| tine | NO | yes | 255 | 254 | 254 | 254 | +0 | 254 | 243 | 243 | 243 | 243 | 15 | 243 | 0 | 0 |
| nordicpower-no | NO | yes | 252 | 244 | 244 | 0 | +244 | 244 | 48 | 52 | 30 | 31 | 34 | 46 | 0 | 0 |
| scitec | EU | yes | 878 | 243 | 243 | 0 | +243 | 203 | 63 | 60 | 59 | 63 | 19 | 59 | 235 | 0 |
| applied-nutrition | UK | yes | 1096 | 238 | 238 | 0 | +238 | 238 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| tyngre | SE | yes | 198 | 198 | 198 | 0 | +198 | 138 | 168 | 166 | 168 | 168 | 30 | 168 | 167 | 0 |
| nidar | NO | yes | 193 | 193 | 193 | 193 | +0 | 193 | 177 | 177 | 177 | 177 | 30 | 177 | 0 | 0 |
| hennig-olsen | NO | yes | 175 | 175 | 175 | 175 | +0 | 175 | 163 | 163 | 163 | 163 | 0 | 163 | 175 | 0 |
| ringnes | NO | yes | 174 | 174 | 174 | 174 | +0 | 174 | 172 | 163 | 163 | 162 | 0 | 163 | 0 | 0 |
| kungmarkatta | SE | yes | 142 | 142 | 142 | 0 | +142 | 142 | 142 | 125 | 127 | 128 | 87 | 99 | 0 | 0 |
| esn | EU | yes | 703 | 129 | 129 | 0 | +129 | 129 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| bodylab-dk | DK | yes | 157 | 109 | 109 | 0 | +109 | 109 | 45 | 45 | 45 | 45 | 42 | 45 | 0 | 0 |
| quest | US | no | 481 | 108 | 108 | 0 | +108 | 84 | 67 | 67 | 67 | 67 | 67 | 67 | 88 | 0 |
| bodylab-se | SE | yes | 105 | 105 | 105 | 0 | +105 | 48 | 42 | 42 | 42 | 42 | 40 | 42 | 59 | 0 |
| fjordland | NO | yes | 97 | 97 | 97 | 97 | +0 | 97 | 97 | 97 | 97 | 97 | 69 | 97 | 0 | 0 |
| starnutrition-se | SE | yes | 95 | 95 | 95 | 0 | +95 | 95 | 44 | 44 | 44 | 44 | 29 | 44 | 0 | 0 |
| mills | NO | yes | 94 | 94 | 94 | 94 | +0 | 94 | 88 | 82 | 88 | 82 | 17 | 84 | 0 | 0 |
| synnove | NO | yes | 93 | 93 | 93 | 93 | +0 | 93 | 93 | 93 | 93 | 93 | 16 | 93 | 0 | 0 |
| bulk-discontinued | EU | yes | 284 | 92 | 92 | 0 | +92 | 78 | 25 | 25 | 25 | 25 | 25 | 25 | 90 | 88 |
| prior | NO | yes | 90 | 90 | 90 | 90 | +0 | 90 | 90 | 90 | 90 | 90 | 0 | 90 | 90 | 0 |
| cellucor | US | no | 299 | 81 | 81 | 0 | +81 | 81 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| transparent-labs | US | no | 593 | 68 | 68 | 0 | +68 | 68 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| optimum-nutrition | EU | yes | 264 | 65 | 65 | 0 | +65 | 33 | 22 | 21 | 21 | 21 | 13 | 21 | 55 | 0 |
| barebells-no | NO | yes | 64 | 64 | 64 | 0 | +64 | 64 | 48 | 48 | 48 | 48 | 42 | 48 | 0 | 0 |
| barebells | SE | yes | 64 | 64 | 64 | 0 | +64 | 64 | 53 | 52 | 53 | 52 | 41 | 53 | 0 | 0 |
| legion | US | no | 106 | 53 | 53 | 0 | +53 | 53 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| grenade | UK | yes | 90 | 45 | 45 | 0 | +45 | 45 | 32 | 32 | 32 | 32 | 27 | 32 | 0 | 0 |
| gorilla-mind | US | no | 164 | 45 | 45 | 0 | +45 | 45 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| muscletech | US | no | 145 | 44 | 44 | 0 | +44 | 44 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| reflex | UK | yes | 173 | 43 | 43 | 0 | +43 | 43 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| nocco | SE | yes | 42 | 42 | 42 | 0 | +42 | 42 | 41 | 41 | 41 | 41 | 0 | 41 | 0 | 0 |
| q-meieriene | NO | yes | 34 | 34 | 34 | 34 | +0 | 34 | 33 | 33 | 33 | 33 | 11 | 33 | 1 | 0 |
| dymatize | US | no | 62 | 31 | 31 | 0 | +31 | 31 | 25 | 22 | 22 | 25 | 22 | 22 | 0 | 0 |
| saetre | NO | yes | 28 | 28 | 28 | 28 | +0 | 28 | 28 | 28 | 28 | 28 | 28 | 28 | 0 | 0 |
| myprotein | NO | yes | 63 | 27 | 27 | 36 | -9 | 24 | 3 | 3 | 3 | 3 | 2 | 3 | 24 | 0 |
| kavli | NO | yes | 22 | 22 | 22 | 22 | +0 | 22 | 21 | 22 | 22 | 22 | 3 | 22 | 0 | 0 |
| nutramino-dk | DK | yes | 19 | 19 | 19 | 0 | +19 | 19 | 19 | 18 | 18 | 18 | 10 | 16 | 0 | 0 |
| grandiosa | NO | yes | 17 | 17 | 17 | 17 | +0 | 17 | 17 | 17 | 17 | 17 | 0 | 17 | 0 | 0 |
| weider | EU | yes | 20 | 10 | 10 | 0 | +10 | 10 | 0 | 0 | 0 | 0 | 0 | 0 | 9 | 0 |
| fulfil | EU | yes | 16 | 8 | 8 | 0 | +8 | 8 | 8 | 8 | 8 | 8 | 8 | 8 | 0 | 0 |

`raw` counts file lines in `data/raw/<folder>/products.jsonl` (v2 folder for the five replaced shops; for usda-fdc and a few multi-file sources it is blank). Variant, page and offer rows of one page are separate lines in the raw file but one candidate here.

## Food vs non-food per store

Food = every record that went into the merge. Non-food = records dropped because they had no nutrition AND the name or category says clothing, gear, shaker, cosmetics, pet food or household. Placeholder = Nemlig rows whose nutrition is all zero. Not-a-product = a record with no name, no EAN and no nutrition. Kept without nutrition are products that stay in the library (supplements with an image-only table and so on).

| Source | read (food) | with per-100 kcal | kept without nutrition | dropped non-food | dropped placeholder / empty |
|---|---:|---:|---:|---:|---:|
| openfoodfacts-nordic-global | 68329 | 55333 | 9773 | 0 | 0 |
| usda-fdc | 45310 | 41637 | 3039 | 0 | 0 |
| norgesgruppen | 28442 | 24171 | 4269 | 10787 | 0 |
| openfoodfacts | 27445 | 19490 | 7776 | 0 | 0 |
| tights | 7581 | 2220 | 5114 | 3 | 0 |
| kassalapp | 5994 | 5165 | 829 | 0 | 0 |
| ica-se | 4640 | 835 | 3752 | 421 | 0 |
| helsekost-no | 4510 | 2026 | 2481 | 127 | 0 |
| helsam-dk | 4188 | 2668 | 1496 | 0 | 0 |
| bodystore-se | 3280 | 784 | 2489 | 2358 | 0 |
| proteincompany-no | 3064 | 627 | 2197 | 2 | 0 |
| bodystore-discontinued | 2844 | 719 | 2097 | 995 | 1 |
| livsmedelsverket | 2606 | 2606 | 0 | 0 | 0 |
| gymgrossisten-se | 2500 | 716 | 1769 | 0 | 0 |
| bodystore | 2480 | 528 | 1946 | 192 | 0 |
| matvaretabellen | 2121 | 2118 | 0 | 0 | 0 |
| life-no-discontinued | 2013 | 276 | 1707 | 35 | 0 |
| sportkost | 1938 | 1128 | 778 | 0 | 0 |
| proteinfabrikken-discontinued | 1865 | 391 | 1428 | 897 | 105 |
| halsokostbolaget | 1861 | 232 | 1623 | 990 | 0 |
| gymgrossisten | 1854 | 515 | 1331 | 0 | 0 |
| bodypower | 1767 | 1027 | 714 | 0 | 0 |
| life-no | 1635 | 192 | 1434 | 26 | 0 |
| bodystore-dk | 1449 | 71 | 1377 | 90 | 0 |
| proteinbolaget | 1418 | 369 | 1023 | 0 | 0 |
| frida-dk | 1390 | 1390 | 0 | 0 | 0 |
| tillskottsbolaget | 1336 | 423 | 897 | 66 | 0 |
| goldenathlete | 1051 | 205 | 817 | 68 | 0 |
| tights-discontinued | 1042 | 432 | 559 | 5 | 0 |
| gymgrossisten-discontinued | 970 | 90 | 877 | 6 | 0 |
| matas-dk | 956 | 507 | 298 | 0 | 0 |
| myprotein-discontinued | 921 | 249 | 666 | 1 | 0 |
| bodybuilding | 876 | 0 | 876 | 0 | 0 |
| life-se | 847 | 144 | 703 | 2 | 0 |
| kost1-no | 808 | 39 | 768 | 9 | 0 |
| halsafitnessbutiken | 761 | 89 | 666 | 0 | 0 |
| diggbox-no | 757 | 395 | 362 | 0 | 0 |
| mmsports | 703 | 222 | 476 | 0 | 0 |
| proteinfabrikken | 664 | 278 | 364 | 2 | 0 |
| coore-no | 605 | 107 | 486 | 0 | 0 |
| myprotein-uk | 545 | 228 | 308 | 1 | 0 |
| eldorado | 396 | 394 | 2 | 0 | 0 |
| sportylab-no | 336 | 109 | 218 | 152 | 0 |
| gilde | 321 | 321 | 0 | 0 | 0 |
| apex-no | 309 | 123 | 183 | 9 | 0 |
| bodylab-no | 297 | 193 | 104 | 82 | 0 |
| bulk | 284 | 130 | 154 | 0 | 0 |
| firstprice | 279 | 199 | 80 | 15 | 0 |
| toro | 264 | 261 | 0 | 0 | 0 |
| ghost | 262 | 0 | 262 | 0 | 0 |
| tine | 254 | 243 | 11 | 0 | 0 |
| nordicpower-no | 244 | 48 | 191 | 8 | 0 |
| scitec | 243 | 63 | 177 | 71 | 0 |
| applied-nutrition | 238 | 0 | 238 | 0 | 0 |
| tyngre | 198 | 168 | 30 | 0 | 0 |
| nidar | 193 | 177 | 16 | 0 | 0 |
| hennig-olsen | 175 | 163 | 12 | 0 | 0 |
| ringnes | 174 | 172 | 2 | 0 | 0 |
| kungmarkatta | 142 | 142 | 0 | 0 | 0 |
| esn | 129 | 0 | 129 | 0 | 0 |
| bodylab-dk | 109 | 45 | 58 | 48 | 0 |
| quest | 108 | 67 | 41 | 0 | 0 |
| bodylab-se | 105 | 42 | 63 | 0 | 0 |
| fjordland | 97 | 97 | 0 | 0 | 0 |
| starnutrition-se | 95 | 44 | 51 | 0 | 0 |
| mills | 94 | 88 | 6 | 0 | 0 |
| synnove | 93 | 93 | 0 | 0 | 0 |
| bulk-discontinued | 92 | 25 | 67 | 10 | 0 |
| prior | 90 | 90 | 0 | 0 | 0 |
| cellucor | 81 | 0 | 81 | 0 | 0 |
| transparent-labs | 68 | 0 | 68 | 0 | 0 |
| optimum-nutrition | 65 | 22 | 43 | 0 | 0 |
| barebells-no | 64 | 48 | 16 | 0 | 0 |
| barebells | 64 | 53 | 11 | 0 | 0 |
| legion | 53 | 0 | 53 | 0 | 0 |
| gorilla-mind | 45 | 0 | 45 | 0 | 0 |
| grenade | 45 | 32 | 13 | 0 | 0 |
| muscletech | 44 | 0 | 44 | 0 | 0 |
| reflex | 43 | 0 | 43 | 0 | 0 |
| nocco | 42 | 41 | 1 | 0 | 0 |
| q-meieriene | 34 | 33 | 1 | 0 | 0 |
| dymatize | 31 | 25 | 6 | 0 | 0 |
| saetre | 28 | 28 | 0 | 0 | 0 |
| myprotein | 27 | 3 | 24 | 0 | 0 |
| kavli | 22 | 21 | 0 | 0 | 0 |
| nutramino-dk | 19 | 19 | 0 | 0 | 0 |
| grandiosa | 17 | 17 | 0 | 0 | 0 |
| weider | 10 | 0 | 10 | 0 | 0 |
| fulfil | 8 | 8 | 0 | 0 | 0 |

## Region and Norway relevance

`region` of a product is the best region among its sources in the order NO, SE, DK, EU, UK, US, other (so an EAN found in a Norwegian shop is NO even if a Swedish shop also has it); `regions` lists all. `norway_relevant` is true when any source is Norwegian, or a Nordic, EU or UK online shop / database Max can buy from (Swedish and Danish shops, Bulk, Myprotein UK, Scitec, ESN, Weider, Optimum Nutrition EU, Grenade and other UK sites, Open Food Facts records tagged for a Nordic country). It is false when every source is USDA branded, Frida, Livsmedelsverket, a US brand site (Quest, Cellucor, MuscleTech, Ghost, Transparent Labs, Gorilla Mind, Legion, Dymatize, Bodybuilding.com) or an Open Food Facts record that is not tagged for a Nordic country. That is a judgement about reach, not a statement that the product cannot be bought in Norway.

| Region | products | norway-relevant | with full macros | relevant with full macros | with EAN | discontinued |
|---|---:|---:|---:|---:|---:|---:|
| NO | 80270 | 80270 | 51883 | 51883 | 60533 | 5416 |
| SE | 42118 | 39512 | 29266 | 26660 | 32309 | 0 |
| DK | 6178 | 4788 | 4455 | 3066 | 4435 | 0 |
| EU | 21676 | 713 | 15581 | 226 | 20890 | 78 |
| UK | 2520 | 716 | 1409 | 191 | 2065 | 0 |
| US | 26440 | 0 | 21994 | 0 | 16208 | 0 |
| other | 6860 | 283 | 4719 | 229 | 6722 | 0 |
| **all** | 186062 | 126282 | 129307 | 82255 | 143162 | 5494 |

Norway-relevant products by how they qualify: NO 80270, SE 39512, DK 4788, EU 713, UK 716, other 283 (by best region).

Of the Norway-relevant products with full macros, 310 have the per-100 g values derived from a per-serving table (flag `per100_derived_from_serving`) and 5027 carry the flag `flavour_nutrition_shared_assumed`.

## Discontinued products

A product is `discontinued` when every one of its source pages is gone: the live URL answered 404/410 or redirected elsewhere, and the data comes from an Internet Archive snapshot (tights, gymgrossisten, bodystore, proteinfabrikken, myprotein, bulk, life.no), or Open Food Facts marks the product obsolete. Products whose page is live but hidden from the shop listing are NOT discontinued. If any live source exists the product is not discontinued, even when an old shop page is gone.

| Primary source | discontinued products | with full macros | with EAN |
|---|---:|---:|---:|
| life-no-discontinued | 1421 | 183 | 1 |
| bodystore-discontinued | 1158 | 209 | 970 |
| tights-discontinued | 847 | 361 | 115 |
| myprotein-discontinued | 827 | 202 | 58 |
| proteinfabrikken-discontinued | 763 | 107 | 397 |
| gymgrossisten-discontinued | 400 | 24 | 216 |
| bulk-discontinued | 78 | 21 | 76 |

Source entries with a gone page (including entries that sit inside a still-live product): 6659.

## Nutrient completeness of the unified products (primary values + gap fills)

| Has | Products | % of all | % of products with a barcode |
|---|---:|---:|---:|
| kcal | 132039 | 71.0% | 73.6% |
| protein | 131209 | 70.5% | 72.9% |
| fat | 130859 | 70.3% | 72.7% |
| carbs | 131242 | 70.5% | 73.0% |
| fibre | 75921 | 40.8% | 38.6% |
| salt | 121771 | 65.4% | 66.5% |
| sugars | 123589 | 66.4% | 69.4% |
| saturated fat | 120591 | 64.8% | 66.5% |
| kcal + protein + fat + carbs (full macros) | 129307 | 69.5% | 72.0% |
| full macros + fibre + salt | 71377 | 38.4% | 35.8% |
| at least one vitamin | 38748 | 20.8% | 15.0% |
| at least one mineral (besides sodium) | 39570 | 21.3% | 15.7% |
| at least one amino acid | 6865 | 3.7% | 0.2% |
| at least one fatty-acid detail (omega-3, EPA, chains) | 14633 | 7.9% | 0.9% |
| both a vitamin and a mineral | 33528 | 18.0% | 11.9% |
| per-serving values (any) | 12974 | 7.0% | 4.5% |
| no nutrition at all | 49788 | 26.8% | 23.9% |

Product kinds: generic 14379, product 171683 (`generic` = food composition table rows: Matvaretabellen, Frida, Livsmedelsverket, USDA Foundation/SR Legacy; they have no EAN or brand).

Products with a barcode by region of the primary EAN prefix: Norwegian 70xx: 27697; other: 115465.

## Data-quality flags

Every product has a `data_quality` list; the primary source decides it, plus cross-source flags. Thresholds: kcal vs 4/4/9 (plus 2 kcal/g fibre, 7 kcal/g alcohol, 2.4 kcal/g polyols) must be within 15 % or 20 kcal; kJ/kcal within 12 %; protein+fat+carbs over 105 g per 100 g is flagged as probably per-serving or a unit error; cross-source disagreement: kcal more than 15 % and 20 kcal apart, protein/fat/carbs more than 25 % and 3 g apart.

| Flag | Products | Meaning |
|---|---:|---|
| missing_fibre | 57419 | has kcal but no fibre value |
| no_nutrition | 49788 | no per-100 g or per-serving nutrition at all |
| flavour_nutrition_shared_assumed | 16583 | page lists several flavours / variants; one nutrition table is used for the product (decided: flavours share nutrition) |
| missing_salt | 11111 | has kcal but neither salt nor sodium |
| us_market_product | 7751 | USDA branded product (US market) |
| per_serving_only | 6997 | only per-serving values, no per-100 g (not converted) |
| kcal_macro_mismatch | 5214 | kcal does not match macros (4/4/9 check) |
| ean_malformed | 4330 | EAN is a PLU/short code (weighed goods) or wrong length (not used for merging) |
| filled_from_other_source | 4266 | gaps in the primary filled from an agreeing source (kcal within tolerance), see field_provenance |
| missing_kcal | 4235 | per-100 g values exist but no energy |
| kj_kcal_mismatch | 4062 | kJ and kcal disagree by more than 12 % |
| ean_checksum_invalid | 2859 | EAN given by the source fails the GTIN check digit (not used for merging) |
| missing_macros | 2797 | kcal present but protein, fat or carbs missing |
| salt_sodium_mismatch | 2401 | salt and sodium differ by more than 40 % from the 2.5 factor |
| ingredients_discarded_junk | 2306 | scraped text was a page footer or a whole-page dump, not an ingredient list; discarded |
| sources_disagree | 2019 | two sources disagree on kcal/protein/fat/carbs, see source_disagreements |
| nutrition_text_only | 1062 | nutrition only as free text, not parsed |
| nutrition_image_only | 1000 | nutrition is only an image on the page (not read) |
| per100_derived_from_serving | 680 | per-100 g computed from a per-serving table and its gram size (energy present, serving at least 5 g) |
| per100_basis_unverified | 595 | page table did not state per 100 g or per serving |
| bundle_or_multipack | 575 | bundle or multipack page |
| per100_is_prepared_state | 503 | per-100 g is the prepared (cooked) state, not as sold |
| macros_sum_over_100g | 362 | protein+fat+carbs over 105 g: per-100 g may be per-serving |
| unit_assumed | 348 | a vitamin/mineral value had no unit, canonical unit assumed |
| kcal_implausible_high | 298 | over 910 kcal per 100 g |
| sugars_exceed_carbs | 295 | sugars above carbohydrate |
| per100_basis_assumed | 261 | the table did not print per 100 g / 100 ml; per 100 assumed |
| carbs_over_100g | 188 | carbohydrate above 100 g per 100 g |
| flavour_table_ambiguous | 163 | proteinfabrikken page with several candidate tables; the collector could not pick one |
| protein_over_100g | 153 | protein above 100 g per 100 g |
| sat_fat_exceeds_fat | 106 | saturated fat above total fat |
| scraper_flag_macro_energy_mismatch | 94 | collector flagged macros vs energy |
| scraper_flag_kj_kcal_ratio | 93 | collector flagged kJ vs kcal |
| kj_dropped_inconsistent_with_kcal | 90 | kJ disagreed with kcal and was dropped (kcal kept) |
| fat_over_100g | 85 | fat above 100 g per 100 g |
| unit_inferred_by_scraper | 79 | unit not printed, inferred by the collector |
| variant_table_ambiguous | 29 | several flavour tables, first used |
| implausible_value_removed_by_collector | 22 | a value above physical limits was removed by the fix-flavours collector |
| sodium_unit_assumed | 19 | sodium without unit: values <= 5 read as g, else mg |
| variants_share_one_nutrition_table | 17 | page states that variants share one table |
| flavour_macros_may_differ | 10 | page text says flavour macros may differ |
| per100_prepared_state_only | 8 | only a prepared-drink column exists, not mapped |
| energy_unit_guessed | 6 | Gymgrossisten energy unit guessed |
| energy_unit_unclear | 3 | Gymgrossisten energy unit unclear |

## Real searches against products.sqlite

Run with FTS5 (`products_fts` on name, brand, flavour, categories; unicode61, diacritics folded). Ranking is bm25, products with kcal first. Values per 100 g. `src` = primary source, `n` = number of source entries.

### YT proteinyoghurt

`MATCH yt AND proteinyoghurt*` : 16 hits, top 10

| id | name | brand | flavour | kcal | protein | fat | carbs | salt | src | n |
|---|---|---|---|---:|---:|---:|---:|---:|---|---:|
| tine:https://www.tine.no/merkevarer/yt/produkter/yt-proteinyoghurt-bringeb%C3%A6r | YT® PROTEINYOGHURT BRINGEBÆR - YT® | yt |  | 69 | 9.3 | 1.9 | 3.4 | 0.09 | tine | 1 |
| tine:https://www.tine.no/merkevarer/yt/produkter/yt-proteinyoghurt-pasjonsfrukt | YT® PROTEINYOGHURT PASJONSFRUKT - YT® | yt |  | 67 | 9.3 | 1.8 | 3.4 | 0.09 | tine | 1 |
| tine:https://www.tine.no/merkevarer/yt/produkter/yt-proteinyoghurt-vanilje | YT® PROTEINYOGHURT VANILJE - YT® | yt |  | 69 | 9.2 | 1.8 | 3.5 | 0.1 | tine | 1 |
| tine:https://www.tine.no/merkevarer/yt/produkter/yt-proteinyoghurt-vanilje-stor | YT® PROTEINYOGHURT VANILJE - YT® | yt |  | 69 | 9.2 | 1.8 | 3.5 | 0.1 | tine | 1 |
| ean:7038010071904 | YT Proteinyoghurt Vanilje | YT |  | 68.8372 | 19.8 | 3.9 | 7.5 | 0.00025 | openfoodfacts | 1 |
| tine:https://www.tine.no/merkevarer/yt/produkter/yt-proteinyoghurt-bringeb%C3%A6r-180g | YT® PROTEINYOGHURT BRINGEBÆR 180g - YT® | yt |  | 69 | 9.3 | 1.9 | 3.4 | 0.09 | tine | 1 |
| tine:https://www.tine.no/merkevarer/yt/produkter/yt-proteinyoghurt-vanilje-180g | YT® PROTEINYOGHURT VANILJE 180g - YT® | yt |  | 69 | 9.2 | 1.8 | 3.5 | 0.1 | tine | 1 |
| kassalapp:199717 | YT proteinyoghurt Bringebær, 430 g | Tine |  | 69 | 9.3 | 1.9 | 3.4 | 0.09 | kassalapp | 1 |
| kassalapp:213449 | YT proteinyoghurt Vanilje, 180 g | Tine |  | 69 | 9.2 | 1.8 | 3.5 | 0.1 | kassalapp | 1 |
| kassalapp:213650 | YT proteinyoghurt Bringebær, 180 g | Tine |  | 69 | 9.3 | 1.9 | 3.4 | 0.09 | kassalapp | 1 |

### Skyr

`MATCH skyr` : 213 hits, top 10

| id | name | brand | flavour | kcal | protein | fat | carbs | salt | src | n |
|---|---|---|---|---:|---:|---:|---:|---:|---|---:|
| ean:7048840210947 | Skyr yoghurt | Skyr |  | 60 | 9.6 | 0.16 | 4 |  | openfoodfacts | 1 |
| ean:7048840219285 | Skyr pasjonsfrukt | Skyr |  | 57.6923 | 9.23077 | 0.153846 | 4.23077 |  | openfoodfacts | 1 |
| ean:7048840210916 | Skyr Mango & Pasjon | Skyr |  | 65 | 10 | 0.2 | 4.7 | 0.0975 | openfoodfacts | 1 |
| ean:7048840222896 | Skyr | Skyr |  | 60 | 11 | 0.2 | 3.6 | 0.1 | norgesgruppen | 2 |
| ean:7048840225781 | Skyr | Skyr |  | 61 | 9.7 | 0.2 | 4.6 | 0.1 | norgesgruppen | 2 |
| ean:7048840225521 | Skyr | Skyr |  | 57 | 9.7 | 0.2 | 3.8 | 0.1 | norgesgruppen | 2 |
| ean:7048840210183 | Skyr |  |  | 96 | 16 | 0.3 | 6.4 |  | openfoodfacts | 1 |
| ean:7048840091041 | Skyr Mini | Skyr |  | 68 | 9.4 | 0.2 | 6.8 | 0.1 | norgesgruppen | 2 |
| ean:7048840290819 | Skyr Luftig | Skyr |  | 51 | 8.6 | 0.2 | 3.6 | 0.1 | norgesgruppen | 2 |
| ean:7048840224203 | Skyr Aktiv Blåbær & Accai | Skyr |  | 63 | 9.4 | 0.1 | 4.4 | 0.0975 | openfoodfacts | 1 |

### Tine Lett

`MATCH tine AND lett*` : 107 hits, top 10

| id | name | brand | flavour | kcal | protein | fat | carbs | salt | src | n |
|---|---|---|---|---:|---:|---:|---:|---:|---|---:|
| tine:https://www.tine.no/merkevarer/tine-brunost/produkter/tine-fl%C3%B8temysost-lett | TINE® Fløtemysost Lett | tine-brunost |  | 371 | 12 | 16 | 44 | 0.89 | tine | 1 |
| tine:https://www.tine.no/merkevarer/tine-fl%C3%B8te/produkter/tine-lett-matfl%C3%B8te | TINE® Lett Matfløte | tine-fløte |  | 114 | 1.7 | 10 | 4.2 | 0.1 | tine | 1 |
| tine:https://www.tine.no/merkevarer/tine-prim/produkter/tine-prim-lett | TINE Prim Lett | tine-prim |  | 255 | 7 | 4 | 48 | 0.75 | tine | 1 |
| tine:https://www.tine.no/merkevarer/tine-r%C3%B8mme/produkter/tine-laktosefri-lettr%C3%B8mme | TINE® Laktosefri Lettrømme | tine-rømme |  | 180 | 2.9 | 17 | 3.9 | 0.09 | tine | 1 |
| tine:https://www.tine.no/merkevarer/tine-r%C3%B8mme/produkter/tine-lett-r%C3%B8mme-10-prosent | TINE® Lettrømme 10 % | tine-rømme |  | 119 | 3.2 | 10 | 4 | 0.1 | tine | 1 |
| tine:https://www.tine.no/merkevarer/tine-r%C3%B8mme/produkter/tine-lettr%C3%B8mme-17-prosent | TINE® Lettrømme 17 % | tine-rømme |  | 180 | 2.9 | 17 | 3.9 | 0.09 | tine | 1 |
| ean:7038010044809 | Økologisk lettmelk | Tine |  | 39 | 3.4 | 0.7 | 4.7 |  | openfoodfacts | 1 |
| ean:7038010071850 | Lettmelk sjokolade | Tine |  | 47 | 3.7 | 1.1 | 5.6 |  | openfoodfacts | 1 |
| ean:2302693411100 | Norvegia Lettest | Tine |  | 268 | 31 | 16 | 0 | 1.0825 | openfoodfacts | 1 |
| ean:2302693411087 | Norvegia Lettost | Tine |  | 268 | 31 | 16 | 0 |  | openfoodfacts | 1 |

### protein powder chocolate

`MATCH (protein* OR whey* OR myseprotein* OR proteinpulver*) AND (chocolate OR sjokolade OR choc* OR chokolade)` : 5207 hits, top 10

| id | name | brand | flavour | kcal | protein | fat | carbs | salt | src | n |
|---|---|---|---|---:|---:|---:|---:|---:|---|---:|
| ean:7350132947111 | Whey Tech Protein, 1kg, Sjokolade | Proteinfabrikken |  | 387 | 75 | 5.6 | 8.9 | 0.64 | proteinfabrikken-discontinued | 3 |
| ean:7350132943472 | Whey 100 %, 1 kg, Sjokolade | Proteinfabrikken |  | 393 | 74 | 6.5 | 8.9 | 0.92 | proteinfabrikken-discontinued | 4 |
| ean:7350132943427 | Whey 100 %, 1 kg, Mocca Sjokolade | Proteinfabrikken |  | 390 | 72 | 6.5 | 9.7 | 0.91 | proteinfabrikken-discontinued | 3 |
| ean:5060763891524 | Shadowhey Concentrate Myseprotein 2 kg Chocolate Hazelnut | Proteinfabrikken |  | 383 | 74 | 6.5 | 7.1 | 0.4 | proteinfabrikken-discontinued | 1 |
| ean:7350116311211 | Athletics Myseprotein 500 g Sjokolade | Pureness |  | 351 | 70 | 5.4 | 4.4 | 1.2 | bodystore-discontinued | 7 |
| ean:7350023036368 | Myseprotein Sjokolade 750 gram | Elexir Pharma |  | 365 | 72 | 6.2 | 4.5 | 0.66 | bodystore | 3 |
| ean:5056357901229 | Maltesers Proteinpulver 450 g Mars Chocolate Malt | Mars |  | 399 | 60 | 7 | 22 | 0.83 | bodystore-discontinued | 4 |
| bodystore-discontinued:SETHOLISTICVASSLEPROTCHOK | 2 x Holistic Myseprotein Sjokolade 750 g | Holistic |  | 405 | 75.4 | 6.6 | 11.4 | 0.5 | bodystore-discontinued | 1 |
| ean:7350132945339 | Vitaprana Grass-Fed Whey Protein Isolate Chocolate 750g | Vitaprana | Sjokolade | 371 | 83 | 2.3 | 3.4 | 1.4 | tights | 13 |
| ean:7350071920343 | Supreme Whey 100 Myseprotein 900 g Coconut Choco | Delta Nutrition |  | 380 | 77 | 4 | 8 | 0.5 | bodystore-discontinued | 1 |

### Gilde kjottdeig

`MATCH gilde AND (kjottdeig* OR kjøttdeig*)` : 11 hits, top 10

| id | name | brand | flavour | kcal | protein | fat | carbs | salt | src | n |
|---|---|---|---|---:|---:|---:|---:|---:|---|---:|
| ean:7037204612428 | Kjøttdeig Storfe | Gilde |  | 227 | 17 | 18 | 0 | 0.8 | norgesgruppen | 2 |
| ean:7037203627263 | Gilde Kjøttdeig av Storfe 14% 400g | Gilde |  | 194 | 17 | 14 | 0 | 1.1 | kassalapp | 3 |
| ean:7020098003052 | Gilde Kjøttdeig u/Salt/Vann 400g Enh | Gilde |  | 202 | 19 | 14 | 0 | 0.1 | gilde | 3 |
| ean:7037203627973 | Norsk kjøttdeig storfekjøtt 14% fett | Gilde |  | 807 | 17 | 14 | 0 | 1.1 | openfoodfacts | 1 |
| ean:7037203626952 | Lammedeig Hverdagslam 400g Gilde | Gilde |  | 252 | 18 | 20 | 0 | 0.1 | kassalapp | 2 |
| ean:7037203636388 | Karbonadedeig Nordnorsk 5% 400g Gilde | Gilde |  | 125 | 20 | 5 | 0 | 0.1 | kassalapp | 1 |
| ean:7037203645618 | Kjøttdeig Storfe USV 14% 400g Enh | Gilde |  | 202 | 19 | 14 | 0 | 0.1 | gilde | 2 |
| ean:7037203645731 | Kjøttdeig Lam USV 20% 400g Enh | Gilde |  | 271 | 17 | 23 | 0 | 0.2 | gilde | 2 |
| ean:7020098003106 | Gilde Karbonadedeig u/Salt/Vann 400g Enh | Gilde |  | 125 | 20 | 5 | 0 | 0.1 | gilde | 3 |
| ean:7037203645670 | Øko Kjøttdeig Sf USV 14% 400g Enh | Gilde |  | 202 | 19 | 14 | 0 | 0.1 | gilde | 2 |

Reproduce: `sqlite3 products.sqlite "select p.name,p.brand,p.kcal,p.protein_g from products_fts f join products p on p.rowid=f.rowid where products_fts match 'skyr' order by bm25(products_fts) limit 10"`.

## Protein powders and supplements

Products whose name or category matches protein, whey, creatine, BCAA/EAA, amino, pre-workout, casein, gainer, vitamin, omega, collagen, magnesium and similar words (kind = product, so no generic tables). This is a name match, not a curated category; Jev (TypeSafe) was NOT used to classify, it needs a chat yes first.

| Region | supplement-like products | Norway-relevant | with per-100 kcal | with full macros | per-serving only | no nutrition | with EAN | discontinued |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| NO | 12907 | 12907 | 4684 | 4521 | 2538 | 7844 | 7900 | 2052 |
| SE | 7741 | 7741 | 3700 | 3531 | 2245 | 3895 | 2861 | 0 |
| DK | 1149 | 1149 | 415 | 390 | 428 | 649 | 892 | 0 |
| EU | 12162 | 363 | 9787 | 9657 | 110 | 1520 | 11717 | 22 |
| UK | 1555 | 437 | 925 | 906 | 62 | 507 | 1252 | 0 |
| US | 10627 | 0 | 8491 | 8256 | 11 | 1631 | 9680 | 0 |
| other | 4056 | 155 | 3085 | 3006 | 0 | 691 | 3979 | 0 |
| all | 50197 | 22752 | 31087 | 30267 | 5394 | 16737 | 38281 | 2074 |

Supplement and protein shops, per source (entries, per-100 g kcal, per-serving only, no nutrition among products where the source is primary):

| Source | region | entries | with per-100 g kcal | per-serving only | no nutrition |
|---|---|---:|---:|---:|---:|
| tights | NO | 7581 | 2220 | 363 | 4578 |
| gymgrossisten | NO | 1854 | 515 | 749 | 1096 |
| bodystore | NO | 2480 | 528 | 131 | 541 |
| proteinfabrikken | NO | 664 | 278 | 7 | 27 |
| bulk | EU | 284 | 130 | 86 | 117 |
| myprotein | NO | 27 | 3 | 3 | 22 |
| tights-discontinued | NO | 1042 | 432 | 53 | 525 |
| gymgrossisten-discontinued | NO | 970 | 90 | 17 | 442 |
| bodystore-discontinued | NO | 2844 | 719 | 169 | 1104 |
| proteinfabrikken-discontinued | NO | 1865 | 391 | 27 | 703 |
| myprotein-discontinued | NO | 921 | 249 | 53 | 638 |
| bulk-discontinued | EU | 92 | 25 | 12 | 57 |
| bodylab-no | NO | 297 | 193 | 58 | 72 |
| life-no | NO | 1635 | 192 | 109 | 544 |
| life-no-discontinued | NO | 2013 | 276 | 81 | 1245 |
| kost1-no | NO | 808 | 39 | 423 | 768 |
| proteincompany-no | NO | 3064 | 627 | 511 | 850 |
| sportylab-no | NO | 336 | 109 | 74 | 157 |
| helsekost-no | NO | 4510 | 2026 | 0 | 2062 |
| apex-no | NO | 309 | 123 | 80 | 178 |
| nordicpower-no | NO | 244 | 48 | 52 | 191 |
| coore-no | NO | 605 | 107 | 134 | 393 |
| diggbox-no | NO | 757 | 395 | 0 | 327 |
| barebells-no | NO | 64 | 48 | 5 | 16 |
| gymgrossisten-se | SE | 2500 | 716 | 356 | 463 |
| bodystore-se | SE | 3280 | 784 | 89 | 298 |
| tillskottsbolaget | SE | 1336 | 423 | 512 | 820 |
| bodylab-se | SE | 105 | 42 | 15 | 25 |
| proteinbolaget | SE | 1418 | 369 | 80 | 103 |
| goldenathlete | SE | 1051 | 205 | 30 | 733 |
| mmsports | SE | 703 | 222 | 344 | 438 |
| sportkost | SE | 1938 | 1128 | 538 | 769 |
| bodypower | SE | 1767 | 1027 | 491 | 690 |
| tyngre | SE | 198 | 168 | 6 | 22 |
| life-se | SE | 847 | 144 | 53 | 260 |
| halsokostbolaget | SE | 1861 | 232 | 62 | 803 |
| halsafitnessbutiken | SE | 761 | 89 | 88 | 666 |
| barebells | SE | 64 | 53 | 3 | 11 |
| nocco | SE | 42 | 41 | 1 | 1 |
| starnutrition-se | SE | 95 | 44 | 1 | 51 |
| kungmarkatta | SE | 142 | 142 | 0 | 0 |
| bodystore-dk | DK | 1449 | 71 | 4 | 131 |
| bodylab-dk | DK | 109 | 45 | 43 | 58 |
| nutramino-dk | DK | 19 | 19 | 0 | 0 |
| helsam-dk | DK | 4188 | 2668 | 731 | 1271 |
| matas-dk | DK | 956 | 507 | 113 | 153 |
| myprotein-uk | UK | 545 | 228 | 135 | 250 |
| quest | US | 108 | 67 | 11 | 25 |
| fulfil | EU | 8 | 8 | 0 | 0 |
| reflex | UK | 43 | 0 | 0 | 43 |
| esn | EU | 129 | 0 | 0 | 129 |
| grenade | UK | 45 | 32 | 3 | 13 |
| cellucor | US | 81 | 0 | 0 | 81 |
| muscletech | US | 44 | 0 | 3 | 44 |
| applied-nutrition | UK | 238 | 0 | 0 | 238 |
| weider | EU | 10 | 0 | 0 | 10 |
| gorilla-mind | US | 45 | 0 | 0 | 45 |
| ghost | US | 262 | 0 | 0 | 262 |
| transparent-labs | US | 68 | 0 | 0 | 68 |
| optimum-nutrition | EU | 65 | 22 | 1 | 25 |
| dymatize | US | 31 | 25 | 5 | 6 |
| scitec | EU | 243 | 63 | 82 | 139 |
| legion | US | 53 | 0 | 0 | 53 |
| bodybuilding | US | 876 | 0 | 0 | 876 |

Products whose name or categories mention whey/protein powder/kreatin/casein and have per-100 g protein: 7568.

## Gaps and honest limits

- Kassalapp: 5,994 records saved (the priority pass stopped at its 3 h cap; about 154,000 queued products remain, mostly priority 2 "unknown" and food keywords). NorgesGruppen covers Meny/Spar/Joker (~39k EANs, 24k with nutrition); Kiwi is not covered. Only 600 NorgesGruppen products got the detail pass, so many lack ingredients. Resume Kassalapp with `scrapers/kassalapp_prio.py`.
- Duplicates are merged on a valid EAN (GTIN check digit), across shops and countries. A page that lists several flavours or sizes is ONE product that answers to all of its EANs (union of EANs, so a flavour EAN found in another shop joins the same product). Producer pages and grocery sources without EAN (Tine, Fjordland, Toro, Ringnes, Synnove, Kavli, Mills, Grandiosa, Nidar, Saetre, Q-Meieriene mostly; Nemlig, Rema 1000 DK, Kost1, Nordic Power, Barebells.no) stay separate products; they are not fuzzy-matched. Expect some products to exist twice because of that.
- Flavours share nutrition (Max decided). Every page that lists two or more flavours is one product with ONE table (the page default or the first one) and the flag `flavour_nutrition_shared_assumed`; real flavour differences of a few kcal or grams are not visible. The old per-flavour split of Gymgrossisten and Tights is gone.
- US brand sites (Quest, Cellucor, MuscleTech, Ghost, Transparent Labs, Gorilla Mind, Legion, Dymatize, Bodybuilding.com) publish per serving only or an image; where a gram serving and energy exist, per-100 g is derived and flagged `per100_derived_from_serving`. Image-only panels (Applied Nutrition 238, Ghost 177, Bodybuilding 213 and more) were not read: those products stay without nutrition. Their EANs are mostly missing, so they rarely merge with a Nordic shop.
- Norway relevance for US brand sites is false by definition used here (no Norwegian shop behind the page). Many of those brands are sold in Norwegian shops; the EAN merge makes such products relevant when a Norwegian source carries the same barcode.
- Not collected, with reasons: Prozis, Apotea (Cloudflare challenge), BSN, PhD Nutrition, Sci-MX, Foodspring, Clean Machine, Warrior, Olimp, Misfits, mmsports.no and nutravit.no (robots disallow), Healthwell.dk, Netto, Coop DK/SE, Lidl DK, Willys, Hemkop, Svenskt Kosttillskott (nutrition only as images), image-only Norwegian shops (getfit, gymbutikken, proteinspesialisten, tomminutrition, fitnessgrossisten, go-on-shop, kinsarvik, sunkost, vitusapotek, apotek1, farmasiet, med24), Nupo.dk, Med24.dk, Helsebixen.dk (not attempted). Fotex was sampled on food keywords only (281 of about 40,000 pages), Matas on supplement and food slugs only (2,699 of 63,000), ICA.se covers 5,061 of its 5,064 sitemap products but 4,226 of them have no nutrition table.
- Nemlig and Rema 1000 DK have no EAN, so their 9,000+ Danish grocery products never merge with the library; 2,121 Nemlig rows with an all-zero table were dropped as placeholders. Rema 1000 DK prints bare numbers; per 100 g or 100 ml is assumed (flag `per100_basis_assumed`).
- Open Food Facts global (89,463 records) was selected by category tags and by Sweden/Denmark; protein or supplement products with missing or unusual category tags are not in it. 3,600 of its records had no product name and keep a null name. Its values carry the usual crowd-sourced noise (3,700 kJ/kcal mismatches, 2,800 kcal/macro mismatches); it is lowest priority after pack-label and store pages. Name text may contain mojibake from OFF itself.
- Discontinued coverage is only what the Internet Archive and the live "hidden" pages gave: tights and gymgrossisten snapshots, bodystore, proteinfabrikken, myprotein, bulk and life.no. Archive snapshots often come in an older layout (no EAN, no nutrition). Bodylab.no archive pages load nutrition by script, so none were usable. 89 Gymgrossisten gone URLs had no snapshot at all.
- Non-food detection is a word list on name and the first three category levels, applied only to records with no nutrition. Non-food items without telltale words (a "Ribbed T-back" style garment) can still be in the library with `no_nutrition`; food-like supplement pages without a table are kept on purpose.
- Per-serving-only products (supplements, vitamins) are not converted to per 100 g unless they have energy and a serving of at least 5 g; `per_serving` holds their values with `serving_g` when the table gives a gram size.
- USDA branded rows are a filtered US set (supplement and protein brands): US EANs, English names, only merged when the barcode matches. Livsmedelsverket, Frida and USDA generic rows are tables, never Norway-relevant on their own.
- Swedish, Danish and Finnish label mapping was extended (Energi, Fett, mattat / maettede fedtsyrer, Kolhydrater / Kulhydrat, sockerarter, Fibrer / Kostfibre, Salt, Finnish rasva / hiilihydraatit / suola and joined labels such as "Kolhydrater -varav sockerarter"). About 18,000 distinct labels remain unmapped on purpose; the great majority are supplement actives (extracts, enzymes, probiotics, salts of minerals) and USDA / Frida detail rows, listed in `unmapped.json` and kept under `other_nutrients` / `per_100g_as_reported`. Mapped supplement codes: creatine, caffeine, taurine, beta-alanine, citrulline, carnitine, collagen, CoQ10, BCAA/EAA, amino acids.
- Vitamin A is stored as RAE/RE ug, vitamin E as alpha-tocopherol equivalents mg, niacin as mg; IU values are ignored in favour of the ug rows. Sources disagree on how these are measured; no conversions beyond units.
- Categories: the library keeps each source category list as-is. No unified category tree exists yet; Jev (TypeSafe) could classify the 217,000 names into one, but it needs a chat yes/no first and was not called.

## Folder size

| Folder | Size |
|---|---:|
| data/unified (products.jsonl, products.sqlite, dictionary) | 1.23 GB |
| data/raw (all collector output) | 2.09 GB |
| logs | 0 MB |
| scrapers + build | 1 MB |
| **macro-library total** | **3.33 GB** (cap 10 GB) |

Files: `products.jsonl` 588 MB, `products.sqlite` 639 MB.

## How to query

```sql
-- per-100 g macros for one barcode
select code, value, unit, source from nutrients where product_id='ean:7038010061844' and basis='per_100g';
-- all products with at least 20 g protein and under 150 kcal per 100 g
select name, brand, kcal, protein_g from products where protein_g>=20 and kcal<150 order by protein_g desc limit 20;
-- every source's opinion of one product
select source, url, kcal, protein_g, fat_g, carbs_g from product_sources where product_id='ean:7038010061844';
```
