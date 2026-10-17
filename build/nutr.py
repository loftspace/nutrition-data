"""Nutrient dictionary and label mapper for the macro library.

One stable code per nutrient; the code ends in its canonical unit (kcal, kj, _g, _mg, _ug).
map_label(label, unit, key=None, source=None) -> (code, factor, why)  or  (None, None, reason)
Values are converted into the canonical unit with `factor`.
A label that is not known is NEVER guessed: it goes to unmapped.json.
"""
import re
import unicodedata

# ---------------------------------------------------------------- dictionary
# (code, unit, group, name_en, name_nb, [aliases])
D = []


def add(code, unit, group, en, nb, aliases):
    D.append((code, unit, group, en, nb, aliases))


# energy
add('kcal', 'kcal', 'energy', 'Energy', 'Energi', ['kalorier', 'calories', 'calorie', 'kalorier kcal', 'kcal', 'kilokalorier', 'kalori', 'energi kcal', 'energy kcal', 'energie kcal', 'kalorier per 100g', 'energi kcal'])
add('kj', 'kj', 'energy', 'Energy (kJ)', 'Energi (kJ)', ['kj', 'kilojoule', 'energi kj', 'energy kj', 'energie kj', 'energi kj'])
# macros
add('protein_g', 'g', 'macro', 'Protein', 'Protein', ['protein', 'proteiner', 'proteins', 'protein total', 'proteiini', 'eggehvite', 'eiweiss', 'eiwitten', 'protein totalt', 'proteine'])
add('fat_g', 'g', 'macro', 'Fat, total', 'Fett, totalt', ['fett', 'fett totalt', 'totalt fett', 'fats', 'fett total', 'fat', 'total fat', 'total lipid fat', 'fat total', 'fedt', 'fedt total', 'fett i alt', 'fett sum', 'lipids', 'fat in total', 'fedt totalt', 'total fat nlea', 'fat nlea'])
add('sat_fat_g', 'g', 'macro', 'Saturated fat', 'Mettet fett', ['mettet fett', 'mettede fettsyrer', 'mettet', 'mettede', 'saturated fat', 'saturates', 'saturated', 'saturated fatty acids', 'mattat fett', 'mattade fettsyror', 'mattat', 'mattat fett g', 'mattet fett g', 'mættede fedtsyrer', 'mættet fedt', 'summa mattade fettsyror', 'sum saturated fatty acids', 'fatty acids total saturated', 'fettsyrer mettede', 'saturated fat g', 'sfa', 'fett mettet', 'fettsyrer mettet'])
add('mono_fat_g', 'g', 'macro', 'Monounsaturated fat', 'Enumettet fett', ['enumettet fett', 'enkelomattat fett', 'mono unsaturated fat', 'mono-unsaturated fat', 'enumettet fett g', 'enumettede fettsyrer', 'enumettet', 'monounsaturated fat', 'monounsaturates', 'monounsaturated', 'monounsaturated fatty acids', 'enkelomattade fettsyror', 'summa enkelomattade fettsyror', 'monoumættede fedtsyrer', 'sum monounsaturated fatty acids', 'fatty acids total monounsaturated', 'mufa', 'enumettede'])
add('poly_fat_g', 'g', 'macro', 'Polyunsaturated fat', 'Flerumettet fett', ['flerumettet fett', 'fleromattat fett', 'poly unsaturated fat', 'poly-unsaturated fat', 'flerumettet fett g', 'flerumettede fettsyrer', 'flerumettet', 'polyunsaturated fat', 'polyunsaturates', 'polyunsaturated', 'polyunsaturated fatty acids', 'fleromattade fettsyror', 'summa fleromattade fettsyror', 'polyumættede fedtsyrer', 'sum polyunsaturated fatty acids', 'fatty acids total polyunsaturated', 'pufa', 'flerumettede'])
add('trans_fat_g', 'g', 'macro', 'Trans fat', 'Transfett', ['transfett', 'transfettsyrer', 'trans fat', 'trans fatty acids', 'trans fats', 'sum trans fatty acids', 'fatty acids total trans', 'transfedtsyrer', 'transfettsyror'])
add('cholesterol_mg', 'mg', 'macro', 'Cholesterol', 'Kolesterol', ['kolesterol', 'cholesterol', 'kolesterol mg'])
add('carbs_g', 'g', 'macro', 'Carbohydrate', 'Karbohydrat', ['karbohydrat', 'karbohydrater', 'carbohydrate', 'carbohydrates', 'carbs', 'karbohydrater totalt', 'kolhydrater', 'kolhydrater tillgangliga', 'kulhydrat', 'kulhydrater', 'kullhydrater', 'kullhydrat', 'carbs total', 'karbohydrater total', 'kolhydrat g', 'karbohydrat total', 'carbohydrates total', 'carbohydrate total', 'carbohydrate by difference', 'available carbohydrate', 'available carbohydrates', 'total carbohydrates', 'total carbohydrate', 'karbohydrater tilgjengelige', 'karbohydrat tilgjengelig', 'tilgjengelig karbohydrat', 'karbo', 'kolhydrat', 'carbohydrate by summation', 'carbohydrates carbs', 'karbohydrater carbs', 'carbohydrat', 'carbohydrates g'])
add('sugars_g', 'g', 'macro', 'Sugars', 'Sukkerarter', ['sukkerarter', 'sukker', 'sugars', 'sugar', 'sukkerarter totalt', 'sockerarter', 'sockerarter totalt', 'sukkerarter i alt', 'total sugars', 'sugars total', 'sum sugars', 'mono di', 'mono+di', 'sukkerarter total', 'sukre', 'sukkerarter sum', 'sukkerater', 'hvor sukkerarter', 'sukkertarter', 'som sukkerarter', 'hvilke sukkerarter', 'sukkerter', 'sockerarter', 'sugar g', 'sukker g', 'sukker (g)', 'sukkerarter (g)', 'of which sugars', 'sugars g', 'sukker totalt', 'sukkerstoffer', 'sockerarter total'])
add('added_sugars_g', 'g', 'macro', 'Added sugars', 'Tilsatt sukker', ['tilsatt sukker', 'sukker tilsatt', 'added sugars', 'added sugar', 'sugars added', 'tillsatt socker', 'tilsat sukker', 'sukker tilsatt'])
add('free_sugars_g', 'g', 'macro', 'Free sugars', 'Fritt sukker', ['sukker fritt', 'free sugars', 'fritt socker', 'fritt sukker'])
add('polyols_g', 'g', 'macro', 'Polyols (sugar alcohols)', 'Polyoler', ['hvilke polyoler', 'sum sugar alcohols', 'polyoler', 'sukkeralkoholer', 'polyols', 'sukkeralkohol', 'polyol', 'sugar alcohols', 'total sugar alcohols', 'polyalkoholer', 'sockeralkoholer', 'polyoler sukkeralkoholer', 'sukkeralkohol polyoler', 'polyoler g'])
add('starch_g', 'g', 'macro', 'Starch', 'Stivelse', ['stivelse', 'starch', 'starch glycogen', 'starch/glycogen', 'starkelse', 'stivelse g', 'staerkelse', 'stivelse total'])
add('fibre_g', 'g', 'macro', 'Dietary fibre', 'Kostfiber', ['kostfiber', 'kostfibrer', 'kostfibre', 'fiber', 'fibre', 'kostfibre', 'fibre dietary', 'dietary fibre', 'dietary fiber', 'fiber total dietary', 'fiber, total dietary', 'kostfiber totalt', 'kostfibre totalt', 'fibrer', 'fibre g', 'dietary fibre total', 'total dietary fiber aoac 2011 25', 'kostfiber fiber', 'fiber kostfiber', 'fibre kostfibre', 'fiber g', 'kostfibre g', 'kostfiber g', 'fibre total', 'fiber totalt', 'kostfiber total'])
add('salt_g', 'g', 'macro', 'Salt', 'Salt', ['salt', 'salt nacl', 'nacl', 'koksalt', 'salt g', 'salt labelling', 'sodium chloride', 'salz', 'salt equivalent', 'salt ekvivalent', 'salt (nacl)'])
add('sodium_mg', 'mg', 'mineral', 'Sodium', 'Natrium', ['natrium', 'sodium', 'natrium na', 'sodium na', 'natrium (na)'])
add('water_g', 'g', 'macro', 'Water', 'Vann', ['vann', 'vatten', 'water', 'vand'])
add('alcohol_g', 'g', 'macro', 'Alcohol', 'Alkohol', ['alkohol', 'alcohol', 'alcohol ethyl', 'alcohol, ethyl'])
add('alcohol_vol_pct', '%vol', 'macro', 'Alcohol by volume', 'Alkohol (vol%)', ['alcohol vol', 'alkohol vol', 'abv'])
add('ash_g', 'g', 'macro', 'Ash', 'Aske', ['aske', 'aska', 'ash', 'crude ash'])
add('lactose_g', 'g', 'macro', 'Lactose', 'Laktose', ['laktose', 'lactose', 'laktos'])
add('fructose_g', 'g', 'macro', 'Fructose', 'Fruktose', ['fruktose', 'fructose', 'frukto'])
add('glucose_g', 'g', 'macro', 'Glucose', 'Glukose', ['glukose', 'glucose', 'druesukker'])
add('sucrose_g', 'g', 'macro', 'Sucrose', 'Sukrose', ['sukrose', 'sucrose', 'sackaros', 'rorsukker'])
add('maltose_g', 'g', 'macro', 'Maltose', 'Maltose', ['maltose'])
add('galactose_g', 'g', 'macro', 'Galactose', 'Galaktose', ['galaktose', 'galactose'])
add('monosaccharides_g', 'g', 'macro', 'Monosaccharides', 'Monosakkarider', ['monosackarider', 'sum monosaccharides', 'monosakkarider'])
add('disaccharides_g', 'g', 'macro', 'Disaccharides', 'Disakkarider', ['disackarider', 'sum disaccharides', 'disakkarider'])
add('erythritol_g', 'g', 'macro', 'Erythritol', 'Erytritol', ['erytritol', 'erythritol', 'erytritol g'])
add('beta_glucan_g', 'g', 'macro', 'Beta-glucan', 'Betaglukan', ['beta glucan', 'betaglukan', 'beta-glucan'])
add('fibre_soluble_g', 'g', 'macro', 'Fibre, soluble', 'Kostfiber, loselig', ['fiber soluble', 'fiber, soluble'])
add('fibre_insoluble_g', 'g', 'macro', 'Fibre, insoluble', 'Kostfiber, uloselig', ['fiber insoluble', 'fiber, insoluble'])
add('resistant_starch_g', 'g', 'macro', 'Resistant starch', 'Resistent stivelse', ['resistant starch'])
add('carbs_by_diff_g', 'g', 'macro', 'Carbohydrate by difference', 'Karbohydrat (differanse)', ['carbohydrate by difference'])
# fatty-acid groups
add('omega3_g', 'g', 'fatty_acid', 'Omega-3 fatty acids', 'Omega-3', ['totalt omega 3 fettsyrer', 'omega 3', 'omega3', 'omega-3', 'omega 3 fett', 'omega 3 fettsyrer', 'sum n 3 fatty acids', 'n 3 fettsyrer', 'omega-3 fett', 'omega 3 fatty acids', 'omega 3 fat'])
add('omega6_g', 'g', 'fatty_acid', 'Omega-6 fatty acids', 'Omega-6', ['omega 6', 'omega6', 'omega-6', 'omega 6 fett', 'omega 6 fettsyrer', 'sum n 6 fatty acids', 'omega 6 fatty acids', 'omega 6 fat'])
add('omega9_g', 'g', 'fatty_acid', 'Omega-9 fatty acids', 'Omega-9', ['omega 9', 'omega9', 'omega-9'])
add('epa_g', 'g', 'fatty_acid', 'EPA (20:5 n-3)', 'EPA', ['epa', 'eikosapentaensyre', 'eicosapentaenoic acid', 'eicosapentaenoic acid epa', 'epa c20 5', 'c20 5n 3 eikosapentaensyre epa', 'c20 5n 3 (eikosapentaensyre, epa)', 'epa (c20 5)', 'epa c20 5'])
add('dha_g', 'g', 'fatty_acid', 'DHA (22:6 n-3)', 'DHA', ['dha', 'dokosaheksaensyre', 'docosahexaenoic acid', 'docosahexaenoic acid dha', 'dha c22 6', 'c22 6n 3 dokosaheksaensyre dha', 'dha (c22 6)'])
add('dpa_g', 'g', 'fatty_acid', 'DPA (22:5 n-3)', 'DPA', ['dpa', 'dokosapentaensyre', 'dpa c22 5', 'c22 5n 3 dokosapentaensyre dpa'])
add('ala_fa_g', 'g', 'fatty_acid', 'Alpha-linolenic acid (18:3 n-3)', 'Alfa-linolensyre', ['alfa linolensyre', 'alpha linolenic acid', 'alfalinolensyre', 'alpha-linolenic-acid', 'ala', 'linolensyre', 'c18 3n 3 alfalinolensyre'])
add('linoleic_g', 'g', 'fatty_acid', 'Linoleic acid (18:2 n-6)', 'Linolsyre', ['linolsyre', 'linoleic acid', 'linolsyra', 'c18 2n 6 linolsyre'])
add('oleic_g', 'g', 'fatty_acid', 'Oleic acid (18:1)', 'Oljesyre', ['oljesyre', 'oleic acid', 'oljesyra', 'c18 1 sum oljesyre'])
add('arachidonic_g', 'g', 'fatty_acid', 'Arachidonic acid (20:4 n-6)', 'Arakidonsyre', ['arakidonsyre', 'arachidonic acid', 'arakidonsyra', 'c20 4n 6 arakidonsyre'])
add('gla_g', 'g', 'fatty_acid', 'Gamma-linolenic acid (18:3 n-6)', 'Gammalinolensyre', ['gamma linolenic acid', 'gamma-linolenic-acid', 'gla'])
add('erucic_g', 'g', 'fatty_acid', 'Erucic acid (22:1)', 'Erukasyre', ['erucic acid', 'erucic-acid', 'erukasyre'])
add('cla_g', 'g', 'fatty_acid', 'CLA (conjugated linoleic acid)', 'CLA', ['cla', 'conjugated linoleic acid'])
# vitamins
add('vit_a_ug', 'ug', 'vitamin', 'Vitamin A (RAE)', 'Vitamin A', ['vitamin a', 'vitamin a rae', 'vitamin a (rae)', 'a vitamin', 'vit a', 'vitamin a re', 'vitamin a (re)', 'vitamin a retinol equivalents', 'vitamin a, rae', 'vitamin a retinolekvivalenter', 'retinolekvivalenter', 'vit a re'])
add('retinol_ug', 'ug', 'vitamin', 'Retinol', 'Retinol', ['retinol'])
add('beta_carotene_ug', 'ug', 'vitamin', 'Beta-carotene', 'Betakaroten', ['betakaroten', 'beta karoten', 'beta carotene', 'beta-carotene', 'b karo', 'carotene beta', 'betakaroten β karoten', 'betakaroten/β karoten', 'beta caroten'])
add('vit_d_ug', 'ug', 'vitamin', 'Vitamin D', 'Vitamin D', ['vitamin d', 'vitamin d3', 'd vitamin', 'vit d', 'vitamin d d2 d3', 'vitamin d (d2 + d3)', 'vitamin d inkl 25 oh d3', 'vitamin d3 cholecalciferol', 'd3 vitamin', 'd3-vitamin', 'vitamin d2', 'ergocalciferol', 'cholecalciferol', 'kolekalsiferol', 'vitamin d d2 + d3', 'vitamin d (d2 + d3), international units'])
add('vit_e_mg', 'mg', 'vitamin', 'Vitamin E (alpha-tocopherol equiv.)', 'Vitamin E', ['vitamin e', 'e vitamin', 'vit e', 'vitamin e alpha tocopherol', 'alpha tocopherol', 'alfa tocopherol', 'vitamin e (alpha-tocopherol)', 'alpha-tocopherol', 'vitamin e alpha te', 'tocopherol', 'vitamin e ate', 'vitamin e (label entry primarily)', 'alfa tocoferol', 'vitamin e (alfa-te)', 'vitamin e d alfa tocopherol'])
add('vit_k_ug', 'ug', 'vitamin', 'Vitamin K', 'Vitamin K', ['vitamin k', 'k vitamin', 'vit k', 'phylloquinone', 'vitamin k phylloquinone', 'vitamin k (phylloquinone)', 'vitamin k1', 'vitamin k1 phylloquinone', 'fyllokinon'])
add('vit_k2_ug', 'ug', 'vitamin', 'Vitamin K2 (menaquinone)', 'Vitamin K2', ['vitamin k2', 'menaquinone', 'vitamin k menaquinone 4', 'menakinon', 'k2 vitamin', 'vitamin k2 mk 7', 'vitamin k2 (mk-7)', 'k2 mk 7'])
add('vit_c_mg', 'mg', 'vitamin', 'Vitamin C', 'Vitamin C', ['vitamin c', 'c vitamin', 'c-vitamin', 'vit c', 'vitamin c askorbinsyre', 'vitamin c (askorbinsyre)', 'ascorbic acid', 'vitamin c total ascorbic acid', 'vitamin c, total ascorbic acid', 'askorbinsyre', 'c vitamin askorbinsyre', 'l askorbinsyre'])
add('vit_b1_mg', 'mg', 'vitamin', 'Thiamin (vitamin B1)', 'Tiamin (B1)', ['tiamin', 'thiamin', 'thiamine', 'vitamin b1', 'vitamin b1 tiamin', 'vitamin b1 (tiamin)', 'thiamin vitamin b1', 'thiamin (vitamin b1)', 'b1', 'b1 vitamin', 'b1 tiamin', 'vit b1', 'thiamin hcl', 'tiamin vitamin b1', 'vitamin b 1', 'thiamine hcl', 'tiamin (vitamin b1)', 'tiamin hydroklorid'])
add('vit_b2_mg', 'mg', 'vitamin', 'Riboflavin (vitamin B2)', 'Riboflavin (B2)', ['riboflavin', 'vitamin b2', 'vitamin b2 riboflavin', 'vitamin b2 (riboflavin)', 'riboflavin vitamin b2', 'riboflavin (vitamin b2)', 'b2', 'b2 vitamin', 'vit b2', 'b2 riboflavin', 'riboflavin vitamin b2', 'vitamin b 2', 'riboflavine'])
add('vit_b3_mg', 'mg', 'vitamin', 'Niacin (vitamin B3)', 'Niacin (B3)', ['niacin', 'vitamin b3', 'vitamin b3 niacin', 'vitamin b3 (niacin)', 'b3', 'niacin nicotinsyre', 'nikotinsyre', 'nicotinamide', 'nikotinamid', 'vitamin pp', 'niacin vitamin b3', 'niacin (vitamin b3)', 'vit b3', 'b3 niacin', 'niacin b3', 'niacin ne', 'vitamin b3 niacin ne', 'nicotinic acid', 'nikotinamid niacin'])
add('vit_b3_ne_mg', 'mg', 'vitamin', 'Niacin equivalents', 'Niacinekvivalenter', ['niacinekvivalenter', 'niacin equivalents', 'niacin equivalent', 'niaeq', 'niacinekvivalent'])
add('vit_b5_mg', 'mg', 'vitamin', 'Pantothenic acid (vitamin B5)', 'Pantotensyre (B5)', ['pantotensyre', 'patotensyre', 'pantothenic acid', 'vitamin b5', 'pantothensyre', 'b5', 'pantotensyre vitamin b5', 'vitamin b5 pantotensyre', 'vitamin b5 (pantotensyre)', 'pantothenic', 'pantothenic acid vitamin b5', 'vitamin b5 pantothenic acid', 'pantotensyre (vitamin b5)', 'pantotensyre b5', 'pantothenic acid (b5)', 'pantotensyra', 'vit b5', 'calcium pantothenate', 'kalsium pantotenat', 'pantotenat', 'pantothenat'])
add('vit_b6_mg', 'mg', 'vitamin', 'Vitamin B6', 'Vitamin B6', ['vitamin b6', 'viamin b6', 'vitamin b 6', 'b6', 'b6 vitamin', 'pyridoksin', 'pyridoxine', 'vitamin b6 pyridoksin', 'vitamin b6 (pyridoksin)', 'vit b6', 'vitamin b6 pyridoxine', 'pyridoxine hcl', 'vitamin b6 (pyridoxin)', 'pyridoxin', 'vitamin b6 pyridoxin', 'b6 pyridoksin', 'vitamin b-6', 'pyridoksinhydroklorid'])
add('vit_b7_ug', 'ug', 'vitamin', 'Biotin (vitamin B7)', 'Biotin (B7)', ['biotin', 'vitamin b7', 'b7', 'vitamin h', 'biotin vitamin b7', 'vit b7', 'd biotin'])
add('vit_b9_ug', 'ug', 'vitamin', 'Folate (vitamin B9)', 'Folat (B9)', ['folat', 'folsyra', 'folate', 'folacin', 'folsyre', 'folic acid', 'vitamin b9', 'vitamin b9 folat', 'vitamin b9 (folat)', 'folat totalt', 'folat, totalt', 'folate, total', 'folate total', 'folate dfe', 'folate, dfe', 'folat dfe', 'b9', 'folates', 'folates total folates', 'folate food', 'folate, food', 'folsyre vitamin b9', 'folat (vitamin b9)', 'folat folsyre', 'vit b9', 'quatrefolic', 'metylfolat', 'l 5 mthf', '5 mthf', 'folate (folic acid)', 'folinsyre', 'folic acid (b9)', 'folate vitamin b9', 'vitamin b9 (folic acid)', 'vitamin b9 folic acid'])
add('vit_b12_ug', 'ug', 'vitamin', 'Vitamin B12', 'Vitamin B12', ['vitamin b12', 'vitamin b 12', 'b12', 'b12 vitamin', 'kobalamin', 'cobalamin', 'vitamin b12 kobalamin', 'vitamin b12 (kobalamin)', 'vit b12', 'vitamin b12 cobalamin', 'vitamin b-12', 'vitamin b12 cobalamin', 'cyanokobalamin', 'cyanocobalamin', 'metylkobalamin', 'methylcobalamin', 'b12 kobalamin', 'vitamin b12 (cobalamin)'])
add('choline_mg', 'mg', 'vitamin', 'Choline', 'Kolin', ['kolin', 'choline', 'choline total', 'choline, total', 'cholin'])
add('betaine_mg', 'mg', 'vitamin', 'Betaine', 'Betain', ['betain', 'betaine', 'betaine anhydrous', 'betain anhydrous', 'trimethylglycine', 'tmg'])
add('inositol_mg', 'mg', 'vitamin', 'Inositol', 'Inositol', ['inositol', 'myo inositol'])
add('lutein_ug', 'ug', 'vitamin', 'Lutein + zeaxanthin', 'Lutein', ['lutein', 'lutein zeaxanthin', 'lutein + zeaxanthin', 'lutein zeaxantin'])
add('lycopene_ug', 'ug', 'vitamin', 'Lycopene', 'Lykopen', ['lycopene', 'lykopen'])
# minerals
add('calcium_mg', 'mg', 'mineral', 'Calcium', 'Kalsium', ['kalsium', 'calcium', 'kalsium ca', 'calcium ca', 'kalcium', 'kalcium ca', 'calcium, ca', 'kalsium (ca)', 'kalsiumkarbonat', 'kalsiumcitrat'])
add('iron_mg', 'mg', 'mineral', 'Iron', 'Jern', ['jern', 'iron', 'jern fe', 'iron fe', 'jarn', 'jarn fe', 'iron, fe', 'jern (fe)'])
add('magnesium_mg', 'mg', 'mineral', 'Magnesium', 'Magnesium', ['magnesium', 'magnesium mg', 'magnesium, mg', 'magnesium (mg)'])
add('phosphorus_mg', 'mg', 'mineral', 'Phosphorus', 'Fosfor', ['fosfor', 'phosphorus', 'fosfor p', 'phosphorus p', 'phosphorus, p', 'fosfor (p)', 'fosfat'])
add('potassium_mg', 'mg', 'mineral', 'Potassium', 'Kalium', ['kalium', 'potassium', 'kalium k', 'potassium k', 'potassium, k', 'kalium (k)'])
add('zinc_mg', 'mg', 'mineral', 'Zinc', 'Sink', ['sink', 'zinc', 'zink', 'sink zn', 'zink zn', 'zinc zn', 'zinc, zn', 'sink (zn)'])
add('copper_mg', 'mg', 'mineral', 'Copper', 'Kobber', ['kobber', 'copper', 'koppar', 'kobber cu', 'copper cu', 'copper, cu', 'kobber (cu)', 'koppar cu'])
add('manganese_mg', 'mg', 'mineral', 'Manganese', 'Mangan', ['mangan', 'manganese', 'mangan mn', 'manganese mn', 'manganese, mn', 'mangan (mn)'])
add('selenium_ug', 'ug', 'mineral', 'Selenium', 'Selen', ['selen', 'selenium', 'selen se', 'selenium se', 'selenium, se', 'selen (se)'])
add('iodine_ug', 'ug', 'mineral', 'Iodine', 'Jod', ['jod', 'iodine', 'jod i', 'iodine i', 'iodine, i', 'jod (i)', 'jodid', 'jod, i'])
add('chromium_ug', 'ug', 'mineral', 'Chromium', 'Krom', ['krom', 'chromium', 'chrom', 'krom cr', 'chromium cr', 'chromium, cr'])
add('molybdenum_ug', 'ug', 'mineral', 'Molybdenum', 'Molybden', ['molybden', 'molydben', 'molybdenum', 'molybden mo', 'molybdenum mo', 'molybdenum, mo'])
add('fluoride_mg', 'mg', 'mineral', 'Fluoride', 'Fluorid', ['fluorid', 'fluoride', 'fluor', 'fluoride, f', 'fluorid f'])
add('chloride_mg', 'mg', 'mineral', 'Chloride', 'Klorid', ['klorid', 'chloride', 'chlorine', 'chlorine, cl', 'klor', 'chloride cl', 'cld', 'cloruro'])
add('boron_ug', 'ug', 'mineral', 'Boron', 'Bor', ['boron', 'boron, b', 'bor'])
add('silicon_mg', 'mg', 'mineral', 'Silicon', 'Silisium', ['silicon', 'silisium', 'silica', 'silika', 'kisel'])
add('sulfur_mg', 'mg', 'mineral', 'Sulfur', 'Svovel', ['sulfur', 'sulfur, s', 'svovel', 'sulfate', 'sulphate', 'sulfat'])
add('bicarbonate_mg', 'mg', 'mineral', 'Bicarbonate', 'Bikarbonat', ['bicarbonate', 'bikarbonat', 'hydrogenkarbonat'])
# amino acids
for code, en, nb, al in [
    ('leucine', 'Leucine', 'Leucin', ['leucin', 'leucine', 'l leucine', 'l leucin']),
    ('isoleucine', 'Isoleucine', 'Isoleucin', ['isoleucin', 'isoleucine', 'l isoleucine', 'l isoleucin']),
    ('valine', 'Valine', 'Valin', ['valin', 'valine', 'l valine', 'l valin']),
    ('lysine', 'Lysine', 'Lysin', ['lysin', 'lysine', 'l lysine', 'l lysin']),
    ('methionine', 'Methionine', 'Metionin', ['metionin', 'methionine', 'l methionine', 'l metionin']),
    ('phenylalanine', 'Phenylalanine', 'Fenylalanin', ['fenylalanin', 'phenylalanine', 'l phenylalanine', 'l fenylalanin', 'phenylalanin']),
    ('threonine', 'Threonine', 'Treonin', ['treonin', 'threonine', 'l threonine', 'l treonin', 'threonin']),
    ('tryptophan', 'Tryptophan', 'Tryptofan', ['tryptofan', 'tryptophan', 'l tryptophan', 'l tryptofan']),
    ('histidine', 'Histidine', 'Histidin', ['histidin', 'histidine', 'l histidine', 'l histidin']),
    ('arginine', 'Arginine', 'Arginin', ['arginin', 'arginine', 'l arginine', 'l arginin']),
    ('alanine', 'Alanine', 'Alanin', ['alanin', 'alanine', 'l alanine', 'l alanin']),
    ('aspartic_acid', 'Aspartic acid', 'Asparaginsyre', ['asparaginsyre', 'aspartic acid', 'aspartinsyre', 'asparaginsyra', 'asp']),
    ('cystine', 'Cystine/cysteine', 'Cystin', ['cystin', 'cystine', 'cystein', 'cysteine', 'l cystein', 'l cysteine', 'cystein cystin', 'l cystin', 'n acetyl cystein', 'nac']),
    ('glutamic_acid', 'Glutamic acid', 'Glutaminsyre', ['glutaminsyre', 'glutamic acid', 'glutaminsyra', 'glutamat']),
    ('glycine', 'Glycine', 'Glycin', ['glycin', 'glycine', 'l glycine', 'l glycin']),
    ('proline', 'Proline', 'Prolin', ['prolin', 'proline', 'l proline', 'l prolin']),
    ('serine', 'Serine', 'Serin', ['serin', 'serine', 'l serine', 'l serin']),
    ('tyrosine', 'Tyrosine', 'Tyrosin', ['tyrosin', 'tyrosine', 'l tyrosine', 'l tyrosin']),
    ('glutamine', 'Glutamine', 'Glutamin', ['glutamin', 'glutamine', 'l glutamine', 'l glutamin']),
    ('hydroxyproline', 'Hydroxyproline', 'Hydroksyprolin', ['hydroxyproline', 'hydroksyprolin']),
]:
    add(code + '_g', 'g', 'amino_acid', en, nb, al)
