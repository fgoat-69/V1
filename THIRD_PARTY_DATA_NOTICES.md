# Third-Party Data Notices

## Open Food Facts

Source:

Open Food Facts

https://world.openfoodfacts.org/data

Database licence:

Open Data Commons Open Database License 1.0

https://opendatacommons.org/licenses/odbl/1-0/

Individual contents licence:

Open Data Commons Database Contents License 1.0

https://opendatacommons.org/licenses/dbcl/1-0/

Attribution notice:

Contains information from Open Food Facts, which is made available
under the Open Database License (ODbL).

MostoFit modifies the source database by:

* filtering products by country;
* selecting app-facing fields;
* selecting nutrition values per 100 g;
* converting kilojoules to kilocalories when necessary;
* normalizing selected serving units;
* removing records without usable nutrition information;
* deduplicating products;
* sorting products using popularity information where available;
* limiting large packs to a configured size budget;
* splitting large packs into app-facing files;
* converting the source export to JSON.

The generated packs do not contain Open Food Facts product images.

Open Food Facts data is collaboratively submitted and may be
incomplete or inaccurate. MostoFit does not represent the generated
packs as official nutritional or medical advice.

## Fineli - Finnish Food Composition Database

Source:

Fineli - Finnish Food Composition Database

Finnish Institute for Health and Welfare (THL)

https://fineli.fi/fineli/en/avoin-data

Licence:

Creative Commons Attribution 4.0 International (CC BY 4.0)

https://creativecommons.org/licenses/by/4.0/

Attribution notice:

Contains modified information from the Fineli - Finnish Food
Composition Database, Release 20.0, published by the Finnish Institute
for Health and Welfare (THL), and made available under the Creative
Commons Attribution 4.0 International licence.

Copyright 2015 National Institute for Health and Welfare (THL).

MostoFit modifies the Fineli source data by:

* combining Fineli Basic package 1, Basic package 2, and Ingredients for food industry;
* using English food names only;
* converting all-uppercase English food names to sentence case;
* selecting energy, protein, available carbohydrate, and total fat fields;
* converting Fineli energy values from kilojoules per 100 g to kilocalories per 100 g;
* normalizing nutrient values to the MostoFit food schema;
* setting brand and barcode to null because these fields are not supplied by the selected Fineli data;
* representing nutrition on a 100 g basis;
* deduplicating records across the three Fineli packages by Fineli FOODID and verifying overlapping values;
* removing records that contain none of the selected app-facing nutrient values;
* converting the source CSV data to JSON.

The resulting Fineli-derived dataset is modified from the original
source. MostoFit is not affiliated with, endorsed by, sponsored by, or
officially connected with Fineli or the Finnish Institute for Health
and Welfare (THL).

Nutritional information derived from Fineli is provided as reference
data and is not represented by MostoFit as medical or dietary advice.
