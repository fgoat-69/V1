import csv
import gzip
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone

import requests

from manifest_utils import (
    build_file_entry,
    build_standard_manifest,
    utc_now_iso,
)

csv.field_size_limit(sys.maxsize)

DUMP_URL = os.getenv(
    "OFF_DUMP_URL",
    "https://static.openfoodfacts.org/data/en.openfoodfacts.org.products.csv.gz",
)
DOWNLOAD_STALL_TIMEOUT_SECONDS = int(os.getenv("OFF_DOWNLOAD_STALL_TIMEOUT_SECONDS", "120"))
DOWNLOAD_CHUNK_SIZE = 1024 * 1024

TARGET_TOTAL_BYTES = 7_000_000
TARGET_MAIN_BYTES = 5_000_000
FULL_PACK_MAX_ITEMS = 15_000

CACHE_DIR = ".cache"
DUMP_FILENAME = os.getenv("OFF_DUMP_FILENAME", "en.openfoodfacts.org.products.csv.gz")
DUMP_PATH = os.path.join(CACHE_DIR, DUMP_FILENAME)
OFF_SOURCE_NAME = "Open Food Facts"
OFF_PUBLISHER = "Open Food Facts"

OFF_DATABASE_LICENSE_ID = "ODbL-1.0"
OFF_DATABASE_LICENSE_URL = (
    "https://opendatacommons.org/licenses/odbl/1-0/"
)

OFF_CONTENTS_LICENSE_ID = "DbCL-1.0"
OFF_CONTENTS_LICENSE_URL = (
    "https://opendatacommons.org/licenses/dbcl/1-0/"
)

OFF_SOURCE_PAGE_URL = "https://world.openfoodfacts.org/data"

OFF_ATTRIBUTION = (
    "Contains information from Open Food Facts, which is made available "
    "under the Open Database License (ODbL)."
)

USER_AGENT = os.getenv(
    "OFF_USER_AGENT",
    "MostoFitCountryPackBuilder/1.0 (contact-required-set-OFF_USER_AGENT)",
)

LIQUID_HINTS = {
    "water", "milk", "juice", "cola", "soda", "oil", "syrup", "tea", "coffee",
    "lemonade", "shake", "broth", "stock", "drink", "smoothie", "vinegar",
    "cider", "liquor", "wine", "beer", "yogurt"
}


def normalize_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def normalize_key(item):
    barcode = str(item.get("barcode") or "").strip()
    if barcode:
        return f"bc:{barcode}"

    name = normalize_text(item.get("name"))
    brand = normalize_text(item.get("brand"))

    if name or brand:
        return f"nb:{name}|{brand}"

    return None


def split_csv_like_string(value):
    if not value:
        return []
    return [part.strip() for part in str(value).split(",") if part.strip()]


def to_float(value):
    if value in (None, ""):
        return None

    text = str(value).strip().replace(",", ".")
    if not text:
        return None

    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def first_number(*values):
    for value in values:
        if value is not None:
            return value
    return None


def first_text(*values):
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def first_brand(brands):
    if not brands:
        return None
    return str(brands).split(",")[0].strip() or None


def parse_serving_size(raw):
    if not raw:
        return None, None

    text = str(raw).strip()
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*([a-zA-Z]+)", text)
    if not match:
        return None, None

    size = match.group(1).replace(",", ".")
    unit = match.group(2).strip().lower()

    try:
        size_value = float(size)
    except ValueError:
        return None, None

    if unit in {"l", "liter", "litre", "liters", "litres"}:
        return size_value * 1000.0, "ml"
    if unit == "dl":
        return size_value * 100.0, "ml"
    if unit == "cl":
        return size_value * 10.0, "ml"
    if unit == "ml":
        return size_value, "ml"

    if unit in {"kg", "kilogram", "kilograms"}:
        return size_value * 1000.0, "g"
    if unit in {"g", "gram", "grams"}:
        return size_value, "g"

    return size_value, unit


def looks_liquid(name, serving_unit):
    if (serving_unit or "").lower() == "ml":
        return True

    lowered = normalize_text(name)
    return any(token in lowered for token in LIQUID_HINTS)


def get_popularity_score(product):
    for key in (
        "unique_scans_n",
        "scans_n",
        "popularity_key",
        "completeness",
    ):
        raw = product.get(key)
        if raw in (None, ""):
            continue

        try:
            return int(float(raw))
        except (TypeError, ValueError):
            continue

    return 0


def product_country_tokens(product):
    values = []

    for key in (
        "countries",
        "countries_en",
        "countries_tags",
        "main_countries_tags",
    ):
        raw = product.get(key)

        if isinstance(raw, list):
            values.extend(raw)
        elif isinstance(raw, str):
            values.extend(split_csv_like_string(raw))

    normalized = set()

    for value in values:
        token = str(value).strip().lower()
        if not token:
            continue

        normalized.add(token)

        if ":" in token:
            normalized.add(token.split(":", 1)[1])

    return normalized


