import csv
import io
import json
import os
import re
import zipfile
from collections import defaultdict

from manifest_utils import build_file_entry, build_standard_manifest, utc_now_iso


OUTPUT_ROOT = "countries"
SOURCE_ROOT = "national_sources/FI"

SOURCE_PACKAGES = [
    (
        "basic_2_74_components",
        os.path.join(SOURCE_ROOT, "Fineli_Rel20__74_ravintotekij__.zip"),
    ),
    (
        "basic_1_55_components",
        os.path.join(SOURCE_ROOT, "Fineli_Rel20.zip"),
    ),
    (
        "food_industry_ingredients_40_components",
        os.path.join(SOURCE_ROOT, "Fineli_Rel20_R40.zip"),
    ),
]

FINELI_RELEASE = "20.0"
FINELI_SOURCE_ID = "fineli_thl"
FINELI_SOURCE_NAME = "Fineli - Finnish Food Composition Database"
FINELI_PUBLISHER = "Finnish Institute for Health and Welfare (THL)"
FINELI_SOURCE_URL = "https://fineli.fi/fineli/en/avoin-data"
FINELI_LICENSE_ID = "CC-BY-4.0"
FINELI_LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
FINELI_COPYRIGHT = "Copyright 2015 National Institute for Health and Welfare (THL)."

# Fineli component codes used by MostoFit.
COMPONENT_ENERGY_KJ = "ENERC"
COMPONENT_FAT_G = "FAT"
COMPONENT_CARBS_G = "CHOAVL"
COMPONENT_PROTEIN_G = "PROT"
SELECTED_COMPONENTS = {
    COMPONENT_ENERGY_KJ,
    COMPONENT_FAT_G,
    COMPONENT_CARBS_G,
    COMPONENT_PROTEIN_G,
}


def normalize_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip())


def normalize_for_match(value):
    return normalize_text(value).casefold()


def sentence_case_all_caps(value):
    """Lowercase an ALL-CAPS Fineli name except for its first alphabetic character."""
    text = normalize_text(value)

    if not text or not any(char.isalpha() for char in text):
        return text

    if text != text.upper():
        return text

    lowered = text.lower()

    for index, char in enumerate(lowered):
        if char.isalpha():
            return lowered[:index] + char.upper() + lowered[index + 1 :]

    return lowered


def parse_number(value):
    text = normalize_text(value)

    if not text:
        return None

    text = text.replace(",", ".")

    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"Invalid Fineli number: {value!r}") from exc


def read_csv_from_zip(zip_file, member):
    if member not in zip_file.namelist():
        raise FileNotFoundError(
            f"Missing {member!r} from Fineli source archive {zip_file.filename}"
        )

    text = zip_file.read(member).decode("cp1252")
    return list(csv.DictReader(io.StringIO(text), delimiter=";"))


def load_fineli_package(label, zip_path):
    if not os.path.isfile(zip_path):
        raise FileNotFoundError(
            f"Missing Fineli source archive for {label}: {zip_path}"
        )

    with zipfile.ZipFile(zip_path, "r") as zip_file:
        food_rows = read_csv_from_zip(zip_file, "food.csv")
        name_rows = read_csv_from_zip(zip_file, "foodname_EN.csv")
        component_rows = read_csv_from_zip(zip_file, "component.csv")
        value_rows = read_csv_from_zip(zip_file, "component_value.csv")

    foods = {normalize_text(row["FOODID"]): row for row in food_rows}
    names = {
        normalize_text(row["FOODID"]): normalize_text(row["FOODNAME"])
        for row in name_rows
        if normalize_text(row.get("LANG")).upper() == "EN"
    }
    components = {
        normalize_text(row["EUFDNAME"]): row
        for row in component_rows
    }

    required_components = SELECTED_COMPONENTS - set(components)
    if required_components:
        raise RuntimeError(
            f"{label} is missing required components: {sorted(required_components)}"
        )

    expected_units = {
        COMPONENT_ENERGY_KJ: "KJ",
        COMPONENT_FAT_G: "G",
        COMPONENT_CARBS_G: "G",
        COMPONENT_PROTEIN_G: "G",
    }

    for code, expected_unit in expected_units.items():
        actual_unit = normalize_text(components[code].get("COMPUNIT")).upper()
        if actual_unit != expected_unit:
            raise RuntimeError(
                f"Unexpected Fineli unit for {code}: {actual_unit!r}; "
                f"expected {expected_unit!r}"
            )

    nutrients = defaultdict(dict)

    for row in value_rows:
        component = normalize_text(row.get("EUFDNAME"))
        if component not in SELECTED_COMPONENTS:
            continue

        food_id = normalize_text(row.get("FOODID"))
        value = parse_number(row.get("BESTLOC"))
        key = (food_id, component)

        if component in nutrients[food_id]:
            raise RuntimeError(
                f"Duplicate component row inside {label}: "
                f"FOODID={food_id}, component={component}"
            )

        nutrients[food_id][component] = value

    package = {
        "label": label,
        "path": zip_path,
        "foods": foods,
        "names": names,
        "nutrients": dict(nutrients),
        "component_count": len(components),
    }

    print(
        f"Loaded {label}: {len(foods)} foods, "
        f"{len(names)} English names, {len(components)} components"
    )

    return package


