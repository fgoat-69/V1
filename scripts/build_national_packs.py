import json
import os
import re
from datetime import datetime, timezone

from openpyxl import load_workbook


OUTPUT_ROOT = "countries"

DE_BLS_SOURCE = "national_sources/DE/BLS_4_0_Daten_2025_DE.xlsx"


def normalize_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip())


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


def normalize_key(item):
    return normalize_text(item.get("name")).lower()


def write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def find_header(headers, starts_with):
    for header in headers:
        text = normalize_text(header)
        if text.startswith(starts_with):
            return header
    return None


def build_germany_bls():
    if not os.path.exists(DE_BLS_SOURCE):
        raise FileNotFoundError(f"Missing BLS source file: {DE_BLS_SOURCE}")

    workbook = load_workbook(DE_BLS_SOURCE, read_only=True, data_only=True)
    sheet = workbook.active

    rows = sheet.iter_rows(values_only=True)
    headers = list(next(rows))
    header_set = set(headers)

    required_headers = {
        "BLS Code",
        "Lebensmittelbezeichnung",
        "Food name",
    }

    missing = required_headers - header_set
    if missing:
        raise RuntimeError(f"Missing required BLS headers: {missing}")

    kcal_header = find_header(headers, "ENERCC Energie (Kilokalorien)")
    protein_header = find_header(headers, "PROT625 Protein")
    fat_header = find_header(headers, "FAT Fett")
    carbs_header = find_header(headers, "CHO Kohlenhydrate, verfügbar")

    if not kcal_header or not protein_header or not fat_header or not carbs_header:
        raise RuntimeError(
            "Could not find required nutrient columns. "
            f"kcal={kcal_header}, protein={protein_header}, fat={fat_header}, carbs={carbs_header}"
        )

    index = {header: i for i, header in enumerate(headers)}

    items = []
    seen = set()

    for row in rows:
        code = row[index["BLS Code"]]
        name_de = row[index["Lebensmittelbezeichnung"]]
        name_en = row[index["Food name"]]

        if not code or not name_de:
            continue

        calories = to_float(row[index[kcal_header]]) or 0.0
        protein = to_float(row[index[protein_header]]) or 0.0
        fat = to_float(row[index[fat_header]]) or 0.0
        carbs = to_float(row[index[carbs_header]]) or 0.0

        if calories == 0.0 and protein == 0.0 and fat == 0.0 and carbs == 0.0:
            continue

        name = normalize_text(name_de)
        english_name = normalize_text(name_en)

        final_name = name
        if english_name and english_name.lower() != name.lower():
            final_name = f"{name} / {english_name}"

        item = {
            "name": final_name,
            "brand": "BLS 4.0",
            "barcode": None,
            "calories": round(calories, 2),
            "protein": round(protein, 2),
            "carbs": round(carbs, 2),
            "fat": round(fat, 2),
            "servingSize": 100.0,
            "servingUnit": "g",
            "isLiquid": False,
            "source": "germany_bls",
        }

        key = normalize_key(item)
        if key in seen:
            continue

        seen.add(key)
        items.append(item)

    items.sort(key=lambda item: item["name"].lower())

    output_path = os.path.join(OUTPUT_ROOT, "DE", "national.json")
    manifest_path = os.path.join(OUTPUT_ROOT, "DE", "national_manifest.json")

    write_json(output_path, items)

    write_json(manifest_path, {
        "countryIso2": "DE",
        "source": "germany_bls",
        "sourceName": "Bundeslebensmittelschlüssel BLS Version 4.0",
        "owner": "Max Rubner-Institut",
        "license": "CC BY 4.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "itemCount": len(items),
        "file": "countries/DE/national.json",
    })

    print(f"Saved Germany BLS national pack: {len(items)} items")


def main():
    build_germany_bls()


if __name__ == "__main__":
    main()