add('bcaa_g', 'g', 'amino_acid', 'BCAA (sum)', 'BCAA', ['total bcaa', 'total mengde bcaa', 'bcaa totalt', 'bcaa', 'bcaa 2 1 1', 'bcaas', 'bcaa total', 'branched chain amino acids', 'bcaa (leucin, isoleucin, valin)', 'forgrenede aminosyrer', 'bcaa leucine isoleucine valine'])
add('eaa_g', 'g', 'amino_acid', 'EAA (sum essential amino acids)', 'EAA', ['eaa', 'eaas', 'essential amino acids', 'essensielle aminosyrer', 'sum essential amino acids', 'sum essensielle aminosyrer'])
# supplement-style actives (only the common, unambiguous ones)
add('creatine_g', 'g', 'supplement', 'Creatine', 'Kreatin', ['kreatin', 'creatine', 'kreatin monohydrat', 'creatine monohydrate', 'kreatinmonohydrat', 'creapure', 'creatin', 'creatine monohydrate creapure', 'kreatinmonohydrat creapure', 'creatine hcl'])
add('caffeine_mg', 'mg', 'supplement', 'Caffeine', 'Koffein', ['koffein', 'caffeine', 'koffein anhydrous', 'caffeine anhydrous', 'coffein'])
add('taurine_mg', 'mg', 'supplement', 'Taurine', 'Taurin', ['taurin', 'taurine', 'l taurin', 'l taurine'])
add('beta_alanine_g', 'g', 'supplement', 'Beta-alanine', 'Beta-alanin', ['beta alanin', 'beta alanine', 'betaalanin', 'betaalanine', 'beta-alanine', 'carnosyn'])
add('citrulline_g', 'g', 'supplement', 'Citrulline', 'Citrullin', ['citrullin', 'citrulline', 'l citrullin', 'l citrulline', 'citrullin malat', 'citrulline malate', 'l-citrulline', 'l citrullin malat', 'l citrulline malate'])
add('carnitine_mg', 'mg', 'supplement', 'L-carnitine', 'L-karnitin', ['karnitin', 'carnitine', 'l karnitin', 'l carnitine', 'l-carnitine', 'acetyl l karnitin', 'acetyl l carnitine', 'l karnitin tartrat', 'l carnitine tartrate'])
add('collagen_g', 'g', 'supplement', 'Collagen', 'Kollagen', ['kollagen', 'collagen', 'collagen peptides', 'kollagenpeptider', 'hydrolysert kollagen', 'hydrolyzed collagen', 'kollagen peptider'])
add('coq10_mg', 'mg', 'supplement', 'Coenzyme Q10', 'Koenzym Q10', ['coq10', 'q10', 'koenzym q10', 'coenzyme q10', 'ubiquinone', 'koenzym q10 ubiquinon', 'ubiquinol'])
add('theobromine_mg', 'mg', 'supplement', 'Theobromine', 'Teobromin', ['theobromine', 'teobromin'])
add('glucosamine_mg', 'mg', 'supplement', 'Glucosamine', 'Glukosamin', ['glukosamin', 'glucosamine', 'glukosamin sulfat', 'glucosamine sulfate', 'glukosaminsulfat', 'glucosamine sulphate'])
add('msm_mg', 'mg', 'supplement', 'MSM', 'MSM', ['msm', 'metylsulfonylmetan', 'methylsulfonylmethane'])
add('phytosterols_mg', 'mg', 'supplement', 'Phytosterols', 'Fytosteroler', ['phytosterols', 'fytosteroler', 'plantesteroler'])
add('hmb_g', 'g', 'supplement', 'HMB', 'HMB', ['hmb', 'hmb calcium', 'beta hydroxy beta methylbutyrate'])

