import csv
import json
import os
import re
from datetime import datetime, timezone


OUTPUT_ROOT = "countries"
SOURCE_ROOT = "national_sources"

UK_SOURCE_CSV = os.path.join(SOURCE_ROOT, "GB", "cofid.csv")
DE_SOURCE_CSV = os.path.join(SOURCE_ROOT, "DE", "bls.csv")


def normalize_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip())


def normalize_key(item):
    name = normalize_text(item.get("name")).lower()
    brand = normalize_text(item.get("brand")).lower()
    return f"{name}|{brand}"


def to_float(value):
    if value in (None, ""):
        return None

    text = str(value).strip().replace(",", ".")
    text = re.sub(r"[^\d.\-]", "", text)

    if not text:
        return None

    try:
        return float(text)
    except ValueError:
        return None


def first_existing(row, possible_names):
    lower_map = {
        normalize_text(k).lower(): v
        for k, v in row.items()
    }

    for name in possible_names:
        key = normalize_text(name).lower()
        if key in lower_map:
            return lower_map[key]

    return None


def write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_csv(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def save_national_pack(country_iso2, items, source_name):
    country_dir = os.path.join(OUTPUT_ROOT, country_iso2)
    os.makedirs(country_dir, exist_ok=True)

    output_path = os.path.join(country_dir, "national.json")

    deduped = []
    seen = set()

    for item in items:
        key = normalize_key(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    write_json(output_path, deduped)

    meta_path = os.path.join(country_dir, "national_manifest.json")
    write_json(meta_path, {
        "countryIso2": country_iso2,
        "source": source_name,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "itemCount": len(deduped),
        "file": f"countries/{country_iso2}/national.json",
    })

    print(f"Saved {country_iso2} national pack: {len(deduped)} items")


def map_uk_cofid_row(row):
    name = first_existing(row, [
        "Food Name",
        "Food name",
        "Food",
        "Name",
        "Description",
    ])

    if not name:
        return None

    calories = first_existing(row, [
        "Energy kcal",
        "Energy (kcal)",
        "Energy_kcal",
        "kcal",
    ])

    protein = first_existing(row, [
        "Protein (g)",
        "Protein",
        "Protein_g",
    ])

    carbs = first_existing(row, [
        "Carbohydrate (g)",
        "Carbohydrate",
        "Available carbohydrate (g)",
        "Carbs",
    ])

    fat = first_existing(row, [
        "Fat (g)",
        "Total fat (g)",
        "Fat",
    ])

    item = {
        "name": normalize_text(name),
        "brand": "CoFID",
        "barcode": None,
        "calories": to_float(calories) or 0.0,
        "protein": to_float(protein) or 0.0,
        "carbs": to_float(carbs) or 0.0,
        "fat": to_float(fat) or 0.0,
        "servingSize": 100.0,
        "servingUnit": "g",
        "isLiquid": False,
        "source": "uk_cofid",
    }

    if item["calories"] == 0.0 and item["protein"] == 0.0 and item["carbs"] == 0.0 and item["fat"] == 0.0:
        return None

    return item


def map_de_bls_row(row):
    name = first_existing(row, [
        "Name",
        "Food Name",
        "Lebensmittel",
        "Bezeichnung",
        "Description",
    ])

    if not name:
        return None

    calories = first_existing(row, [
        "Energy kcal",
        "Energy (kcal)",
        "Energie kcal",
        "kcal",
    ])

    protein = first_existing(row, [
        "Protein",
        "Protein (g)",
        "Eiweiß",
        "Eiweiss",
    ])

    carbs = first_existing(row, [
        "Carbohydrate",
        "Carbohydrate (g)",
        "Kohlenhydrate",
    ])

    fat = first_existing(row, [
        "Fat",
        "Fat (g)",
        "Fett",
    ])

    item = {
        "name": normalize_text(name),
        "brand": "BLS",
        "barcode": None,
        "calories": to_float(calories) or 0.0,
        "protein": to_float(protein) or 0.0,
        "carbs": to_float(carbs) or 0.0,
        "fat": to_float(fat) or 0.0,
        "servingSize": 100.0,
        "servingUnit": "g",
        "isLiquid": False,
        "source": "germany_bls",
    }

    if item["calories"] == 0.0 and item["protein"] == 0.0 and item["carbs"] == 0.0 and item["fat"] == 0.0:
        return None

    return item


def build_uk_cofid():
    if not os.path.exists(UK_SOURCE_CSV):
        print(f"Missing UK source CSV: {UK_SOURCE_CSV}")
        return

    rows = load_csv(UK_SOURCE_CSV)
    items = [map_uk_cofid_row(row) for row in rows]
    items = [item for item in items if item]

    save_national_pack("GB", items, "uk_cofid")


def build_germany_bls():
    if not os.path.exists(DE_SOURCE_CSV):
        print(f"Missing Germany source CSV: {DE_SOURCE_CSV}")
        return

    rows = load_csv(DE_SOURCE_CSV)
    items = [map_de_bls_row(row) for row in rows]
    items = [item for item in items if item]

    save_national_pack("DE", items, "germany_bls")


def main():
    build_uk_cofid()
    build_germany_bls()


if __name__ == "__main__":
    main()
