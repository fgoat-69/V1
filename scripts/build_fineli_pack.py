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
FINELI_COPYRIGHT = (
    "Copyright 2015 National Institute for Health and Welfare (THL)."
)

# Fineli component codes used by MostoFit.
#
# IMPORTANT:
# These values are source composition values. Fineli reports them on a
# per-100 g basis. Serving-size metadata must NEVER be used to rescale these
# fields inside this builder.
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

# Fineli provides generic PORTS / PORTM / PORTL values for essentially every
# food. Those are intentionally NOT used as app serving sizes.
#
# Only explicitly sourced serving units are accepted:
# - KPL_VALM: Manufacturer (piece)
# - PORTTBL: Food composition table portion
#
# The MASS field in foodaddunit.csv is documented by Fineli as grams, so the
# app-facing serving value is stored in grams.
EXPLICIT_SERVING_UNIT_PRIORITY = (
    "KPL_VALM",
    "PORTTBL",
)

# Conservative liquid classification.
#
# Fineli does not provide a literal boolean "is liquid" field. We therefore
# mark an item liquid only when its food-use classification unambiguously
# describes a beverage/liquid group. We do NOT infer liquid status from:
# - the English food name;
# - the presence of a decilitre measurement;
# - density assumptions.
#
# This deliberately leaves ambiguous foods (for example yoghurt, cream,
# soups, sauces, oils, infant-formula powders) as non-liquid.
LIQUID_PARENT_CLASSES = {
    "BEVTOT",  # Beverages
    "ALCTOT",  # Alcoholic beverages
}

LIQUID_DIRECT_CLASSES = {
    "FRUBJUIC",  # Juices
    "VEGJUICE",  # Vegetable juices
    "MILKFF",    # Milks skimmed
    "MILKLF",    # Milks <2% fat
    "MILKHF",    # Milks >2% fat
    "SMILK",     # Soured milks
}


def normalize_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip())


def normalize_for_match(value):
    return normalize_text(value).casefold()


def sentence_case_all_caps(value):
    """
    Convert an ALL-CAPS Fineli English food name to sentence case.

    Already mixed-case text is left unchanged.
    """
    text = normalize_text(value)

    if not text or not any(char.isalpha() for char in text):
        return text

    if text != text.upper():
        return text

    lowered = text.lower()

    for index, char in enumerate(lowered):
        if char.isalpha():
            return (
                lowered[:index]
                + char.upper()
                + lowered[index + 1 :]
            )

    return lowered


def parse_number(value):
    text = normalize_text(value)

    if not text:
        return None

    text = text.replace(",", ".")

    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(
            f"Invalid Fineli number: {value!r}"
        ) from exc


def read_csv_from_zip(zip_file, member):
    if member not in zip_file.namelist():
        raise FileNotFoundError(
            f"Missing {member!r} from Fineli source archive "
            f"{zip_file.filename}"
        )

    text = zip_file.read(member).decode("cp1252")
    return list(
        csv.DictReader(
            io.StringIO(text),
            delimiter=";",
        )
    )