def canonical_food_metadata(row):
    """Fields that identify the same Fineli FOODID across package variants."""
    return {
        "FOODNAME": normalize_text(row.get("FOODNAME")),
        "FOODTYPE": normalize_text(row.get("FOODTYPE")),
        "PROCESS": normalize_text(row.get("PROCESS")),
        "EDPORT": normalize_text(row.get("EDPORT")),
        "IGCLASS": normalize_text(row.get("IGCLASS")),
        "IGCLASSP": normalize_text(row.get("IGCLASSP")),
        "FUCLASS": normalize_text(row.get("FUCLASS")),
        "FUCLASSP": normalize_text(row.get("FUCLASSP")),
    }


def merge_packages(packages):
    merged = {}
    duplicate_food_ids = 0
    overlapping_component_values = 0

    for package in packages:
        label = package["label"]

        for food_id, food_row in package["foods"].items():
            english_name = package["names"].get(food_id)
            nutrient_values = package["nutrients"].get(food_id, {})

            if not english_name:
                raise RuntimeError(
                    f"Missing English name in {label} for Fineli FOODID={food_id}"
                )

            if food_id not in merged:
                merged[food_id] = {
                    "food": food_row,
                    "english_name": english_name,
                    "nutrients": dict(nutrient_values),
                    "packages": [label],
                }
                continue

            duplicate_food_ids += 1
            current = merged[food_id]

            if canonical_food_metadata(current["food"]) != canonical_food_metadata(food_row):
                raise RuntimeError(
                    f"Conflicting food metadata across Fineli packages for FOODID={food_id}"
                )

            if current["english_name"] != english_name:
                raise RuntimeError(
                    f"Conflicting English name across Fineli packages for FOODID={food_id}: "
                    f"{current['english_name']!r} vs {english_name!r}"
                )

            for component, value in nutrient_values.items():
                if component in current["nutrients"]:
                    overlapping_component_values += 1
                    previous = current["nutrients"][component]
                    if previous != value:
                        raise RuntimeError(
                            "Conflicting Fineli component value across packages: "
                            f"FOODID={food_id}, component={component}, "
                            f"{previous!r} vs {value!r}"
                        )
                else:
                    current["nutrients"][component] = value

            current["packages"].append(label)

    print(f"Merged repeated FOODIDs across package inputs: {duplicate_food_ids}")
    print(f"Verified identical overlapping component values: {overlapping_component_values}")

    return merged


def make_pack_item(food_id, record):
    nutrients = record["nutrients"]

    # A few rows exist in food.csv without any of the selected nutrient values.
    # Do not invent nutrition for those records.
    if not any(component in nutrients for component in SELECTED_COMPONENTS):
        return None

    energy_kj = nutrients.get(COMPONENT_ENERGY_KJ) or 0.0
    fat = nutrients.get(COMPONENT_FAT_G) or 0.0
    carbs = nutrients.get(COMPONENT_CARBS_G) or 0.0
    protein = nutrients.get(COMPONENT_PROTEIN_G) or 0.0

    calories = energy_kj / 4.184

    return {
        "name": sentence_case_all_caps(record["english_name"]),
        "brand": None,
        "barcode": None,
        "calories": round(calories, 2),
        "protein": round(protein, 2),
        "carbs": round(carbs, 2),
        "fat": round(fat, 2),
        "servingSize": 100.0,
        "servingUnit": "g",
        "isLiquid": False,
        "source": FINELI_SOURCE_ID,
        "sourceItemId": str(food_id),
    }