DICT = {c: dict(code=c, unit=u, group=g, name_en=en, name_nb=nb) for (c, u, g, en, nb, al) in D}
ALIAS = {}
for (c, u, g, en, nb, al) in D:
    for a in al:
        ALIAS.setdefault(a, set()).add(c)


# --------------------------------------------------------------- fatty acid chains
FA_ALIASES = {'fa_4_0_g': ['butyric acid', 'smorsyre', 'butyrsyre', 'smorsyra'], 'fa_6_0_g': ['caproic acid', 'kapronsyre', 'kapronsyra'], 'fa_8_0_g': ['caprylic acid', 'kaprylsyre', 'kaprylsyra'],
              'fa_10_0_g': ['capric acid', 'kaprinsyre', 'kaprinsyra'], 'fa_12_0_g': ['lauric acid', 'laurinsyre', 'laurinsyra'], 'fa_14_0_g': ['myristic acid', 'myristinsyre', 'myristinsyra'],
              'fa_16_0_g': ['palmitic acid', 'palmitinsyre', 'palmitinsyra'], 'fa_18_0_g': ['stearic acid', 'stearinsyre', 'stearinsyra'], 'fa_20_0_g': ['arachidic acid', 'arakinsyre', 'arakidinsyra'],
              'fa_16_1_g': ['palmitoleic acid', 'palmitoljesyra', 'palmitoleinsyre'], 'fa_22_0_g': ['behenic acid', 'behensyre']}

