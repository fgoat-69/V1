# OFF Country Packs

This repository builds downloadable Open Food Facts country packs for the Android app.

The app uses these packs as a fast local country layer before falling back to global online Open Food Facts search.

## Intended app search order

1. User-local foods
   - logged and recent foods
   - favorites
   - custom foods

2. Downloaded local country pack

3. Global online Open Food Facts fallback

## Current build strategy

The repository builds packs from the compressed Open Food Facts CSV export instead of bulk-crawling the search API.

Why:

- OFF search endpoints are rate-limited and can block bulk traversal;
- OFF recommends downloading bulk export data directly for large-scale data access;
- this repository needs a stable country-pack publishing process.

## Current packing rules

- If a discovered country dataset is small enough, save it as `full.json`.
- If the discovered dataset is too large, split it into:
  - `main.json`
  - `fill.json`
- Keep total packaged country size near the configured byte budget.
- Deduplicate by:
  - barcode first;
  - normalized name and brand second.

## Current output contract

Each country directory contains:

- `manifest.json`;
- either `full.json`;
- or `main.json` and, when necessary, `fill.json`.

The root `countries/index.json` contains the generated country manifest list.

## Output item format

Each item is written in a simplified app-facing format:

```json
{
  "name": "Example Food",
  "brand": "Example Brand",
  "barcode": "1234567890123",
  "calories": 250.0,
  "protein": 10.5,
  "carbs": 30.0,
  "fat": 8.0,
  "servingSize": 30.0,
  "servingUnit": "g",
  "isLiquid": false,
  "source": "openfoodfacts"
}
```

## Data licensing

The Open Food Facts database is available under the Open Data
Commons Open Database License 1.0, or ODbL 1.0.

Individual database contents are available under the Open Data
Commons Database Contents License 1.0, or DbCL 1.0.

The country packs in this repository are modified databases derived
from Open Food Facts. They are publicly distributed under ODbL 1.0.

Contains information from Open Food Facts, which is made available
under the Open Database License (ODbL).

Official source:

https://world.openfoodfacts.org/data

Database licence:

https://opendatacommons.org/licenses/odbl/1-0/

Contents licence:

https://opendatacommons.org/licenses/dbcl/1-0/

Each country manifest records:

- the Open Food Facts source;
- the snapshot date;
- the transformations performed;
- the database and contents licences;
- record counts;
- file sizes;
- SHA-256 checksums.

The generated packs do not include Open Food Facts product images.

The software source code and the third-party food databases are
separate works. A software licence applied to the repository does not
replace or override the licences governing third-party data.