def load_fineli_package(label, zip_path):
    if not os.path.isfile(zip_path):
        raise FileNotFoundError(
            f"Missing Fineli source archive for {label}: {zip_path}"
        )

    with zipfile.ZipFile(zip_path, "r") as zip_file:
        food_rows = read_csv_from_zip(zip_file, "food.csv")
        name_rows = read_csv_from_zip(
            zip_file,
            "foodname_EN.csv",
        )
        component_rows = read_csv_from_zip(
            zip_file,
            "component.csv",
        )
        value_rows = read_csv_from_zip(
            zip_file,
            "component_value.csv",
        )
        additional_unit_rows = read_csv_from_zip(
            zip_file,
            "foodaddunit.csv",
        )
        food_unit_rows = read_csv_from_zip(
            zip_file,
            "foodunit_EN.csv",
        )

    foods = {
        normalize_text(row["FOODID"]): row
        for row in food_rows
    }

    names = {
        normalize_text(row["FOODID"]): normalize_text(
            row["FOODNAME"]
        )
        for row in name_rows
        if normalize_text(row.get("LANG")).upper() == "EN"
    }

    components = {
        normalize_text(row["EUFDNAME"]): row
        for row in component_rows
    }

    required_components = (
        SELECTED_COMPONENTS - set(components)
    )

    if required_components:
        raise RuntimeError(
            f"{label} is missing required components: "
            f"{sorted(required_components)}"
        )

    expected_units = {
        COMPONENT_ENERGY_KJ: "KJ",
        COMPONENT_FAT_G: "G",
        COMPONENT_CARBS_G: "G",
        COMPONENT_PROTEIN_G: "G",
    }

    for code, expected_unit in expected_units.items():
        actual_unit = normalize_text(
            components[code].get("COMPUNIT")
        ).upper()

        if actual_unit != expected_unit:
            raise RuntimeError(
                f"Unexpected Fineli unit for {code}: "
                f"{actual_unit!r}; expected {expected_unit!r}"
            )

    food_units = {
        normalize_text(row["THSCODE"]): normalize_text(
            row["DESCRIPT"]
        )
        for row in food_unit_rows
        if normalize_text(row.get("LANG")).upper() == "EN"
    }

    for required_unit in EXPLICIT_SERVING_UNIT_PRIORITY:
        if required_unit not in food_units:
            raise RuntimeError(
                f"{label} is missing expected food-unit code "
                f"{required_unit!r}"
            )

    nutrients = defaultdict(dict)

    for row in value_rows:
        component = normalize_text(row.get("EUFDNAME"))

        if component not in SELECTED_COMPONENTS:
            continue

        food_id = normalize_text(row.get("FOODID"))
        value = parse_number(row.get("BESTLOC"))

        if component in nutrients[food_id]:
            raise RuntimeError(
                f"Duplicate component row inside {label}: "
                f"FOODID={food_id}, component={component}"
            )

        nutrients[food_id][component] = value

    additional_units = defaultdict(dict)

    for row in additional_unit_rows:
        food_id = normalize_text(row.get("FOODID"))
        unit_code = normalize_text(row.get("FOODUNIT"))
        mass_g = parse_number(row.get("MASS"))

        if not food_id or not unit_code or mass_g is None:
            continue

        if unit_code not in food_units:
            raise RuntimeError(
                f"Unknown Fineli FOODUNIT in {label}: "
                f"FOODID={food_id}, FOODUNIT={unit_code!r}"
            )

        if mass_g <= 0:
            raise RuntimeError(
                f"Non-positive Fineli unit mass in {label}: "
                f"FOODID={food_id}, FOODUNIT={unit_code}, "
                f"MASS={mass_g}"
            )

        previous = additional_units[food_id].get(
            unit_code
        )

        if previous is not None and previous != mass_g:
            raise RuntimeError(
                f"Conflicting duplicate food-unit row inside "
                f"{label}: FOODID={food_id}, "
                f"FOODUNIT={unit_code}, "
                f"{previous!r} vs {mass_g!r}"
            )

        additional_units[food_id][unit_code] = mass_g

    package = {
        "label": label,
        "path": zip_path,
        "foods": foods,
        "names": names,
        "nutrients": dict(nutrients),
        "additional_units": dict(additional_units),
        "component_count": len(components),
    }

    print(
        f"Loaded {label}: {len(foods)} foods, "
        f"{len(names)} English names, "
        f"{len(components)} components"
    )

    return package


