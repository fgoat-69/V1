import json
import os
import re
import time
from datetime import datetime, timezone

import requests

BASE_URL = "https://world.openfoodfacts.org/cgi/search.pl"
FIELDS = "product_name,brands,code,nutriments,serving_size,serving_quantity"

SEED_QUERIES = [
    "a", "e", "i", "o", "u",
    "milk", "bread", "rice", "water", "coffee",
    "juice", "tea", "cheese", "chicken", "pasta",
    "egg", "yogurt", "soda", "chocolate", "cookie"
]

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
        "servingSize": serving_size,
        "servingUnit": serving_unit,
        "isLiquid": is_liquid,
        "source": "github_country_pack",
    }


def fetch_products(country_slug, query, page, page_size=100):
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

    response = requests.get(BASE_URL, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()
    return payload.get("products", []) or []


def build_country(country_iso2, slug, max_items=25000, max_pages_per_query=3):
    print(f"Building {country_iso2} ({slug})")

    seen = set()
    items = []

    total_requests = 0
    successful_requests = 0
    failed_requests = 0

    for query in SEED_QUERIES:
        for page in range(1, max_pages_per_query + 1):
            if len(items) >= max_items:
                break

            total_requests += 1

            try:
                products = fetch_products(slug, query, page)
                successful_requests += 1
            except Exception as e:
                failed_requests += 1
                print(f"ERROR query={query} page={page}: {e}")
                break

            if not products:
                break

            added_this_page = 0

            for product in products:
                mapped = map_product(product)
                if not mapped:
                    continue

                key = normalize_key(mapped)
                if key in seen:
                    continue

                seen.add(key)
                items.append(mapped)
                added_this_page += 1

                if len(items) >= max_items:
                    break

            print(
                f"Query '{query}' page {page} -> added {added_this_page}, total {len(items)}"
            )

            time.sleep(0.35)

        if len(items) >= max_items:
            break

    if successful_requests == 0:
        raise RuntimeError(f"No successful OFF requests for {country_iso2} ({slug})")

    build_meta = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "seedQueryCount": len(SEED_QUERIES),
        "maxPagesPerQuery": max_pages_per_query,
        "maxItems": max_items,
        "totalRequests": total_requests,
        "successfulRequests": successful_requests,
        "failedRequests": failed_requests,
    }

    return items, build_meta


def save_country(country_iso2, slug, items, build_meta):
    path = os.path.join("countries", country_iso2)
    os.makedirs(path, exist_ok=True)

    pack_filename = "full.json"
    pack_relative_path = f"countries/{country_iso2}/{pack_filename}"
    pack_path = os.path.join(path, pack_filename)

    with open(pack_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    manifest = {
        "countryIso2": country_iso2,
        "slug": slug,
        "version": int(time.time()),
        "generatedAt": build_meta["generatedAt"],
        "strategy": "seeded_fullish",
        "itemCount": len(items),
        "packFiles": [
            {
                "name": pack_filename,
                "path": pack_relative_path,
                "kind": "full",
                "itemCount": len(items),
            }
        ],
        "buildMeta": build_meta,
    }

    manifest_path = os.path.join(path, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"Saved {country_iso2}: {len(items)} items")
    return manifest


if __name__ == "__main__":
    built_items, built_meta = build_country("HU", "hungary")
    save_country("HU", "hungary", built_items, built_meta)
