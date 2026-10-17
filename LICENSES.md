# Source licences

Not legal advice. This table says what we know about each source so that the team can decide what may go into a public app.

| Source | What | Terms (as far as we know) |
|---|---|---|
| Open Food Facts | Products with EAN, nutrition, ingredients | ODbL database licence (attribution + share-alike for the database; contents under DbCL). Commercial use allowed with attribution. |
| USDA FoodData Central | US branded and generic foods | Public domain (CC0). |
| Matvaretabellen (Mattilsynet) | Norwegian generic foods | Open data; cite Matvaretabellen as the source. Check the current terms before publishing. |
| Frida (DTU Food, Denmark) | Danish generic foods | Open data with attribution (CC BY). Check current terms. |
| Livsmedelsverket | Swedish generic foods | Open data, attribution required. Check current terms. |
| Kassalapp | Norwegian grocery product data | Their FAQ allows personal use and caching. Commercial or public redistribution needs their permission. |
| NorgesGruppen (Meny, Spar, Joker) | Nutrition per product | Shop data via the site's own API. Collected for personal research. Product image terms forbid storing images (none stored). |
| Shops and brand sites (Tights, Gymgrossisten, Bodystore, Proteinfabrikken, Bulk, Myprotein, Life, Helsekost, Bodylab, Barebells, Tine, Gilde, Toro, Nidar, Orkla brands and others) | Nutrition tables and product facts | Public pages, collected within robots.txt at 1 request per second for personal research. Each site's terms apply. Nutrition facts themselves are factual data, but a public app that republishes a shop's catalogue is a legal question. Ask before shipping. |
| Internet Archive | Old product pages (discontinued items) | Archived copies of the shops' pages; same terms as the original shop. |

**Recommendation:** for any public app, ship only the open sources (Open Food Facts, USDA, Matvaretabellen, Frida, Livsmedelsverket) plus anything we get written permission for. Every row in `product_sources` carries its `source`, so filtering is a one-line query. Contribute corrections back to Open Food Facts where we can.