def _fa_code(n, d, extra=''):
    return 'fa_%s_%s%s_g' % (n, d, extra)


FA_NAMES = {
    '4:0': 'Butyric acid', '6:0': 'Caproic acid', '8:0': 'Caprylic acid', '10:0': 'Capric acid', '12:0': 'Lauric acid',
    '14:0': 'Myristic acid', '15:0': 'Pentadecanoic acid', '16:0': 'Palmitic acid', '17:0': 'Margaric acid', '18:0': 'Stearic acid',
    '20:0': 'Arachidic acid', '22:0': 'Behenic acid', '24:0': 'Lignoceric acid', '14:1': 'Myristoleic acid', '16:1': 'Palmitoleic acid',
    '18:1': 'Oleic acid (sum)', '20:1': 'Gadoleic acid', '22:1': 'Erucic acid (sum)', '18:2': 'Linoleic acid (sum)', '18:3': 'Linolenic acid (sum)',
    '18:4': 'Stearidonic acid', '20:3': 'Eicosatrienoic acid', '20:4': 'Arachidonic acid (sum)', '22:5': 'Docosapentaenoic acid',
}


def fa_from_label(label):
    """Specific fatty acid chain by label like 'SFA 16:0', 'C18:1', 'Palmitinsyre C16:0'. Returns code or None."""
    l = label.lower()
    if re.search(r'\b(trans|tfa)\b', l) or re.search(r'\btfa\b', l) or ' t,' in l or l.endswith(' t'):
        return None
    m = re.search(r'(?<![\d.])c?(\d{1,2}):(\d{1,2})', l)
    if not m:
        return None
    n, d = int(m.group(1)), int(m.group(2))
    tail = l[m.end():]
    if re.search(r'n-?3', l) or '(epa)' in l or '(dha)' in l or '(ala)' in l or '(dpa)' in l:
        if (n, d) == (20, 5): return 'epa_g'
        if (n, d) == (22, 6): return 'dha_g'
        if (n, d) == (22, 5): return 'dpa_g'
        if (n, d) == (18, 3): return 'ala_fa_g'
        if (n, d) == (18, 4): return 'fa_18_4_n3_g'
        if (n, d) == (20, 4): return 'fa_20_4_n3_g'
        if (n, d) == (20, 3): return 'fa_20_3_n3_g'
        return None
    if re.search(r'n-?6', l):
        if (n, d) == (18, 2): return 'linoleic_g'
        if (n, d) == (20, 4): return 'arachidonic_g'
        if (n, d) == (18, 3): return 'gla_g'
        if (n, d) == (20, 3): return 'fa_20_3_n6_g'
        if (n, d) == (20, 2): return 'fa_20_2_n6_g'
        return None
    if re.search(r'n-?9|n-?7|n-?5|n-?11', l):
        if (n, d) == (18, 1) and re.search(r'n-?9', l):
            return 'oleic_g'
        if (n, d) in ((16, 1), (14, 1), (20, 1), (22, 1), (24, 1)):
            return _fa_code(n, d)
        return None
    if re.search(r'\bcla', l):
        return None
    # skip positional/isomer variants (USDA 'MUFA 18:1 c', 'PUFA 18:2 i', 'PUFA 20:3 c')
    if re.search(r'\s(c|i|t|c,c|c,c,c)\b', tail):
        return None
    if (n, d) == (18, 2): return 'linoleic_g'
    if (n, d) == (18, 1): return 'oleic_g'
    if (n, d) == (20, 4): return 'arachidonic_g'
    if (n, d) == (20, 5): return 'epa_g'
    if (n, d) == (22, 6): return 'dha_g'
    if (n, d) == (22, 5): return 'dpa_g'
    if (n, d) == (18, 3): return 'ala_fa_g'
    return _fa_code(n, d)