def canonical_food_metadata(row):
    """
    Fields used to verify that a repeated FOODID really represents
    the same Fineli food across package variants.
    """
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
    overlapping_additional_units = 0

    for package in packages:
        label = package["label"]

        for food_id, food_row in package["foods"].items():
            english_name = package["names"].get(food_id)
            nutrient_values = package["nutrients"].get(
                food_id,
                {},
            )
            additional_units = package[
                "additional_units"
            ].get(
                food_id,
                {},
            )

            if not english_name:
                raise RuntimeError(
                    f"Missing English name in {label} for "
                    f"Fineli FOODID={food_id}"
                )

            if food_id not in merged:
                merged[food_id] = {
                    "food": food_row,
                    "english_name": english_name,
                    "nutrients": dict(nutrient_values),
                    "additional_units": dict(
                        additional_units
                    ),
                    "packages": [label],
                }
                continue

            duplicate_food_ids += 1
            current = merged[food_id]

            if (
                canonical_food_metadata(
                    current["food"]
                )
                != canonical_food_metadata(food_row)
            ):
                raise RuntimeError(
                    "Conflicting food metadata across "
                    f"Fineli packages for FOODID={food_id}"
                )

            if current["english_name"] != english_name:
                raise RuntimeError(
                    "Conflicting English name across Fineli "
                    f"packages for FOODID={food_id}: "
                    f"{current['english_name']!r} vs "
                    f"{english_name!r}"
                )

            for component, value in (
                nutrient_values.items()
            ):
                if component in current["nutrients"]:
                    overlapping_component_values += 1
                    previous = current["nutrients"][
                        component
                    ]

                    if previous != value:
                        raise RuntimeError(
                            "Conflicting Fineli component "
                            "value across packages: "
                            f"FOODID={food_id}, "
                            f"component={component}, "
                            f"{previous!r} vs {value!r}"
                        )
                else:
                    current["nutrients"][
                        component
                    ] = value

            for unit_code, mass_g in (
                additional_units.items()
            ):
                if (
                    unit_code
                    in current["additional_units"]
                ):
                    overlapping_additional_units += 1
                    previous = current[
                        "additional_units"
                    ][unit_code]

                    if previous != mass_g:
                        raise RuntimeError(
                            "Conflicting Fineli additional "
                            "unit across packages: "
                            f"FOODID={food_id}, "
                            f"FOODUNIT={unit_code}, "
                            f"{previous!r} vs {mass_g!r}"
                        )
                else:
                    current["additional_units"][
                        unit_code
                    ] = mass_g

            current["packages"].append(label)

    print(
        "Merged repeated FOODIDs across package inputs: "
        f"{duplicate_food_ids}"
    )
    print(
        "Verified identical overlapping component values: "
        f"{overlapping_component_values}"
    )
    print(
        "Verified identical overlapping food-unit values: "
        f"{overlapping_additional_units}"
    )

    return merged


def choose_explicit_serving(record):
    """
    Return an app-facing serving mass only when Fineli supplies a
    sufficiently explicit serving source.

    Generic small/medium/large portions are intentionally ignored.

    Returns:
        (serving_size_g, "g", source_unit_code)
        or
        (None, None, None)
    """
    units = record.get("additional_units", {})

    for unit_code in EXPLICIT_SERVING_UNIT_PRIORITY:
        mass_g = units.get(unit_code)

        if mass_g is None:
            continue

        if mass_g <= 0:
            raise RuntimeError(
                "Invalid explicit Fineli serving mass: "
                f"{unit_code}={mass_g}"
            )

        return (
            round(float(mass_g), 2),
            "g",
            unit_code,
        )

    return None, None, None


def is_confident_liquid(food_row):
    """
    Classify only foods whose Fineli food-use classification
    unambiguously identifies them as liquids.

    This function intentionally does not inspect the food name or
    volume-unit availability.
    """
    food_class = normalize_text(
        food_row.get("FUCLASS")
    ).upper()

    parent_class = normalize_text(
        food_row.get("FUCLASSP")
    ).upper()

    return (
        parent_class in LIQUID_PARENT_CLASSES
        or food_class in LIQUID_PARENT_CLASSES
        or food_class in LIQUID_DIRECT_CLASSES
    )


