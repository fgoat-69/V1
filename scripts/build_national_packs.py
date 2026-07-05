import json
import os
import re
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
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


def normalize_for_match(value):
    text = normalize_text(value).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return text


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


def get_ciqual_dataset_files():
    encoded_doi = quote(CIQUAL_DATASET_DOI, safe=":")
    url = (
        f"{CIQUAL_API_BASE}/datasets/export"
        f"?exporter=dataverse_json&persistentId={encoded_doi}"
    )

    payload = fetch_json(url)
    return payload.get("datasetVersion", {}).get("files", [])


def find_ciqual_file(files, starts_with, ends_with=".xml"):
    matches = []

    for file_entry in files:
        data_file = file_entry.get("dataFile", {})
        filename = data_file.get("filename", "")
        persistent_id = data_file.get("persistentId", "")

        filename_l = filename.lower()

        if filename_l.startswith(starts_with) and filename_l.endswith(ends_with) and persistent_id:
            matches.append({
                "filename": filename,
                "persistentId": persistent_id,
            })

    if not matches:
        available = [
            file_entry.get("dataFile", {}).get("filename", "")
            for file_entry in files
        ]
        raise RuntimeError(
            f"Could not find CIQUAL file starting with '{starts_with}'. "
            f"Available files: {available}"
        )

    matches.sort(key=lambda item: item["filename"], reverse=True)
    return matches[0]


def download_ciqual_xml_files():
    files = get_ciqual_dataset_files()
    temp_dir = tempfile.mkdtemp(prefix="ciqual_")

    wanted = {
        "alim": find_ciqual_file(files, "alim_"),
        "const": find_ciqual_file(files, "const_"),
        "compo": find_ciqual_file(files, "compo_"),
    }

    downloaded = {}

    for key, file_info in wanted.items():
        encoded_file_doi = quote(file_info["persistentId"], safe=":")
        download_url = (
            f"{CIQUAL_API_BASE}/access/datafile/:persistentId"
            f"?persistentId={encoded_file_doi}"
        )

        output_path = os.path.join(temp_dir, file_info["filename"])

        print(f"Downloading CIQUAL {key} file: {file_info['filename']}")
        download_file(download_url, output_path)

        downloaded[key] = {
            "path": output_path,
            "filename": file_info["filename"],
            "persistentId": file_info["persistentId"],
        }

    return downloaded


def xml_text(parent, tag_name):
    child = parent.find(tag_name)
    if child is None or child.text is None:
        return ""
    return normalize_text(child.text)


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


def parse_ciqual_alim(path):
    foods = {}

    root = ET.parse(path).getroot()

    for alim in root.findall("ALIM"):
        code = xml_text(alim, "alim_code")
        name_fr = xml_text(alim, "alim_nom_fr")
        name_en = xml_text(alim, "alim_nom_eng")

        if not code or not name_fr:
            continue

        final_name = name_fr
        if name_en and name_en.lower() != name_fr.lower():
            final_name = f"{name_fr} / {name_en}"

        foods[code] = final_name

    return foods


def parse_ciqual_const(path):
    nutrients = {}

    root = ET.parse(path).getroot()

    for const in root.findall("CONST"):
        code = xml_text(const, "const_code")
        name_fr = xml_text(const, "const_nom_fr")
        name_en = xml_text(const, "const_nom_eng")
        infoods = xml_text(const, "code_INFOODS")

        if code:
            nutrients[code] = {
                "name_fr": name_fr,
                "name_en": name_en,
                "infoods": infoods,
            }

    return nutrients


def identify_ciqual_macro_codes(nutrients):
    kcal_code = None
    protein_code = None
    fat_code = None
    carbs_code = None

    for code, meta in nutrients.items():
        infoods = normalize_for_match(meta.get("infoods", ""))
        name = normalize_for_match(
            " ".join([
                meta.get("name_fr", ""),
                meta.get("name_en", ""),
                meta.get("infoods", ""),
            ])
        )

        if not kcal_code and "kcal" in name:
            kcal_code = code

        if not protein_code and (
            "proteines" in name or "protein" in name or infoods == "prot"
        ):
            protein_code = code

        if not fat_code and (
            "lipides" in name or "fat" in name or infoods == "fat"
        ):
            fat_code = code

        if not carbs_code and (
            "glucides" in name
            or "carbohydrate" in name
            or infoods in {"choavl", "chocdf"}
        ):
            carbs_code = code

    if not kcal_code or not protein_code or not fat_code or not carbs_code:
        raise RuntimeError(
            "Could not identify CIQUAL macro codes. "
            f"kcal={kcal_code}, protein={protein_code}, fat={fat_code}, carbs={carbs_code}"
        )

    print(
        "CIQUAL macro codes: "
        f"kcal={kcal_code}, protein={protein_code}, fat={fat_code}, carbs={carbs_code}"
    )

    return {
        "calories": kcal_code,
        "protein": protein_code,
        "fat": fat_code,
        "carbs": carbs_code,
    }


def parse_ciqual_compo(path, macro_codes):
    wanted_codes = set(macro_codes.values())
    reverse_codes = {value: key for key, value in macro_codes.items()}

    values_by_food = {}

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    tokens = text.split()

    if len(tokens) % 5 != 0:
        print(f"Warning: CIQUAL composition token count is not divisible by 5: {len(tokens)}")

    for i in range(0, len(tokens) - 4, 5):
        food_code = tokens[i]
        nutrient_code = tokens[i + 1]
        raw_value = tokens[i + 2]

        if nutrient_code not in wanted_codes:
            continue

        value = to_float(raw_value)
        if value is None:
            continue

        field = reverse_codes[nutrient_code]
        values_by_food.setdefault(food_code, {})[field] = value

    return values_by_food


def build_france_ciqual():
    ciqual_files = download_ciqual_xml_files()

    foods = parse_ciqual_alim(ciqual_files["alim"]["path"])
    nutrients = parse_ciqual_const(ciqual_files["const"]["path"])
    macro_codes = identify_ciqual_macro_codes(nutrients)
    values_by_food = parse_ciqual_compo(ciqual_files["compo"]["path"], macro_codes)

    items = []
    seen = set()

    for food_code, name in foods.items():
        values = values_by_food.get(food_code, {})

        calories = values.get("calories", 0.0)
        protein = values.get("protein", 0.0)
        fat = values.get("fat", 0.0)
        carbs = values.get("carbs", 0.0)

        if calories == 0.0 and protein == 0.0 and carbs == 0.0 and fat == 0.0:
            continue

        item = {
            "name": name,
            "brand": "CIQUAL",
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
        "sourceFiles": {
            "alim": {
                "filename": ciqual_files["alim"]["filename"],
                "persistentId": ciqual_files["alim"]["persistentId"],
            },
            "const": {
                "filename": ciqual_files["const"]["filename"],
                "persistentId": ciqual_files["const"]["persistentId"],
            },
            "compo": {
                "filename": ciqual_files["compo"]["filename"],
                "persistentId": ciqual_files["compo"]["persistentId"],
            },
        },
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