for _k, _v in FA_NAMES.items():
    n, d = _k.split(':')
    _c = _fa_code(n, d)
    if _c not in DICT:
        DICT[_c] = dict(code=_c, unit='g', group='fatty_acid', name_en=_v + ' (%s)' % _k, name_nb=_v + ' (%s)' % _k)
for _c, _n in [('fa_18_4_n3_g', 'Stearidonic acid (18:4 n-3)'), ('fa_20_4_n3_g', 'Eicosatetraenoic acid (20:4 n-3)'),
               ('fa_20_3_n3_g', 'Eicosatrienoic acid (20:3 n-3)'), ('fa_20_3_n6_g', 'DGLA (20:3 n-6)'), ('fa_20_2_n6_g', 'Eicosadienoic acid (20:2 n-6)')]:
    DICT[_c] = dict(code=_c, unit='g', group='fatty_acid', name_en=_n, name_nb=_n)
# other fatty-acid chains seen in USDA/Frida get added on demand
def ensure_fa(code):
    if code not in DICT:
        m = re.match(r'fa_(\d+)_(\d+)_g$', code)
        DICT[code] = dict(code=code, unit='g', group='fatty_acid', name_en='Fatty acid %s:%s' % (m.group(1), m.group(2)), name_nb='Fettsyre %s:%s' % (m.group(1), m.group(2)))