def make_pack_item(food_id, record):
    nutrients = record["nutrients"]

    # A few rows exist in food.csv without any of the selected
    # nutrient values. Do not invent nutrition for those records.
    if not any(
        component in nutrients
        for component in SELECTED_COMPONENTS
    ):
        return None

    energy_kj = (
        nutrients.get(COMPONENT_ENERGY_KJ) or 0.0
    )
    fat = nutrients.get(COMPONENT_FAT_G) or 0.0
    carbs = (
        nutrients.get(COMPONENT_CARBS_G) or 0.0
    )
    protein = (
        nutrients.get(COMPONENT_PROTEIN_G) or 0.0
    )

    # Nutrient fields remain on Fineli's documented 100 g basis.
    # Do not scale them by servingSize.
    calories = energy_kj / 4.184

    (
        serving_size,
        serving_unit,
        _serving_source_unit,
    ) = choose_explicit_serving(record)

    return {
        "name": sentence_case_all_caps(
            record["english_name"]
        ),
        "brand": None,
        "barcode": None,
        "calories": round(calories, 2),
        "protein": round(protein, 2),
        "carbs": round(carbs, 2),
        "fat": round(fat, 2),
        "servingSize": serving_size,
        "servingUnit": serving_unit,
        "isLiquid": is_confident_liquid(
            record["food"]
        ),
        "source": FINELI_SOURCE_ID,
        "sourceItemId": str(food_id),
    }


