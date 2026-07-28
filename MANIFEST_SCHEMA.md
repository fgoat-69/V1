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
```

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

## Pack types

The supported pack types are:

```text
openfoodfacts
national
bundled
custom
```

Repository-generated country packs normally use:

```text
openfoodfacts
national
```

## Canonical source identifiers

Use these stable internal source identifiers:

| Dataset | Source identifier |
|---|---|
| USDA FoodData Central | `usda_fdc` |
| Open Food Facts | `openfoodfacts` |
| Germany BLS | `germany_bls` |
| France Ciqual | `france_ciqual` |
| Canadian Nutrient File | `canada_cnf` |
| UK CoFID 2021 | `uk_cofid_2021` |
| User-created foods | `custom` |

Source identifiers describe the original data source.

They must not describe:

- the hosting provider;
- the download method;
- the file type;
- the cache location;
- the application component that downloaded the data.

The following source identifiers must not be used:

```text
github_country_pack
downloaded_pack
national_pack
country_pack
off_local
open_food_facts
fooddata_central
```

## Field definitions

### `schemaVersion`

Version of the MostoFit manifest structure.

This is not the source dataset version.

### `packId`

A unique identifier for one generated pack release.

Recommended format:

```text
<source>_<country>_<version-or-date>
```

Examples:

```text
off_de_2026_07_25
bls_de_4_0
cofid_gb_2021
ciqual_fr_2025
```

### `packType`

The general type of pack:

```text
openfoodfacts
national
bundled
custom
```

### `countryIso2`

Uppercase ISO 3166-1 alpha-2 country code.

Examples:

```text
DE
GB
FR
CA
```

Keep the field name `countryIso2`. Do not replace it with `countryCode`.

### `source`

Canonical machine-readable source identifier.

Example:

```text
openfoodfacts
```

### `sourceName`

Human-readable official dataset name.

### `publisher`

The organization, government body, or project that publishes the original dataset.

### `datasetVersion`

The exact source dataset release, edition, version, or snapshot date.

Examples:

```text
4.0
2021
2025
2026
2026-07-25
```

This must not contain the Android app version.

### `license`

Short licence identifier.

Examples:

```text
CC0-1.0
ODbL-1.0
CC-BY-4.0
OGL-3.0
```

Dataset-specific licence values must be verified before publication.

### `sourceUrl`

Official source page or official dataset download location.

### `licenseUrl`

Official licence page.

### `modified`

Use `true` whenever MostoFit:

- filters records;
- removes fields;
- renames fields;
- converts units;
- changes names;
- translates names;
- combines fields;
- deduplicates records;
- changes missing values;
- converts the original format;
- splits the source into multiple output files.

Most MostoFit packs will use:

```json
"modified": true
```

### `modifications`

A plain-language list of transformations performed by the generator.

This list must describe what the generator actually does.

### `generatedAt`

UTC date and time when the pack was generated, in ISO 8601 format.

### `recordCount`

Total number of records included across the files listed in `files`.

### `files`

Machine-readable list of generated data files.

Every entry must include:

- filename;
- repository-relative path;
- file role;
- record count;
- byte size;
- SHA-256 checksum.

## Manifest filenames

Open Food Facts packs use:

```text
countries/<ISO2>/manifest.json
```

National datasets use:

```text
countries/<ISO2>/national_manifest.json
```

These filenames must remain separate because one country may contain both:

- an Open Food Facts pack;
- a national food-composition pack.

## Compatibility fields

Existing fields may remain temporarily while generators and consumers are migrated.

Examples include:

```text
slug
version
strategy
itemCountTotal
itemCountMain
itemCountFill
packFiles
buildMeta
owner
itemCount
file
```

New generator code should populate the standardized fields.

Compatibility fields may be removed later only after confirming that no consumer still depends on them.
