import requests
import json
import time
import os

BASE_URL = "https://world.openfoodfacts.org/cgi/search.pl"
FIELDS = "product_name,brands,code,nutriments,serving_size"

SEED_QUERIES = [
    "a", "e", "i", "o", "u",
    "milk", "bread", "rice", "water", "coffee",
    "juice", "tea", "cheese", "chicken", "pasta",
    "egg", "yogurt", "soda", "chocolate", "cookie"
]


def normalize_key(item):
    barcode = item.get("barcode")
    if barcode:
        return f"bc:{barcode}"

    name = (item.get("name") or "").strip().lower()
    brand = (item.get("brand") or "").strip().lower()
    return f"nb:{name}|{brand}"


def map_product(p):
    nutr = p.get("nutriments", {}) or {}

    kcal = nutr.get("energy-kcal_100g", 0) or 0
    protein = nutr.get("proteins_100g", 0) or 0
    carbs = nutr.get("carbohydrates_100g", 0) or 0
    fat = nutr.get("fat_100g", 0) or 0

    if kcal == 0 and protein == 0 and carbs == 0 and fat == 0:
        return None

    name = p.get("product_name")
    if not name:
        return None

    return {
        "name": name,
        "brand": p.get("brands"),
        "barcode": p.get("code"),
        "calories": kcal,
        "protein": protein,
        "carbs": carbs,
        "fat": fat,
        "servingSize": None,
        "servingUnit": None,
        "isLiquid": False,
        "source": "off_country_pack"
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
        "countries_tags_en": country_slug
    }

    r = requests.get(BASE_URL, params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("products", [])


def build_country(country_iso2, slug, max_items=25000, max_pages_per_query=3):
    print(f"Building {country_iso2} ({slug})")

    seen = set()
    items = []

    successful_requests = 0

    for query in SEED_QUERIES:
        for page in range(1, max_pages_per_query + 1):
            if len(items) >= max_items:
                break

            try:
                products = fetch_products(slug, query, page)
                successful_requests += 1
            except Exception as e:
                print(f"ERROR query={query} page={page}: {e}")
                break

            if not products:
                break

            for p in products:
                mapped = map_product(p)
                if not mapped:
                    continue

                key = normalize_key(mapped)
                if key in seen:
                    continue

                seen.add(key)
                items.append(mapped)

                if len(items) >= max_items:
                    break

            print(f"Query '{query}' page {page} -> total {len(items)}")
            time.sleep(0.35)

        if len(items) >= max_items:
            break

    if successful_requests == 0:
        raise RuntimeError(f"No successful OFF requests for {country_iso2} ({slug})")

    return items


def save_country(country_iso2, slug, items):
    path = os.path.join("countries", country_iso2)
    os.makedirs(path, exist_ok=True)

    file_path = os.path.join(path, "full.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False)

    manifest = {
        "countryIso2": country_iso2,
        "slug": slug,
        "version": int(time.time()),
        "strategy": "full" if len(items) < 20000 else "tiered_fill",
        "itemCount": len(items)
    }

    with open(os.path.join(path, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False)

    print(f"Saved {country_iso2}: {len(items)} items")
    return manifest


if __name__ == "__main__":
    items = build_country("HU", "hungary")
    save_country("HU", "hungary", items)
