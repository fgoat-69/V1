# OFF Country Packs

This repository builds downloadable OpenFoodFacts country packs for the Android app.

The app will eventually use these packs as a fast local country layer before falling back to global online OFF search.

## Intended app search order

1. user-local foods
   - logged foods / recent foods
   - favorites
   - custom foods

2. downloaded local country pack

3. global online OpenFoodFacts fallback

## Current build strategy

The repository now builds packs from the Open Food Facts JSONL dump instead of bulk-crawling the search API.

Why:

- OFF search endpoints are rate-limited and can block bulk traversal
- OFF recommends downloading CSV / JSONL data directly for large-scale data access
- this repo needs a stable country-pack publisher path, not an API-crawling script

## Current packing rules

- if a discovered country dataset is small enough, save it as `full.json`
- if the discovered dataset is too large, split it into:
  - `main.json`
  - `fill.json`
- keep total packaged country size near the configured byte budget
- deduplicate by:
  - barcode first
  - normalized name + brand second

## Current output contract

Each country directory contains:

- `manifest.json`
- `full.json`
  - or
- `main.json`
- `fill.json` (when needed)

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
  "source": "github_country_pack"
}