for _c, _al in FA_ALIASES.items():
    for _a in _al:
        ALIAS.setdefault(_a, set()).add(_c)

# ------------------------------------------------------------- key overrides
# (source, key) -> code | None (None = deliberately ignored duplicate / non-nutrient)
USDA = {
    '208': 'kcal', '957': 'kcal', '958': 'kcal', '268': 'kj', '203': 'protein_g', '204': 'fat_g', '298': 'fat_g', '205': 'carbs_g', '205.2': None, '284': None,
    '269': 'sugars_g', '269.3': 'sugars_g', '539': 'added_sugars_g', '291': 'fibre_g', '293': 'fibre_g', '295': 'fibre_soluble_g', '297': 'fibre_insoluble_g',
    '307': 'sodium_mg', '375': 'salt_g', '606': 'sat_fat_g', '645': 'mono_fat_g', '646': 'poly_fat_g', '605': 'trans_fat_g', '601': 'cholesterol_mg',
    '255': 'water_g', '207': 'ash_g', '221': 'alcohol_g', '209': 'starch_g', '299': 'polyols_g', '212': 'fructose_g', '211': 'glucose_g', '210': 'sucrose_g',
    '213': 'lactose_g', '214': 'maltose_g', '287': 'galactose_g', '283': 'resistant_starch_g', '2058': 'beta_glucan_g',
    '301': 'calcium_mg', '303': 'iron_mg', '304': 'magnesium_mg', '305': 'phosphorus_mg', '306': 'potassium_mg', '309': 'zinc_mg', '312': 'copper_mg',
    '315': 'manganese_mg', '317': 'selenium_ug', '314': 'iodine_ug', '310': 'chromium_ug', '316': 'molybdenum_ug', '313': 'fluoride_mg', '302': 'chloride_mg', '354': 'boron_ug', '308': 'sulfur_mg',
    '401': 'vit_c_mg', '320': 'vit_a_ug', '318': None, '319': 'retinol_ug', '321': 'beta_carotene_ug', '328': 'vit_d_ug', '324': None, '326': None, '325': None, '327': None,
    '323': 'vit_e_mg', '394': 'vit_e_mg', '959': 'vit_e_mg', '340': None, '430': 'vit_k_ug', '428': 'vit_k2_ug', '429': None,
    '404': 'vit_b1_mg', '405': 'vit_b2_mg', '406': 'vit_b3_mg', '410': 'vit_b5_mg', '415': 'vit_b6_mg', '416': 'vit_b7_ug', '417': 'vit_b9_ug', '435': None, '432': None, '431': None, '418': 'vit_b12_ug',
    '578': None, '573': None, '421': 'choline_mg', '454': 'betaine_mg', '422': 'inositol_mg', '337': 'lycopene_ug', '338': 'lutein_ug',
    '262': 'caffeine_mg', '263': 'theobromine_mg', '529': 'taurine_mg', '636': 'phytosterols_mg', '528': 'glutamine_g', '521': 'hydroxyproline_g',
    '501': 'tryptophan_g', '502': 'threonine_g', '503': 'isoleucine_g', '504': 'leucine_g', '505': 'lysine_g', '506': 'methionine_g', '507': 'cystine_g', '526': 'cystine_g',
    '508': 'phenylalanine_g', '509': 'tyrosine_g', '510': 'valine_g', '511': 'arginine_g', '512': 'histidine_g', '513': 'alanine_g', '514': 'aspartic_acid_g',
    '515': 'glutamic_acid_g', '516': 'glycine_g', '517': 'proline_g', '518': 'serine_g', '202': None, '227': None,
}
# taurine in USDA is g -> taurine_mg handled by factor via unit conversion (canonical mg)
FRIDA = {
    '137': None, '356': None, '316': 'kj', '359': 'kcal', '318': 'carbs_g', '172': None, '170': 'carbs_by_diff_g', '168': 'fibre_g', '141': 'fat_g',
    '19': 'alcohol_g', '327': 'salt_g', '33': 'ash_g', '265': None, '268': 'water_g', '201': 'sodium_mg', '443': None, '417': 'added_sugars_g', '418': 'free_sugars_g',
    '243': 'starch_g', '252': None, '218': None, '317': 'protein_g', '421': None, '245': 'sugars_g', '300': None, '219': None, '248': 'sat_fat_g', '247': 'mono_fat_g',
    '251': 'poly_fat_g', '249': 'omega3_g', '250': 'omega6_g', '261': 'trans_fat_g', '12': 'vit_a_ug', '115': 'cholesterol_mg', '225': 'retinol_ug', '37': 'vit_b1_mg',
    '203': 'vit_b3_ne_mg', '39': 'vit_b2_mg', '140': None, '303': 'beta_carotene_ug', '116': 'choline_mg', '294': 'vit_b3_mg', '126': 'vit_d_ug', '47': 'vit_c_mg',
    '40': 'vit_b6_mg', '38': 'vit_b12_ug', '135': 'vit_e_mg', '340': None, '143': 'vit_b9_ug', '276': None, '430': 'eaa_g', '431': None, '128': None, '164': 'vit_k_ug', '175': None,
    '442': None, '42': 'vit_b7_ug', '18': 'disaccharides_g', '228': 'sucrose_g', '191': 'monosaccharides_g', '149': 'glucose_g', '146': 'fructose_g', '179': 'lactose_g', '185': 'maltose_g',
    '145': None, '363': None, '422': None, '24': None, '400': 'hydroxyproline_g', '210': 'vit_b5_mg',
}
MV = {'Mono+Di': 'sugars_g', 'Sukker': 'added_sugars_g', 'SUGAN': 'free_sugars_g', 'Karbo': 'carbs_g', 'Vit A RE': None, 'Vit A': 'vit_a_ug', 'Niacin': 'vit_b3_mg', 'NIAEQ': 'vit_b3_ne_mg',
      'Alko': 'alcohol_g', 'NaCl': 'salt_g', 'Na': 'sodium_mg', 'C18:1': 'oleic_g', 'C16:1': 'fa_16_1_g'}
