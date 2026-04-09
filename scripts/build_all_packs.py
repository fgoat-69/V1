import gzip
import json
import os
import re
import shutil
import time
from datetime import datetime, timezone

import requests

DUMP_URL = "https://static.openfoodfacts.org/data/openfoodfacts-products.jsonl.gz"
REQUEST_TIMEOUT_SECONDS = 120
DOWNLOAD_CHUNK_SIZE = 1024 * 1024

# Packaging rules
TARGET_TOTAL_BYTES = 7_000_000
TARGET_MAIN_BYTES = 5_000_000
FULL_PACK_MAX_ITEMS = 15_000

# Local cache
CACHE_DIR = ".cache"
DUMP_FILENAME = "openfoodfacts-products.jsonl.gz"
DUMP_PATH = os.path.join(CACHE_DIR, DUMP_FILENAME)

LIQUID_HINTS = {
    "water", "milk", "juice", "cola", "soda", "oil", "syrup", "tea", "coffee",
    "lemonade", "shake", "broth", "stock", "drink", "smoothie", "vinegar",
    "cider", "liquor", "wine", "beer", "yogurt"
}


def normalize_text(value):
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def normalize_key(item):
    barcode = (item.get("barcode") or "").strip()
    if barcode:
        return f"bc:{barcode}"

    name = normalize_text(item.get("name"))
    brand = normalize_text(item.get("brand"))
    return f"nb:{name}|{brand}"


def parse_serving_size(raw):
    if not raw:
        return None, None

    match = re.search(r"(\d+(?:[.,]\d+)?)\s*([a-zA-Z]+)", str(raw).strip())
    if not match:
        return None, None

    size = match.group(1).replace(",", ".")
    unit = match.group(2).strip().lower()

    try:
        size_value = float(size)
    except ValueError:
        return None, None

    if unit in {"ml", "l", "cl", "dl", "liter", "litre"}:
        if unit == "l":
            return size_value * 1000.0, "ml"
        if unit == "cl":
            return size_value * 10.0, "ml"
        if unit == "dl":
            return size_value * 100.0, "ml"
        return size_value, "ml"

    if unit in {"g", "gram", "grams"}:
        return size_value, "g"

    return size_value, unit


def looks_liquid(name, serving_unit):
    if (serving_unit or "").lower() == "ml":
        return True

    lowered = normalize_text(name)
    return any(token in lowered for token in LIQUID_HINTS)


def first_brand(brands):
    if not brands:
        return None

    if isinstance(brands, list):
        first = next((str(x).strip() for x in brands if str(x).strip()), None)
        return first or None

    return str(brands).split(",")[0].strip() or None


def to_float(value):
    if value in (None, ""):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_nutriments(product):
    nutr = product.get("nutriments")
    if isinstance(nutr, dict):
        return nutr
    return {}


def get_popularity_score(product):
    raw = (
        product.get("unique_scans_n")
        or product.get("scans_n")
        or product.get("popularity_key")
        or 0
    )

    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return 0


def product_country_tokens(product):
    values = []

    for key in ("countries_tags", "countries_tags_en"):
        raw = product.get(key)
        if isinstance(raw, list):
            values.extend(raw)
        elif isinstance(raw, str):
            values.extend([part.strip() for part in raw.split(",") if part.strip()])

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

    if slug in tokens:
        return True

    if iso2 and iso2 in tokens:
        return True

    return False