def product_matches_country(product, country_iso2, slug):
    tokens = product_country_tokens(product)
    iso2 = (country_iso2 or "").strip().lower()
    slug = (slug or "").strip().lower()

    return (slug and slug in tokens) or (iso2 and iso2 in tokens)

def map_product(product):
    name = first_text(
        product.get("product_name"),
        product.get("product_name_en"),
        product.get("generic_name"),
        product.get("generic_name_en"),
    )

    if not name:
        return None

    # App-facing nutrient values are always per 100 g.
    # Do not substitute per-serving values into these fields.
    kcal = to_float(product.get("energy-kcal_100g"))

    energy_kj = first_number(
        to_float(product.get("energy-kj_100g")),
        to_float(product.get("energy_100g")),
    )

    if kcal is None and energy_kj is not None:
        kcal = energy_kj / 4.184

    protein = to_float(product.get("proteins_100g"))
    carbs = to_float(product.get("carbohydrates_100g"))
    fat = to_float(product.get("fat_100g"))
    kcal = 0.0 if kcal is None else kcal
    protein = 0.0 if protein is None else protein
    carbs = 0.0 if carbs is None else carbs
    fat = 0.0 if fat is None else fat

    if kcal == 0.0 and protein == 0.0 and carbs == 0.0 and fat == 0.0:
        return None

    brand = first_brand(product.get("brands"))
    barcode = str(product.get("code") or "").strip() or None

    serving_size = None
    serving_unit = None

    raw_serving = product.get("serving_size")
    if raw_serving:
        serving_size, serving_unit = parse_serving_size(raw_serving)

    if serving_size is None:
        quantity_value = to_float(product.get("serving_quantity"))
        if quantity_value is not None:
            serving_size = quantity_value

    is_liquid = looks_liquid(name, serving_unit)

    if is_liquid and (not serving_unit or serving_unit == "g"):
        serving_unit = "ml"

    return {
        "name": name,
        "brand": brand,
        "barcode": barcode,
        "calories": round(kcal, 2),
        "protein": round(protein, 2),
        "carbs": round(carbs, 2),
        "fat": round(fat, 2),
        "servingSize": round(serving_size, 2) if isinstance(serving_size, (int, float)) else None,
        "servingUnit": serving_unit,
        "isLiquid": is_liquid,
        "source": "openfoodfacts",
        "_sortScore": get_popularity_score(product),
    }