def deduplicate_output_items(items):
    """
    Cross-check for duplicates that somehow survived FOODID merging.

    Different Fineli FOODIDs are only merged when both normalized English name and
    all four app-facing macro values are identical. This deliberately avoids fuzzy
    matching that could collapse genuine raw/cooked or process variants.
    """
    unique = []
    seen = {}
    duplicate_count = 0

    for item in items:
        key = (
            normalize_for_match(item["name"]),
            item["calories"],
            item["protein"],
            item["carbs"],
            item["fat"],
        )

        previous = seen.get(key)
        if previous is not None:
            duplicate_count += 1
            continue

        seen[key] = item
        unique.append(item)

    print(f"Removed exact cross-ID duplicates after normalization: {duplicate_count}")
    return unique


def write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as output_file:
        json.dump(payload, output_file, ensure_ascii=False, indent=2)


def build_fineli_pack():
    packages = [
        load_fineli_package(label, path)
        for label, path in SOURCE_PACKAGES
    ]

    merged = merge_packages(packages)

    items = []
    skipped_without_selected_nutrients = 0

    for food_id in sorted(merged, key=lambda value: int(value)):
        item = make_pack_item(food_id, merged[food_id])
        if item is None:
            skipped_without_selected_nutrients += 1
            continue
        items.append(item)

    items = deduplicate_output_items(items)
    items.sort(key=lambda item: (item["name"].casefold(), int(item["sourceItemId"])))

    output_dir = os.path.join(OUTPUT_ROOT, "FI")
    national_path = os.path.join(output_dir, "national.json")
    national_relative_path = "countries/FI/national.json"
    manifest_path = os.path.join(output_dir, "national_manifest.json")

    write_json(national_path, items)

    file_entry = build_file_entry(
        file_path=national_path,
        relative_path=national_relative_path,
        kind="national",
        record_count=len(items),
    )

    generated_at = utc_now_iso()

    manifest = build_standard_manifest(
        pack_id="fineli_fi_20_0",
        pack_type="national",
        country_iso2="FI",
        source=FINELI_SOURCE_ID,
        source_name=FINELI_SOURCE_NAME,
        publisher=FINELI_PUBLISHER,
        dataset_version=FINELI_RELEASE,
        license_id=FINELI_LICENSE_ID,
        source_url=FINELI_SOURCE_URL,
        license_url=FINELI_LICENSE_URL,
        modified=True,
        modifications=[
            "combined Fineli Basic package 1, Basic package 2 and Ingredients for food industry",
            "used English food names only",
            "converted all-uppercase English food names to sentence case",
            "selected energy, protein, available carbohydrate and total fat fields",
            "converted Fineli energy values from kilojoules per 100 g to kilocalories per 100 g",
            "normalized nutrient values to the MostoFit food schema",
            "set brand and barcode to null because these fields are not supplied by the selected Fineli data",
            "represented nutrition on a 100 g basis",
            "deduplicated records across the three Fineli packages by Fineli FOODID and verified overlapping values",
            "removed records that had none of the selected app-facing nutrient values",
            "converted the source CSV data to JSON",
        ],
        generated_at=generated_at,
        record_count=len(items),
        files=[file_entry],
        extra_fields={
            "owner": FINELI_PUBLISHER,
            "itemCount": len(items),
            "file": national_relative_path,
            "sourceFiles": [path.replace("\\", "/") for _, path in SOURCE_PACKAGES],
            "copyright": FINELI_COPYRIGHT,
            "attribution": (
                "Fineli - Finnish Food Composition Database, Release 20.0, "
                "Finnish Institute for Health and Welfare (THL), CC BY 4.0. "
                "Modified by MostoFit."
            ),
        },
    )

    write_json(manifest_path, manifest)

    print(f"Skipped foods with no selected nutrient values: {skipped_without_selected_nutrients}")
    print(f"Saved Fineli national pack: {len(items)} items")
    print(f"Output: {national_path}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    build_fineli_pack()