def deduplicate_output_items(items):
    """
    Secondary cross-ID duplicate guard.

    Fineli FOODID remains the primary identity. Different FOODIDs are
    only collapsed if every app-facing value that can distinguish the
    records is identical.

    No fuzzy name matching is performed.
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
            item["servingSize"],
            item["servingUnit"],
            item["isLiquid"],
        )

        previous = seen.get(key)

        if previous is not None:
            duplicate_count += 1
            continue

        seen[key] = item
        unique.append(item)

    print(
        "Removed exact cross-ID duplicates after "
        f"normalization: {duplicate_count}"
    )

    return unique


def validate_output_items(items, merged):
    """
    Final safety audit.

    This specifically protects against the error we want to avoid:
    accidentally treating a serving mass as the nutrient basis.

    Every output macro is re-derived directly from the Fineli
    component values, independently of servingSize and isLiquid.
    """
    explicit_serving_count = 0
    liquid_count = 0
    serving_source_counts = defaultdict(int)

    for item in items:
        food_id = item["sourceItemId"]

        if food_id not in merged:
            raise RuntimeError(
                "Generated item references unknown Fineli "
                f"FOODID={food_id}"
            )

        record = merged[food_id]
        nutrients = record["nutrients"]

        expected = {
            "calories": round(
                (
                    nutrients.get(
                        COMPONENT_ENERGY_KJ
                    )
                    or 0.0
                )
                / 4.184,
                2,
            ),
            "protein": round(
                nutrients.get(
                    COMPONENT_PROTEIN_G
                )
                or 0.0,
                2,
            ),
            "carbs": round(
                nutrients.get(
                    COMPONENT_CARBS_G
                )
                or 0.0,
                2,
            ),
            "fat": round(
                nutrients.get(COMPONENT_FAT_G)
                or 0.0,
                2,
            ),
        }

        for field, expected_value in expected.items():
            if item[field] != expected_value:
                raise RuntimeError(
                    "Fineli output audit failed for "
                    f"FOODID={food_id}, field={field}: "
                    f"generated={item[field]!r}, "
                    f"expected={expected_value!r}"
                )

        (
            expected_serving_size,
            expected_serving_unit,
            serving_source_unit,
        ) = choose_explicit_serving(record)

        if (
            item["servingSize"]
            != expected_serving_size
            or item["servingUnit"]
            != expected_serving_unit
        ):
            raise RuntimeError(
                "Fineli serving audit failed for "
                f"FOODID={food_id}: "
                f"generated="
                f"({item['servingSize']!r}, "
                f"{item['servingUnit']!r}), "
                f"expected="
                f"({expected_serving_size!r}, "
                f"{expected_serving_unit!r})"
            )

        if serving_source_unit is not None:
            explicit_serving_count += 1
            serving_source_counts[
                serving_source_unit
            ] += 1

        expected_liquid = is_confident_liquid(
            record["food"]
        )

        if item["isLiquid"] != expected_liquid:
            raise RuntimeError(
                "Fineli liquid audit failed for "
                f"FOODID={food_id}: "
                f"generated={item['isLiquid']!r}, "
                f"expected={expected_liquid!r}"
            )

        if expected_liquid:
            liquid_count += 1

    print(
        f"Audited {len(items)} generated items against "
        "raw Fineli nutrition values: 0 mismatches"
    )
    print(
        "Items with explicit Fineli serving mass: "
        f"{explicit_serving_count}"
    )

    for unit_code in EXPLICIT_SERVING_UNIT_PRIORITY:
        print(
            f"  {unit_code}: "
            f"{serving_source_counts.get(unit_code, 0)}"
        )

    print(
        "Items conservatively classified as liquid: "
        f"{liquid_count}"
    )


def write_json(path, payload):
    os.makedirs(
        os.path.dirname(path),
        exist_ok=True,
    )

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as output_file:
        json.dump(
            payload,
            output_file,
            ensure_ascii=False,
            indent=2,
        )


def build_fineli_pack():
    packages = [
        load_fineli_package(label, path)
        for label, path in SOURCE_PACKAGES
    ]

    merged = merge_packages(packages)

    items = []
    skipped_without_selected_nutrients = 0

    for food_id in sorted(
        merged,
        key=lambda value: int(value),
    ):
        item = make_pack_item(
            food_id,
            merged[food_id],
        )

        if item is None:
            skipped_without_selected_nutrients += 1
            continue

        items.append(item)

    items = deduplicate_output_items(items)

    # Run the full source-vs-output audit before any file is written.
    validate_output_items(items, merged)

    items.sort(
        key=lambda item: (
            item["name"].casefold(),
            int(item["sourceItemId"]),
        )
    )

    output_dir = os.path.join(
        OUTPUT_ROOT,
        "FI",
    )
    national_path = os.path.join(
        output_dir,
        "national.json",
    )
    national_relative_path = (
        "countries/FI/national.json"
    )
    manifest_path = os.path.join(
        output_dir,
        "national_manifest.json",
    )

    write_json(
        national_path,
        items,
    )

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
            (
                "combined Fineli Basic package 1, "
                "Basic package 2 and Ingredients for "
                "food industry"
            ),
            "used English food names only",
            (
                "converted all-uppercase English food "
                "names to sentence case"
            ),
            (
                "selected energy, protein, available "
                "carbohydrate and total fat fields"
            ),
            (
                "converted Fineli energy values from "
                "kilojoules per 100 g to kilocalories "
                "per 100 g"
            ),
            (
                "kept app-facing nutrient values on "
                "Fineli's documented 100 g basis and "
                "did not rescale them by serving size "
                "or liquid status"
            ),
            (
                "normalized nutrient values to the "
                "MostoFit food schema"
            ),
            (
                "set brand and barcode to null because "
                "these fields are not supplied by the "
                "selected Fineli data"
            ),
            (
                "used an explicit serving mass only "
                "when Fineli supplied a manufacturer "
                "piece or food-composition-table portion; "
                "otherwise left serving size and unit null"
            ),
            (
                "stored accepted Fineli serving masses "
                "in grams using the MASS field from "
                "foodaddunit.csv"
            ),
            (
                "classified liquids conservatively from "
                "explicit Fineli food-use classification "
                "codes and did not infer liquid status "
                "from names or volume-unit availability"
            ),
            (
                "deduplicated records across the three "
                "Fineli packages by Fineli FOODID and "
                "verified overlapping nutrient and "
                "food-unit values"
            ),
            (
                "removed records that had none of the "
                "selected app-facing nutrient values"
            ),
            "converted the source CSV data to JSON",
        ],
        generated_at=generated_at,
        record_count=len(items),
        files=[file_entry],
        extra_fields={
            "owner": FINELI_PUBLISHER,
            "itemCount": len(items),
            "file": national_relative_path,
            "sourceFiles": [
                path.replace("\\", "/")
                for _, path in SOURCE_PACKAGES
            ],
            "copyright": FINELI_COPYRIGHT,
            "attribution": (
                "Fineli - Finnish Food Composition "
                "Database, Release 20.0, Finnish "
                "Institute for Health and Welfare (THL), "
                "CC BY 4.0. Modified by MostoFit."
            ),
        },
    )

    write_json(
        manifest_path,
        manifest,
    )

    print(
        "Skipped foods with no selected nutrient "
        f"values: {skipped_without_selected_nutrients}"
    )
    print(
        f"Saved Fineli national pack: {len(items)} items"
    )
    print(f"Output: {national_path}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    build_fineli_pack()
