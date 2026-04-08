# OFF Country Packs

This repository stores preprocessed OpenFoodFacts country datasets for use in mobile apps.

## Strategy

- Small countries (< 20k items): full dataset
- Large countries (> 20k items):
  - Top 10k popular items
  - Fill up to 25k total

## Deduplication

- Primary: barcode
- Fallback: normalized name + brand

## Structure

countries/
  index.json
  {ISO2}/
    manifest.json
    full.json OR top.json + fill.json

## Update frequency

- Weekly (planned via GitHub Actions)
