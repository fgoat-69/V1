````markdown
# MostoFit Country Pack Manifest Schema

All generated food-data packs must include a manifest describing:

- where the data originated;
- who published the original dataset;
- which dataset version was used;
- which licence governs the source;
- how MostoFit modified the data;
- which generated files belong to the pack;
- how many records were generated;
- SHA-256 checksums for generated files.

## Schema version

The current manifest schema version is:

```text
1
````

## Required manifest fields

Every `manifest.json` and `national_manifest.json` must contain the following standard fields:

```json
{
  "schemaVersion": 1,
  "packId": "off_de_2026_07_25",
  "packType": "openfoodfacts",
  "countryIso2": "DE",
  "source": "openfoodfacts",
  "sourceName": "Open Food Facts",
  "publisher": "Open Food Facts",
  "datasetVersion": "2026-07-25",
  "license": "ODbL-1.0",
  "sourceUrl": "OFFICIAL SOURCE URL",
  "licenseUrl": "OFFICIAL LICENCE URL",
  "modified": true,
  "modifications": [
    "filtered by country",
    "reduced to selected fields",
    "normalized to the MostoFit food schema",
    "deduplicated"
  ],
  "generatedAt": "2026-07-25T12:00:00+00:00",
  "recordCount": 22854,
  "files": [
    {
      "name": "main.json",
      "path": "countries/DE/main.json",
      "kind": "main",
      "recordCount": 18000,
      "bytes": 5000000,
      "sha256": "SHA-256 VALUE"
    },
    {
      "name": "fill.json",
      "path": "countries/DE/fill.json",
      "kind": "fill",
      "recordCount": 4854,
      "bytes": 1900000,
      "sha256": "SHA-256 VALUE"
    }
  ]
}
```

```
```
