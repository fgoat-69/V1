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

## Current packing strategy

The repository currently builds country packs with these rules:

- if a discovered country dataset is small enough, save it as `full.json`
- if the discovered dataset is too large, split it into:
  - `main.json`
  - `fill.json`
- keep total packaged country size near the configured byte budget
- deduplicate by:
  - barcode first
  - normalized name + brand second

## Important limitation

The current builder uses OFF search API discovery with country filtering and popularity sorting.

That means:

- it is practical and low-cost
- it can build useful country packs
- it does **not** guarantee mathematically complete country coverage

So `full.json` currently means:
“all discovered usable items for that country within the builder’s rules”

It does **not** yet mean:
“provably every OFF item for that country”

If stricter full-country coverage is needed later, the build pipeline should move toward an OFF dump/export-based ingestion path.

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