def json_bytes(data):
    return len(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def save_json(path, payload):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def ensure_dump(download_if_missing=True, force_download=False):
    ensure_cache_dir()

    if os.path.exists(DUMP_PATH) and not force_download:
        return DUMP_PATH

    if not download_if_missing:
        raise FileNotFoundError(
            f"OFF CSV dump not found at {DUMP_PATH}. Download it first or allow auto-download."
        )

    print(f"Downloading OFF CSV dump from {DUMP_URL}")
    temp_path = f"{DUMP_PATH}.part"

    if os.path.exists(temp_path):
        os.remove(temp_path)

    try:
        response = requests.get(
            DUMP_URL,
            stream=True,
            timeout=(30, DOWNLOAD_STALL_TIMEOUT_SECONDS),
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()

        total_bytes = int(response.headers.get("Content-Length", "0") or "0")
        downloaded_bytes = 0
        last_reported_mb = -1

        if total_bytes > 0:
            print(f"OFF CSV dump size: {round(total_bytes / (1024 * 1024), 2)} MB")

        with open(temp_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                if not chunk:
                    continue

                f.write(chunk)
                downloaded_bytes += len(chunk)

                downloaded_mb = downloaded_bytes // (1024 * 1024)
                if downloaded_mb != last_reported_mb:
                    last_reported_mb = downloaded_mb

                    if total_bytes > 0:
                        percent = round((downloaded_bytes / total_bytes) * 100, 2)
                        print(
                            f"Downloaded {downloaded_mb} MB / "
                            f"{round(total_bytes / (1024 * 1024), 2)} MB "
                            f"({percent}%)"
                        )
                    else:
                        print(f"Downloaded {downloaded_mb} MB")

        shutil.move(temp_path, DUMP_PATH)
        return DUMP_PATH

    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def iter_dump_products(dump_path):
    with gzip.open(dump_path, "rt", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for line_number, row in enumerate(reader, start=1):
            yield line_number, row


def strip_internal_fields(items):
    cleaned = []
    for item in items:
        cleaned.append({
            "name": item.get("name"),
            "brand": item.get("brand"),
            "barcode": item.get("barcode"),
            "calories": item.get("calories"),
            "protein": item.get("protein"),
            "carbs": item.get("carbs"),
            "fat": item.get("fat"),
            "servingSize": item.get("servingSize"),
            "servingUnit": item.get("servingUnit"),
            "isLiquid": item.get("isLiquid"),
            "source": item.get("source"),
        })
    return cleaned


def split_items_by_budget(items, main_budget_bytes, total_budget_bytes):
    main_items = []
    fill_items = []

    main_bytes = 2
    total_bytes = 2

    for item in items:
        item_bytes = json_bytes(item)
        separator_bytes = 1

        projected_main = main_bytes + item_bytes + (separator_bytes if main_items else 0)
        projected_total = total_bytes + item_bytes + (separator_bytes if (main_items or fill_items) else 0)

        if projected_main <= main_budget_bytes:
            main_items.append(item)
            main_bytes = projected_main
            total_bytes = projected_total
            continue

        if projected_total <= total_budget_bytes:
            fill_items.append(item)
            total_bytes = projected_total
            continue

        break

    return main_items, fill_items


def sort_discovered_items(items):
    items.sort(
        key=lambda item: (
            -item.get("_sortScore", 0),
            normalize_text(item.get("name")),
            normalize_text(item.get("brand")),
            normalize_text(item.get("barcode")),
        )
    )
    return items


def build_country(country_iso2, slug, download_if_missing=True, force_download=False):
    print(f"Building {country_iso2} ({slug}) from CSV dump")

    dump_path = ensure_dump(
        download_if_missing=download_if_missing,
        force_download=force_download,
    )

    seen = set()
    items = []

    scanned_products = 0
    matched_products = 0
    mapped_products = 0
    deduped_products = 0
    skipped_no_name = 0
    skipped_no_key = 0
    skipped_no_nutrition = 0

    for _, product in iter_dump_products(dump_path):
        scanned_products += 1

        if not product_matches_country(product, country_iso2, slug):
            continue

        matched_products += 1

        mapped = map_product(product)
        if not mapped:
            skipped_no_nutrition += 1
            continue

        mapped_products += 1

        key = normalize_key(mapped)
        if not key:
            skipped_no_key += 1
            continue

        if key in seen:
            deduped_products += 1
            continue

        seen.add(key)
        items.append(mapped)

    sort_discovered_items(items)

    discovered_items = strip_internal_fields(items)
    discovered_count = len(discovered_items)
    discovered_size = json_bytes(discovered_items)

    build_meta = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "discoveryMethod": "off_csv_dump_country_filter",
        "coverageNote": (
            "This build is generated from the OFF CSV dump with country filtering, "
            "app-field reduction, nutrition filtering, and deduplication. Products with "
            "completely empty calories/protein/carbs/fat are skipped. Large countries are "
            "popularity-sorted using OFF popularity fields when available before budget-based packaging."
        ),
        "dumpUrl": DUMP_URL,
        "dumpCachePath": dump_path,
        "fullPackMaxItems": FULL_PACK_MAX_ITEMS,
        "targetTotalBytes": TARGET_TOTAL_BYTES,
        "targetMainBytes": TARGET_MAIN_BYTES,
        "scannedProducts": scanned_products,
        "matchedProducts": matched_products,
        "mappedProducts": mapped_products,
        "dedupedProducts": deduped_products,
        "skippedNoName": skipped_no_name,
        "skippedNoKey": skipped_no_key,
        "skippedNoNutrition": skipped_no_nutrition,
        "discoveredItemCount": discovered_count,
        "discoveredBytes": discovered_size,
    }

    return discovered_items, build_meta

def remove_existing_off_outputs(country_path):
    for filename in (
        "full.json",
        "main.json",
        "fill.json",
        "manifest.json",
    ):
        file_path = os.path.join(country_path, filename)

        if os.path.isfile(file_path):
            os.remove(file_path)
            
def save_country(country_iso2, slug, items, build_meta):
    country_iso2 = country_iso2.strip().upper()

    path = os.path.join("countries", country_iso2)
    os.makedirs(path, exist_ok=True)

    remove_existing_off_outputs(path)

    discovered_item_count = len(items)
    discovered_bytes = json_bytes(items)

    can_be_full = (
        discovered_item_count <= FULL_PACK_MAX_ITEMS
        and discovered_bytes <= TARGET_TOTAL_BYTES
    )

    file_entries = []

    strategy = ""
    item_count_main = 0
    item_count_fill = 0

    if can_be_full:
        strategy = "full"

        full_filename = "full.json"
        full_relative_path = (
            f"countries/{country_iso2}/{full_filename}"
        )
        full_path = os.path.join(path, full_filename)

        save_json(full_path, items)

        item_count_main = len(items)

        file_entries.append(
            build_file_entry(
                file_path=full_path,
                relative_path=full_relative_path,
                kind="full",
                record_count=len(items),
            )
        )

    else:
        strategy = "main_fill"

        main_items, fill_items = split_items_by_budget(
            items=items,
            main_budget_bytes=TARGET_MAIN_BYTES,
            total_budget_bytes=TARGET_TOTAL_BYTES,
        )

        main_filename = "main.json"
        main_relative_path = (
            f"countries/{country_iso2}/{main_filename}"
        )
        main_path = os.path.join(path, main_filename)

        save_json(main_path, main_items)

        item_count_main = len(main_items)
        item_count_fill = len(fill_items)

        file_entries.append(
            build_file_entry(
                file_path=main_path,
                relative_path=main_relative_path,
                kind="main",
                record_count=len(main_items),
            )
        )

        if fill_items:
            fill_filename = "fill.json"
            fill_relative_path = (
                f"countries/{country_iso2}/{fill_filename}"
            )
            fill_path = os.path.join(path, fill_filename)

            save_json(fill_path, fill_items)

            file_entries.append(
                build_file_entry(
                    file_path=fill_path,
                    relative_path=fill_relative_path,
                    kind="fill",
                    record_count=len(fill_items),
                )
            )

    packaged_record_count = sum(
        entry["recordCount"]
        for entry in file_entries
    )

    generated_at = str(
        build_meta.get("generatedAt") or utc_now_iso()
    )
    dataset_version = generated_at.split("T", 1)[0]

    compatibility_pack_files = [
        {
            "name": entry["name"],
            "path": entry["path"],
            "kind": entry["kind"],
            "itemCount": entry["recordCount"],
            "recordCount": entry["recordCount"],
            "bytes": entry["bytes"],
            "sha256": entry["sha256"],
        }
        for entry in file_entries
    ]

    manifest = build_standard_manifest(
        pack_id=(
            f"off_{country_iso2.lower()}_"
            f"{dataset_version.replace('-', '_')}"
        ),
        pack_type="openfoodfacts",
        country_iso2=country_iso2,
        source="openfoodfacts",
        source_name=OFF_SOURCE_NAME,
        publisher=OFF_PUBLISHER,
        dataset_version=dataset_version,
        license_id=OFF_DATABASE_LICENSE_ID,
        source_url=OFF_SOURCE_PAGE_URL,
        license_url=OFF_DATABASE_LICENSE_URL,
        modified=True,
        modifications=[
            "filtered the Open Food Facts export by country tags",
            "reduced records to fields used by the MostoFit food schema",
            "selected energy, protein, carbohydrate and fat values per 100 g",
            "converted energy from kilojoules per 100 g to kilocalories per 100 g when required",
            "set missing selected nutrient values to zero",
            "removed products with no usable name",
            "removed products where all selected nutrition values were zero",
            "preserved the Open Food Facts barcode where available",
            "normalized serving quantities and units",
            "inferred liquid status from serving units and food-name hints",
            "deduplicated by barcode with normalized name and brand as a fallback",
            "sorted products using Open Food Facts popularity information where available",
            "limited large packs to the configured app download-size budget",
            "split large country packs into main and fill files",
            "converted the Open Food Facts export to app-facing JSON",
        ],
        generated_at=generated_at,
        record_count=packaged_record_count,
        files=file_entries,
        extra_fields={
            "slug": slug,
            "version": int(time.time()),
            "strategy": strategy,
            "itemCountDiscovered": discovered_item_count,
            "bytesDiscovered": discovered_bytes,
            "itemCountTotal": packaged_record_count,
            "itemCountMain": item_count_main,
            "itemCountFill": item_count_fill,
            "targetTotalBytes": TARGET_TOTAL_BYTES,
            "targetMainBytes": TARGET_MAIN_BYTES,
            "packFiles": compatibility_pack_files,
            "buildMeta": build_meta,
            "contentsLicense": OFF_CONTENTS_LICENSE_ID,
            "contentsLicenseUrl": OFF_CONTENTS_LICENSE_URL,
            "attribution": OFF_ATTRIBUTION,
            "databaseNotice": (
                "This modified Open Food Facts country database "
                "is distributed under ODbL 1.0."
            ),
            "contentsNotice": (
                "Individual database contents are available "
                "under DbCL 1.0."
            ),
            "containsProductImages": False,
        },
    )

    manifest_path = os.path.join(path, "manifest.json")
    save_json(manifest_path, manifest)

    print(
        f"Saved {country_iso2}: strategy={strategy} "
        f"discovered={discovered_item_count} "
        f"packaged={packaged_record_count}"
    )

    return manifest

if __name__ == "__main__":
    built_items, built_meta = build_country("HU", "hungary")
    save_country("HU", "hungary", built_items, built_meta)