LV = {'ENERC': 'kcal', 'CHO': 'carbs_g', 'SUGAR': 'sugars_g', 'SUGAD': 'added_sugars_g', 'SUGFR': 'free_sugars_g', 'NA': 'sodium_mg', 'NACL': 'salt_g', 'NIA': 'vit_b3_mg', 'NIAEQ': 'vit_b3_ne_mg',
      'VITA': 'vit_a_ug', 'VITD': 'vit_d_ug', 'VITD_x': None, 'FOL': 'vit_b9_ug', 'WASTE': None, 'WHOLET': None, 'WHOLE_x': None, 'THIACLHCL': 'vit_b1_mg', 'RETOL': 'retinol_ug',
      'F4-10:0': None, 'CARTBTOT': 'beta_carotene_ug', 'F22:5': 'dpa_g', 'F20:5': 'epa_g', 'F22:6': 'dha_g', 'F20:4': 'arachidonic_g', 'F18:3': 'ala_fa_g', 'F18:2': 'linoleic_g', 'F18:1': 'oleic_g',
      'FAMS': 'mono_fat_g', 'FAPU': 'poly_fat_g', 'FASAT': 'sat_fat_g', 'FAT': 'fat_g', 'FIBT': 'fibre_g', 'PROT': 'protein_g', 'ALC': 'alcohol_g', 'ASH': 'ash_g', 'WATER': 'water_g',
      'DISAC': 'disaccharides_g', 'MNSAC': 'monosaccharides_g', 'SUCS': 'sucrose_g', 'CHORL': 'cholesterol_mg'}
OVERRIDES = {'usda-fdc': USDA, 'frida-dk': FRIDA, 'matvaretabellen': MV, 'livsmedelsverket': LV}

IGNORE_EXTRA = {'naringsvarde', 'indhold', 'innehall per', 'naringsdeklaration', 'x', 'x_', 'x__2', 'x__3', 'anbefalet daglig dosis', 'per daily serving', 'total', 'which are in total',
                '100 ml ferdigdrikke', '0 g', '<0,5 g', 'fran fria aminosyror', 'fra frie aminosyrer', 'fran fria aminosyror g', 'innhold per', 'naeringsdeklaration', 'energi kj'}
# labels that are deliberately NOT nutrients (kept out of unmapped.json, listed in ignored)
IGNORE = {'naeringsindhold', 'naeringsinnhold', 'innhold pr', 'hvorav', 'om morgenen', 'etter trening', 'som mellommaltid', 'pa kvelden', '','fruits vegetables nuts estimate from ingredients', 'fruits vegetables legumes estimate from ingredients', 'nova group', 'nutrition score fr', 'fruits vegetables legumes',
          'fruits vegetables nuts', 'carbon footprint from known ingredients', 'carbon footprint', 'fruits vegetables nuts estimate', 'new 9', 'cocoa', 'waste', 'dry matter',
          'nitrogen', 'density', 'specific gravity', 'sum minerals', 'sum fatty acids', 'fatty acid conversion factor', 'nitrogen conversion factor jones', 'fullkorn totalt',
          'avfall skal etc', 'sum biogenic amines', 'sum non essential amino acids', 'protein from amino acids', 'other fatty acids', 'tocopherol beta', 'tocopherol gamma', 'tocopherol delta'}

# ------------------------------------------------------------------- units
UNIT_G = {'g': 1.0, 'mg': 1e-3, 'ug': 1e-6, 'kg': 1e3}


def norm_unit(u):
    if u is None:
        return None
    s = str(u).strip().lower().replace('µ', 'u').replace('μ', 'u').replace('μ', 'u')
    s = re.sub(r'&[a-z]+[;,]?', '', s)
    s = s.replace(' ', '')
    if not s:
        return None
    s = re.sub(r'/100(g|ml)$', '', s)
    s = re.sub(r'\(.*?\)', '', s) if re.match(r'^(re|rae)\(', s) else s
    if s in ('kcal', 'kcal/100g', 'kilokalorier'):
        return 'kcal'
    if s in ('kj', 'kilojoule'):
        return 'kj'
    if s in ('%', '%vol', 'vol%', '%vol/*'):
        return s
    if '%dv' in s or 'dv' == s or s.endswith('%ri'):
        return 'pct_ri'
    if s.startswith('mg') or s in ('milligram', 'mg-ate'):
        return 'mg'
    if s.startswith(('ug', 'mcg', 'microgram')) or s in ('re', 'rae', 're/ug', 'ug-re'):
        return 'ug'
    if s in ('g', 'gram', 'gr'):
        return 'g'
    if s in ('alfa-te', 'alpha-te', 'ate', 'te'):
        return 'mg'
    if s in ('ne', 'ne/mg'):
        return 'mg'
    if s in ('iu', 'ie', 'i.e.'):
        return 'iu'
    if s in ('ml', 'l', 'dl', 'cl'):
        return s
    return s


def norm_label(label):
    """Normalise a raw label: lowercase, ascii-fold the nordic letters, drop bullets / 'of which' prefixes."""
    if label is None:
        return ''
    s = str(label).replace(' ', ' ').strip().lower()
    s = s.replace('æ', 'ae').replace('ø', 'o').replace('å', 'a').replace('ä', 'a').replace('ö', 'o').replace('ü', 'u').replace('é', 'e').replace('è', 'e')
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace('µ', 'u').replace('μ', 'u')
    s = re.sub(r'<[^>]+>', ' ', s)
    s = re.sub(r'&[a-z]+[;,]?', ' ', s)
    s = re.sub(r'^[\s\-–—•·*+]+', '', s)
    for _ in range(3):
        s = re.sub(r'^(hvorav|herav|heraf|hvoraf|hvor|varav|darav|josta|joista|av hvilke|av hvilka|av disse|derav|hvor av|of which|whereof|including|inkl\.?|waarvan|davon|dont|-)\b[\s:,.\-]*', '', s)
        s = re.sub(r'^[\s\-–—•·*+]+', '', s)
    # joined row labels such as 'kolhydrater -varav sockerarter' or 'fett varav mattat' -> the sub-nutrient
    m_ = re.match(r'^\S.*?\s+[-–]?\s*(?:varav|hvorav|heraf|hvoraf|josta|joista)\s+(.+)$', s)
    if m_:
        s = m_.group(1)
    s = re.sub(r'\bper\s*100\s*(g|ml)\b', ' ', s)
    s = s.replace('*', ' ').replace('†', ' ').replace('‡', ' ')
    s = re.sub(r'\s+', ' ', s).strip(' :;.,')
    return s


def _simplify(s):
    return re.sub(r'\s+', ' ', re.sub(r'[,;:/\-_+&]', ' ', s)).strip()


def _lookup(s):
    c = ALIAS.get(s)
    if c and len(c) == 1:
        return next(iter(c))
    return None


ENERGY_BASE = {'energi', 'energy', 'energie', 'energi kj kcal', 'energy kj kcal', 'energi kj/kcal', 'energi (kj/kcal)', 'energi kcal kj', 'energi kj  kcal', 'energi i alt'}


