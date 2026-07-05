import json
import os
import re
import tempfile
from datetime import datetime, timezone
from urllib.parse import quote
from urllib.request import Request, urlopen

from openpyxl import load_workbook


OUTPUT_ROOT = "countries"

DE_BLS_SOURCE = "national_sources/DE/BLS_4_0_Daten_2025_DE.xlsx"

CIQUAL_DATASET_DOI = "doi:10.57745/RDMHWY"
CIQUAL_API_BASE = "https://entrepot.recherche.data.gouv.fr/api"
USER_AGENT = "MostoFitNationalPackBuilder/1.0"


def normalize_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip())


def normalize_key(item):
    return normalize_text(item.get("name")).lower()


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


def fetch_json(url):
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def download_file(url, output_path):
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=180) as response:
        with open(output_path, "wb") as f:
            f.write(response.read())


def find_latest_ciqual_xlsx_file():
    encoded_doi = quote(CIQUAL_DATASET_DOI, safe=":")
    url = (
        f"{CIQUAL_API_BASE}/datasets/export"
        f"?exporter=dataverse_json&persistentId={encoded_doi}"
    )

    payload = fetch_json(url)
    files = payload.get("datasetVersion", {}).get("files", [])

    xlsx_files = []

    for file_entry in files:
        data_file = file_entry.get("dataFile", {})
        filename = data_file.get("filename", "")
        persistent_id = data_file.get("persistentId", "")

        if filename.lower().endswith(".xlsx") and persistent_id:
            xlsx_files.append({
                "filename": filename,
                "persistentId": persistent_id,
            })

    if not xlsx_files:
        raise RuntimeError("Could not find CIQUAL XLSX file in dataset metadata.")

    xlsx_files.sort(key=lambda item: item["filename"], reverse=True)
    return xlsx_files[0]


def download_latest_ciqual_xlsx():
    latest = find_latest_ciqual_xlsx_file()

    temp_dir = tempfile.mkdtemp(prefix="ciqual_")
    output_path = os.path.join(temp_dir, latest["filename"])

    encoded_file_doi = quote(latest["persistentId"], safe=":")
    download_url = (
        f"{CIQUAL_API_BASE}/access/datafile/:persistentId"
        f"?persistentId={encoded_file_doi}"
    )

    print(f"Downloading CIQUAL file: {latest['filename']}")
    download_file(download_url, output_path)

    return output_path, latest


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


def build_france_ciqual():
    ciqual_path, ciqual_file = download_latest_ciqual_xlsx()

    workbook = load_workbook(ciqual_path, read_only=True, data_only=True)
    sheet = workbook.active

    rows = sheet.iter_rows(values_only=True)
    headers = list(next(rows))

    normalized_headers = {
        normalize_text(header).lower(): header
        for header in headers
    }

    def header_contains(*tokens):
        for header in headers:
            text = normalize_text(header).lower()
            if all(token.lower() in text for token in tokens):
                return header
        return None

    name_header = (
        header_contains("alim", "nom", "fr")
        or header_contains("nom", "fr")
        or header_contains("aliment")
    )

    kcal_header = header_contains("energie", "kcal")
        protein_header = (
        header_contains("proteines")
        or header_contains("protéines")
        or header_contains("prot")
    )
    fat_header = header_contains("lipides")
    carbs_header = header_contains("glucides")

    if not name_header or not kcal_header or not protein_header or not fat_header or not carbs_header:
        raise RuntimeError(
            "Could not find required CIQUAL columns. "
            f"name={name_header}, kcal={kcal_header}, protein={protein_header}, "
            f"fat={fat_header}, carbs={carbs_header}"
        )

    index = {header: i for i, header in enumerate(headers)}

    items = []
    seen = set()

    for row in rows:
        name = normalize_text(row[index[name_header]])

        if not name:
            continue

        calories = to_float(row[index[kcal_header]]) or 0.0
        protein = to_float(row[index[protein_header]]) or 0.0
        fat = to_float(row[index[fat_header]]) or 0.0
        carbs = to_float(row[index[carbs_header]]) or 0.0

        if calories == 0.0 and protein == 0.0 and carbs == 0.0 and fat == 0.0:
            continue

        item = {
            "name": name,
            "brand": "CIQUAL 2025",
            "barcode": None,
            "calories": round(calories, 2),
            "protein": round(protein, 2),
            "carbs": round(carbs, 2),
            "fat": round(fat, 2),
            "servingSize": 100.0,
            "servingUnit": "g",
            "isLiquid": False,
            "source": "france_ciqual",
        }

        key = normalize_key(item)
        if key in seen:
            continue

        seen.add(key)
        items.append(item)

    items.sort(key=lambda item: item["name"].lower())

    output_path = os.path.join(OUTPUT_ROOT, "FR", "national.json")
    manifest_path = os.path.join(OUTPUT_ROOT, "FR", "national_manifest.json")

    write_json(output_path, items)

    write_json(manifest_path, {
        "countryIso2": "FR",
        "source": "france_ciqual",
        "sourceName": "Table de composition nutritionnelle des aliments Ciqual",
        "owner": "ANSES",
        "license": "Etalab Open License 2.0",
        "datasetPersistentId": CIQUAL_DATASET_DOI,
        "filePersistentId": ciqual_file["persistentId"],
        "sourceFileName": ciqual_file["filename"],
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "itemCount": len(items),
        "file": "countries/FR/national.json",
    })

    print(f"Saved France CIQUAL national pack: {len(items)} items")


def main():
    build_germany_bls()
    build_france_ciqual()


if __name__ == "__main__":
    main()