def map_product(product):
    nutr = get_nutriments(product)

    kcal = to_float(nutr.get("energy-kcal_100g"))
    protein = to_float(nutr.get("proteins_100g"))
    carbs = to_float(nutr.get("carbohydrates_100g"))
    fat = to_float(nutr.get("fat_100g"))

    kcal = 0.0 if kcal is None else kcal
    protein = 0.0 if protein is None else protein
    carbs = 0.0 if carbs is None else carbs
    fat = 0.0 if fat is None else fat

    if kcal == 0 and protein == 0 and carbs == 0 and fat == 0:
        return None

    name = (product.get("product_name") or "").strip()
    if not name:
        return None

    brand = first_brand(product.get("brands"))
    barcode = (product.get("code") or "").strip() or None

    serving_size = None
    serving_unit = None

    raw_serving = product.get("serving_size")
    if raw_serving:
        serving_size, serving_unit = parse_serving_size(raw_serving)

    if serving_size is None:
        quantity = product.get("serving_quantity")
        quantity_value = to_float(quantity)
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
        "source": "github_country_pack",
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
            f"OFF dump not found at {DUMP_PATH}. Download it first or allow auto-download."
        )

    print(f"Downloading OFF JSONL dump from {DUMP_URL}")
    temp_path = f"{DUMP_PATH}.part"

    response = requests.get(
        DUMP_URL,
        stream=True,
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={
            "User-Agent": "MostoFitCountryPackBuilder/1.0 (replace-with-your-email@example.com)"
        },
    )
    response.raise_for_status()

    with open(temp_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
            if chunk:
                f.write(chunk)

    shutil.move(temp_path, DUMP_PATH)
    return DUMP_PATH


def iter_dump_products(dump_path):
    with gzip.open(dump_path, "rt", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                yield line_number, json.loads(line)
            except json.JSONDecodeError:
                continue


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


def build_country(country_iso2, slug, download_if_missing=True, force_download=False):
    print(f"Building {country_iso2} ({slug}) from dump")

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

    for _, product in iter_dump_products(dump_path):
        scanned_products += 1

        if not product_matches_country(product, country_iso2, slug):
            continue

        matched_products += 1

        mapped = map_product(product)
        if not mapped:
            continue

        mapped_products += 1

        key = normalize_key(mapped)
        if key in seen:
            deduped_products += 1
            continue

        seen.add(key)
        items.append(mapped)

    items.sort(
        key=lambda item: (
            item.get("_sortScore", 0),
            normalize_text(item.get("name")),
            normalize_text(item.get("brand")),
        ),
        reverse=True,
    )

    discovered_items = strip_internal_fields(items)
    discovered_count = len(discovered_items)
    discovered_size = json_bytes(discovered_items)

    build_meta = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "discoveryMethod": "off_jsonl_dump_country_filter",
        "coverageNote": (
            "This build is generated from the OFF JSONL dump with country filtering, "
            "app-field reduction, and deduplication. Large countries are popularity-sorted "
            "using OFF popularity fields when available before budget-based packaging."
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
        "discoveredItemCount": discovered_count,
        "discoveredBytes": discovered_size,
    }

    return discovered_items, build_meta


def save_country(country_iso2, slug, items, build_meta):
    path = os.path.join("countries", country_iso2)
    os.makedirs(path, exist_ok=True)

    discovered_item_count = len(items)
    discovered_bytes = json_bytes(items)

    can_be_full = (
        discovered_item_count <= FULL_PACK_MAX_ITEMS
        and discovered_bytes <= TARGET_TOTAL_BYTES
    )

    manifest = {
        "countryIso2": country_iso2,
        "slug": slug,
        "version": int(time.time()),
        "generatedAt": build_meta["generatedAt"],
        "strategy": None,
        "itemCountDiscovered": discovered_item_count,
        "bytesDiscovered": discovered_bytes,
        "itemCountTotal": 0,
        "itemCountMain": 0,
        "itemCountFill": 0,
        "targetTotalBytes": TARGET_TOTAL_BYTES,
        "targetMainBytes": TARGET_MAIN_BYTES,
        "packFiles": [],
        "buildMeta": build_meta,
    }

    if can_be_full:
        full_filename = "full.json"
        full_relative_path = f"countries/{country_iso2}/{full_filename}"
        full_path = os.path.join(path, full_filename)

        save_json(full_path, items)

        manifest["strategy"] = "full"
        manifest["itemCountTotal"] = len(items)
        manifest["itemCountMain"] = len(items)
        manifest["itemCountFill"] = 0
        manifest["packFiles"].append({
            "name": full_filename,
            "path": full_relative_path,
            "kind": "full",
            "itemCount": len(items),
            "bytes": json_bytes(items),
        })
    else:
        main_items, fill_items = split_items_by_budget(
            items=items,
            main_budget_bytes=TARGET_MAIN_BYTES,
            total_budget_bytes=TARGET_TOTAL_BYTES,
        )

        main_filename = "main.json"
        main_relative_path = f"countries/{country_iso2}/{main_filename}"
        main_path = os.path.join(path, main_filename)
        save_json(main_path, main_items)

        manifest["strategy"] = "main_fill"
        manifest["itemCountMain"] = len(main_items)
        manifest["itemCountFill"] = len(fill_items)
        manifest["itemCountTotal"] = len(main_items) + len(fill_items)
        manifest["packFiles"].append({
            "name": main_filename,
            "path": main_relative_path,
            "kind": "main",
            "itemCount": len(main_items),
            "bytes": json_bytes(main_items),
        })

        if fill_items:
            fill_filename = "fill.json"
            fill_relative_path = f"countries/{country_iso2}/{fill_filename}"
            fill_path = os.path.join(path, fill_filename)
            save_json(fill_path, fill_items)

            manifest["packFiles"].append({
                "name": fill_filename,
                "path": fill_relative_path,
                "kind": "fill",
                "itemCount": len(fill_items),
                "bytes": json_bytes(fill_items),
            })

    manifest_path = os.path.join(path, "manifest.json")
    save_json(manifest_path, manifest)

    print(
        f"Saved {country_iso2}: strategy={manifest['strategy']} "
        f"discovered={discovered_item_count} packaged={manifest['itemCountTotal']}"
    )

    return manifest


if __name__ == "__main__":
    built_items, built_meta = build_country("HU", "hungary")
    save_country("HU", "hungary", built_items, built_meta)
