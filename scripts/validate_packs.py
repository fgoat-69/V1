import json
import os

from build_all_packs import (
    BATCH_NAME,
    COUNTRY_FILTER,
    selected_countries,
)
from manifest_utils import sha256_file


OFF_OUTPUT_FILENAMES = {
    "full.json",
    "main.json",
    "fill.json",
}

REQUIRED_MANIFEST_FIELDS = {
    "schemaVersion",
    "packId",
    "packType",
    "countryIso2",
    "source",
    "sourceName",
    "publisher",
    "datasetVersion",
    "license",
    "sourceUrl",
    "licenseUrl",
    "modified",
    "modifications",
    "generatedAt",
    "recordCount",
    "files",
}


def fail(message):
    raise RuntimeError(message)


def load_json(path):
    with open(path, "r", encoding="utf-8") as source_file:
        return json.load(source_file)


def countries_to_validate():
    if COUNTRY_FILTER or BATCH_NAME:
        return [
            iso2
            for iso2, _ in selected_countries()
        ]

    countries_root = "countries"

    if not os.path.isdir(countries_root):
        return []

    return sorted(
        entry
        for entry in os.listdir(countries_root)
        if os.path.isfile(
            os.path.join(
                countries_root,
                entry,
                "manifest.json",
            )
        )
    )


def validate_manifest_fields(country_iso2, manifest):
    missing = REQUIRED_MANIFEST_FIELDS - set(manifest.keys())

    if missing:
        fail(
            f"{country_iso2}: manifest is missing fields: "
            f"{', '.join(sorted(missing))}"
        )

    if manifest["schemaVersion"] != 1:
        fail(
            f"{country_iso2}: unsupported schemaVersion "
            f"{manifest['schemaVersion']}"
        )

    if manifest["packType"] != "openfoodfacts":
        fail(
            f"{country_iso2}: unexpected packType "
            f"{manifest['packType']}"
        )

    if manifest["countryIso2"] != country_iso2:
        fail(
            f"{country_iso2}: manifest countryIso2 mismatch"
        )

    if manifest["source"] != "openfoodfacts":
        fail(
            f"{country_iso2}: unexpected manifest source "
            f"{manifest['source']}"
        )

    if manifest["license"] != "ODbL-1.0":
        fail(
            f"{country_iso2}: unexpected database licence "
            f"{manifest['license']}"
        )

    if manifest.get("contentsLicense") != "DbCL-1.0":
        fail(
            f"{country_iso2}: missing or incorrect "
            "contentsLicense"
        )

    if manifest["modified"] is not True:
        fail(
            f"{country_iso2}: OFF country packs must declare "
            "that they are modified"
        )

    if not manifest["modifications"]:
        fail(
            f"{country_iso2}: modifications list is empty"
        )

    if manifest.get("containsProductImages") is not False:
        fail(
            f"{country_iso2}: manifest must declare that "
            "product images are not included"
        )


def validate_data_file(country_iso2, entry):
    relative_path = entry.get("path")
    filename = entry.get("name")

    if not relative_path or not filename:
        fail(
            f"{country_iso2}: invalid file entry in manifest"
        )

    if filename not in OFF_OUTPUT_FILENAMES:
        fail(
            f"{country_iso2}: unexpected OFF output file "
            f"{filename}"
        )

    if not os.path.isfile(relative_path):
        fail(
            f"{country_iso2}: listed file does not exist: "
            f"{relative_path}"
        )

    actual_bytes = os.path.getsize(relative_path)

    if actual_bytes != entry.get("bytes"):
        fail(
            f"{country_iso2}: byte-size mismatch for "
            f"{filename}"
        )

    actual_sha256 = sha256_file(relative_path)

    if actual_sha256 != entry.get("sha256"):
        fail(
            f"{country_iso2}: SHA-256 mismatch for "
            f"{filename}"
        )

    records = load_json(relative_path)

    if not isinstance(records, list):
        fail(
            f"{country_iso2}: {filename} must contain "
            "a JSON array"
        )

    if len(records) != entry.get("recordCount"):
        fail(
            f"{country_iso2}: record-count mismatch for "
            f"{filename}"
        )

    for index, item in enumerate(records):
        if not isinstance(item, dict):
            fail(
                f"{country_iso2}: {filename} record "
                f"{index} is not an object"
            )

        if not str(item.get("name") or "").strip():
            fail(
                f"{country_iso2}: {filename} record "
                f"{index} has no name"
            )

        if item.get("source") != "openfoodfacts":
            fail(
                f"{country_iso2}: {filename} record "
                f"{index} has invalid source "
                f"{item.get('source')}"
            )

        if "barcode" not in item:
            fail(
                f"{country_iso2}: {filename} record "
                f"{index} has no barcode field"
            )

        for key in item:
            if key.lower().startswith("image"):
                fail(
                    f"{country_iso2}: {filename} record "
                    f"{index} unexpectedly contains image data"
                )

    return len(records)


def validate_country(country_iso2):
    country_path = os.path.join(
        "countries",
        country_iso2,
    )
    manifest_path = os.path.join(
        country_path,
        "manifest.json",
    )

    if not os.path.isfile(manifest_path):
        fail(
            f"{country_iso2}: manifest.json does not exist"
        )

    manifest = load_json(manifest_path)
    validate_manifest_fields(country_iso2, manifest)

    manifest_file_names = {
        entry.get("name")
        for entry in manifest["files"]
    }

    existing_output_names = {
        filename
        for filename in OFF_OUTPUT_FILENAMES
        if os.path.isfile(
            os.path.join(country_path, filename)
        )
    }

    if manifest_file_names != existing_output_names:
        fail(
            f"{country_iso2}: manifest file list does not "
            "match generated OFF files"
        )

    calculated_record_count = sum(
        validate_data_file(country_iso2, entry)
        for entry in manifest["files"]
    )

    if calculated_record_count != manifest["recordCount"]:
        fail(
            f"{country_iso2}: manifest recordCount mismatch"
        )

    print(
        f"Validated {country_iso2}: "
        f"{calculated_record_count} records"
    )


def main():
    selected = countries_to_validate()

    if not selected:
        fail("No Open Food Facts country packs selected.")

    for country_iso2 in selected:
        validate_country(country_iso2)

    print(
        f"Successfully validated {len(selected)} "
        "Open Food Facts country packs."
    )


if __name__ == "__main__":
    main()