def map_label(label, unit=None, key=None, source=None):
    """-> (code, factor, note). code None => (None, None, reason) reason 'ignored' or 'unmapped'/'unit'."""
    u = norm_unit(unit)
    if u == 'pct_ri':
        return None, None, 'ignored'
    if u == '%' and key is None and source not in ('openfoodfacts',):
        return None, None, 'ignored_pct_column'
    # source specific overrides (by key)
    ov = OVERRIDES.get(source)
    if ov is not None and key is not None and key in ov:
        code = ov[key]
        if code is None:
            return None, None, 'ignored'
        return _finish(code, u, label)
    if source in ('usda-fdc', 'frida-dk') and key is not None:
        # generic fall back for chain fatty acids on these sources
        c = fa_from_label(label or '')
        if c:
            ensure_fa(c)
            return _finish(c, u, label)
    n = norm_label(label)
    if not n:
        return None, None, 'ignored'
    if ' / ' in n and not (n in ALIAS):
        for part in n.split(' / '):
            r = map_label(part, unit, key=None, source=source)
            if r[0] is not None:
                return r
        return None, None, 'unmapped'
    if n in IGNORE or n in IGNORE_EXTRA or n.startswith('translation missing'):
        return None, None, 'ignored'
    # trailing "(unit)" hint in label
    m = re.search(r'\(\s*(g|mg|ug|mcg|kj|kcal|ml)\s*\)\s*$', n)
    if m:
        hint = m.group(1)
        n = n[:m.start()].strip()
        if u is None:
            u = norm_unit(hint)
    m = re.search(r'\b(kcal|kj)\b$', n)
    cands = [n, _simplify(n)]
    paren_stripped = re.sub(r'\([^)]*\)', ' ', n)
    paren_stripped = re.sub(r'\s+', ' ', paren_stripped).strip()
    if paren_stripped and paren_stripped != n:
        cands += [paren_stripped, _simplify(paren_stripped)]
    inner = re.findall(r'\(([^)]*)\)', n)
    code = None
    # energy
    for c in cands:
        cs = _simplify(c)
        if cs in ('energi', 'energy', 'energie', 'energi i alt', 'kalorier kj', 'energi kj kcal', 'energy kj kcal'):
            if u == 'kj':
                return 'kj', 1.0, 'energy_by_unit'
            if u == 'kcal':
                return 'kcal', 1.0, 'energy_by_unit'
            if 'kcal' in n or 'kalori' in n:
                return 'kcal', 1.0, 'energy_by_label'
            if re.search(r'\bkj\b', n):
                return 'kj', 1.0, 'energy_by_label'
            return None, None, 'energy_unit_unknown'
    for c in cands:
        code = _lookup(c) or _lookup(_simplify(c))
        if code:
            break
    if code is None:
        for c in cands:
            code = _lookup(c.replace(' g', '').strip()) if c.endswith(' g') else None
            if code:
                break
    if code is None:
        for t in inner:
            code = _lookup(norm_label(t)) or _lookup(_simplify(norm_label(t)))
            if code:
                break
    if code is None:
        fa = fa_from_label(label or '')
        if fa:
            ensure_fa(fa)
            code = fa
    if code is None:
        # "vitamin b12 (cobalamin)" style: first word group before ' som ' / ' as ' / ' fra ' / ' from '
        base = re.split(r'\s(?:som|as|fra|from|i form av|form)\s', paren_stripped or n)[0].strip()
        if base != n:
            code = _lookup(base) or _lookup(_simplify(base))
    if code is None:
        # trailing units written inside the label "protein g", "salt mg"
        mm = re.match(r'^(.*?)\s+(g|mg|ug|mcg)$', _simplify(paren_stripped or n))
        if mm:
            code = _lookup(mm.group(1))
            if code and u is None:
                u = norm_unit(mm.group(2))
    if code is None:
        return None, None, 'unmapped'
    return _finish(code, u, label)


def _finish(code, u, label):
    spec = DICT.get(code)
    if spec is None:
        return None, None, 'unmapped'
    cu = spec['unit']
    if u is None:
        return code, 1.0, 'unit_assumed'
    if cu in ('kcal', 'kj'):
        if u == cu:
            return code, 1.0, 'ok'
        if u == 'g' and False:
            pass
        return None, None, 'unit_mismatch:%s->%s' % (u, cu)
    if cu == '%vol':
        return (code, 1.0, 'ok') if u.startswith('%') or u == 'vol%' else (None, None, 'unit_mismatch')
    if u in UNIT_G and cu in UNIT_G:
        return code, UNIT_G[u] / UNIT_G[cu], 'ok'
    return None, None, 'unit_mismatch:%s->%s' % (u, cu)


# ----------------------------------------------------------------------------------------------
# Second pass (2026-10-16): Swedish, Danish and Finnish store labels, folded spellings, mojibake.
# 1) Every existing alias is also registered in its folded form (ae/o/a/o ...), because lookups are made on norm_label() output.
#    This is what fixes Danish "maettede fedtsyrer" (14,000 occurrences), "fedt", "kulhydrater" and so on.
for _a in list(ALIAS):
    _n = norm_label(_a)
    if _n and _n != _a:
        ALIAS.setdefault(_n, set()).update(ALIAS[_a])


def _alias(code, *names):
    for _a in names:
        ALIAS.setdefault(norm_label(_a), set()).add(code)
        ALIAS.setdefault(_a, set()).add(code)


_alias('fat_g', 'rasva', 'rasvaa', 'fedt', 'fett totalt')
_alias('sat_fat_g', 'maettede fedtsyrer', 'maettede fedtsyre', 'maettet', 'maettet fedt', 'mattade fetter', 'mattade fettsyror', 'ma,ttat fett', 'mae,ttede fedtsyrer', 'mae,ttet fedt',
       'tyydyttynytta', 'tyydyttyneet rasvat', 'tyydyttynytta, rasvaa', 'tyydyttynyt rasva', 'tyydyttynyttä', 'mättat', 'mättade fetter', 'mættede fedtsyrer', 'mættet fedt')
_alias('mono_fat_g', 'enkelomattat', 'enkeltumaettede fedtsyrer', 'enkeltumaettet fedt', 'enumettede fedtsyrer', 'enkelomattade fettsyror', 'enkeltumættede fedtsyrer')
_alias('poly_fat_g', 'fleromattat', 'flerumaettede fedtsyrer', 'flerumaettet fedt', 'fleromattade fettsyror', 'flerumættede fedtsyrer')
_alias('trans_fat_g', 'transfetter', 'transfedtsyrer', 'transfettsyror')
_alias('carbs_g', 'hiilihydraatit', 'hiilihydraatteja', 'totala kolhydrater', 'kolhydrater', 'kolhydrat', 'kulhydrater', 'kulhydrat')
_alias('sugars_g', 'socker', 'sokeri', 'sokereita', 'sokerit', 'sockerarter', 'sukkerarter', 'socker (g)')
_alias('fibre_g', 'kuitu', 'kuitua', 'kostfibre', 'fibrer')
_alias('salt_g', 'suola', 'suolaa')
_alias('protein_g', 'proteiinia', 'proteiini')
_alias('phosphorus_mg', 'phosphor', 'fosfor')
_alias('chloride_mg', 'chlorid', 'klorid')
_alias('molybdenum_ug', 'molybdaen', 'molybden')
_alias('calcium_mg', 'calciu')
_alias('vit_b6_mg', 'vit. b6', 'vit b6', 'vitanmin b6', 'b6-vitamin')
_alias('vit_b12_ug', 'vit. b12', 'vit b12', 'vitmain b12', 'b12-vitamin')
_alias('vit_b5_mg', 'b5-vitamin')
_alias('vit_b3_mg', 'b3-vitamin')
_alias('omega3_g', 'omega-3-fettsyror', 'omega-3 fettsyror', 'omega-3 fedtsyrer', 'totalt omega-3', 'omega 3 fedtsyrer')
_alias('caffeine_mg', 'vattenfritt koffein', 'vatskefritt koffein')
_alias('fructose_g', 'fruktos')
_alias('glucose_g', 'glukos')
_alias('lactose_g', 'laktos')
_alias('sat_fat_g', 'mattade')
_alias('mono_fat_g', 'enkelmattade fettsyror')
_alias('polyols_g', 'polyoleja', 'sockeralkoholer')
_alias('carbs_g', 'karboydrater')
_alias('fat_g', 'fett/fedt')
_alias('omega3_g', 'omega-3 ialt', 'omega 3-fettsyror')
_alias('vit_b9_ug', 'vitamin b9, folsyra')
_alias('vit_b7_ug', 'vitamin b7, biotin')
