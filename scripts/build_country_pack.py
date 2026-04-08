import json
import os
import re
import time
from datetime import datetime, timezone

import requests

BASE_URL = "https://world.openfoodfacts.org/cgi/search.pl"
FIELDS = "product_name,brands,code,nutriments,serving_size,serving_quantity"
REQUEST_TIMEOUT_SECONDS = 30

# Packaging rules
TARGET_TOTAL_BYTES = 7_000_000
TARGET_MAIN_BYTES = 5_000_000
FULL_PACK_MAX_ITEMS = 15_000

# Build traversal rules
POPULAR_PAGE_SIZE = 100
POPULAR_MAX_PAGES_SMALL = 300
POPULAR_MAX_PAGES_LARGE = 150

# These are NOT food keywords.
# They are only neutral traversal tokens to broaden search result coverage
# when the OFF endpoint requires a search term.
# This avoids English food bias like "milk", "bread", etc.
TRAVERSAL_TOKENS = list("abcdefghijklmnopqrstuvwxyz0123456789")

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

    match = re.search(r"(\d+(?:[.,]\d+)?)\s*([a-zA-Z]+)", raw.strip())
    if not match:
        return None, None

    size = match.group(1).replace(",", ".")
    unit = match.group(2).strip().lower()

    try:
        size_value = float(size)
    except ValueError:
        return None, None

    if unit in {"ml", "l", "cl", "dl", "liter", "litre"}:
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
    return brands.split(",")[0].strip() or None


def map_product(product):
    nutr = product.get("nutriments", {}) or {}

    kcal = float(nutr.get("energy-kcal_100g") or 0)
    protein = float(nutr.get("proteins_100g") or 0)
    carbs = float(nutr.get("carbohydrates_100g") or 0)
    fat = float(nutr.get("fat_100g") or 0)

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
        if quantity not in (None, ""):
            try:
                serving_size = float(quantity)
            except (TypeError, ValueError):
                serving_size = None

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
    }


def json_bytes(data):
    return len(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def save_json(path, payload):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


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


def fetch_products(country_slug, query, page, page_size=POPULAR_PAGE_SIZE):
    params = {
        "search_terms": query,
        "page": page,
        "page_size": page_size,
        "json": 1,
        "fields": FIELDS,
        "sort_by": "unique_scans_n",
        "search_simple": 1,
        "countries_tags_en": country_slug,
    }

    response = requests.get(BASE_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    payload = response.json()
    return payload.get("products", []) or []


def add_products(products, seen, items):
    added = 0

    for product in products:
        mapped = map_product(product)
        if not mapped:
            continue

        key = normalize_key(mapped)
        if key in seen:
            continue

        seen.add(key)
        items.append(mapped)
        added += 1

    return added


def collect_popularity_first(country_slug, max_pages):
    seen = set()
    items = []

    total_requests = 0
    successful_requests = 0
    failed_requests = 0

    # First pass: most likely/popular coverage using neutral broad token "a"
    primary_token = "a"

    for page in range(1, max_pages + 1):
        total_requests += 1
        try:
            products = fetch_products(country_slug, primary_token, page)
            successful_requests += 1
        except Exception as e:
            failed_requests += 1
            print(f"ERROR popularity pass token={primary_token} page={page}: {e}")
            break

        if not products:
            break

        added = add_products(products, seen, items)
        print(f"Popularity pass '{primary_token}' page {page} -> added {added}, total {len(items)}")
        time.sleep(0.35)

    # Second pass: broader neutral traversal, still popularity-sorted, still country-filtered.
    # No English food words.
    for token in TRAVERSAL_TOKENS:
        if token == primary_token:
            continue

        for page in range(1, max_pages + 1):
            total_requests += 1
            try:
                products = fetch_products(country_slug, token, page)
                successful_requests += 1
            except Exception as e:
                failed_requests += 1
                print(f"ERROR traversal token={token} page={page}: {e}")
                break

            if not products:
                break

            added = add_products(products, seen, items)
            print(f"Traversal '{token}' page {page} -> added {added}, total {len(items)}")

            time.sleep(0.35)

            # Stop once we are far enough past packaging budget.
            # We do not need endless discovery if the final pack will be byte-capped anyway.
            if json_bytes(items) > TARGET_TOTAL_BYTES * 2:
                return items, {
                    "totalRequests": total_requests,
                    "successfulRequests": successful_requests,
                    "failedRequests": failed_requests,
                    "traversalStoppedEarly": True,
                }

    return items, {
        "totalRequests": total_requests,
        "successfulRequests": successful_requests,
        "failedRequests": failed_requests,
        "traversalStoppedEarly": False,
    }


def build_country(country_iso2, slug):
    print(f"Building {country_iso2} ({slug})")

    # First, collect a broad popularity-first discovered pool.
    # We use a larger cap for countries that might still qualify as "full".
    discovered_items, request_meta = collect_popularity_first(
        country_slug=slug,
        max_pages=POPULAR_MAX_PAGES_SMALL
    )

    if request_meta["successfulRequests"] == 0:
        raise RuntimeError(f"No successful OFF requests for {country_iso2} ({slug})")

    discovered_count = len(discovered_items)
    discovered_size = json_bytes(discovered_items)

    # Decide whether the country appears small enough for a full-pack candidate.
    is_full_candidate = (
        discovered_count <= FULL_PACK_MAX_ITEMS
        and discovered_size <= TARGET_TOTAL_BYTES
    )

    # If it clearly is not a full-pack candidate, we do not need extreme traversal.
    # Rebuild a popularity-first pool with a lower page budget to keep the process practical.
    if not is_full_candidate:
        discovered_items, request_meta = collect_popularity_first(
            country_slug=slug,
            max_pages=POPULAR_MAX_PAGES_LARGE
        )
        discovered_count = len(discovered_items)
        discovered_size = json_bytes(discovered_items)

    build_meta = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "discoveryMethod": "popularity_first_country_search",
        "coverageNote": (
            "This build is popularity-first and country-filtered. "
            "It avoids language-specific food keywords, but still depends on OFF search traversal "
            "rather than a full bulk export, so full country coverage is not guaranteed."
        ),
        "popularPageSize": POPULAR_PAGE_SIZE,
        "fullPackMaxItems": FULL_PACK_MAX_ITEMS,
        "targetTotalBytes": TARGET_TOTAL_BYTES,
        "targetMainBytes": TARGET_MAIN_BYTES,
        "traversalTokenCount": len(TRAVERSAL_TOKENS),
        "totalRequests": request_meta["totalRequests"],
        "successfulRequests": request_meta["successfulRequests"],
        "failedRequests": request_meta["failedRequests"],
        "traversalStoppedEarly": request_meta["traversalStoppedEarly"],
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
