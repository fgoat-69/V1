import json
import os
import traceback
from datetime import datetime, timezone

from build_country_pack import (
    DUMP_URL,
    FULL_PACK_MAX_ITEMS,
    TARGET_MAIN_BYTES,
    TARGET_TOTAL_BYTES,
    ensure_dump,
    iter_dump_products,
    json_bytes,
    map_product,
    normalize_key,
    product_country_tokens,
    save_country,
    sort_discovered_items,
    strip_internal_fields,
)

COUNTRIES = [
    ("AL", "albania"),
    ("DZ", "algeria"),
    ("AO", "angola"),
    ("AG", "antigua-and-barbuda"),
    ("AR", "argentina"),
    ("AM", "armenia"),
    ("AW", "aruba"),
    ("AU", "australia"),
    ("AT", "austria"),
    ("AZ", "azerbaijan"),
    ("BS", "bahamas"),
    ("BH", "bahrain"),
    ("BD", "bangladesh"),
    ("BY", "belarus"),
    ("BE", "belgium"),
    ("BZ", "belize"),
    ("BJ", "benin"),
    ("BO", "bolivia"),
    ("BA", "bosnia-and-herzegovina"),
    ("BW", "botswana"),
    ("BR", "brazil"),
    ("VG", "british-virgin-islands"),
    ("BG", "bulgaria"),
    ("BF", "burkina-faso"),
    ("KH", "cambodia"),
    ("CM", "cameroon"),
    ("CA", "canada"),
    ("CV", "cape-verde"),
    ("KY", "cayman-islands"),
    ("TD", "chad"),
    ("CL", "chile"),
    ("CN", "china"),
    ("CO", "colombia"),
    ("KM", "comoros"),
    ("CG", "republic-of-the-congo"),
    ("CD", "democratic-republic-of-the-congo"),
    ("CR", "costa-rica"),
    ("HR", "croatia"),
    ("CU", "cuba"),
    ("CY", "cyprus"),
    ("CZ", "czech-republic"),
    ("DK", "denmark"),
    ("DJ", "djibouti"),
    ("DM", "dominica"),
    ("DO", "dominican-republic"),
    ("EC", "ecuador"),
    ("EG", "egypt"),
    ("SV", "el-salvador"),
    ("ER", "eritrea"),
    ("EE", "estonia"),
    ("FJ", "fiji"),
    ("FI", "finland"),
    ("FR", "france"),
    ("GA", "gabon"),
    ("GM", "gambia"),
    ("GE", "georgia"),
    ("DE", "germany"),
    ("GH", "ghana"),
    ("GI", "gibraltar"),
    ("GR", "greece"),
    ("GD", "grenada"),
    ("GT", "guatemala"),
    ("GN", "guinea"),
    ("GW", "guinea-bissau"),
    ("HT", "haiti"),
    ("HN", "honduras"),
    ("HK", "hong-kong"),
    ("HU", "hungary"),
    ("IS", "iceland"),
    ("IN", "india"),
    ("ID", "indonesia"),
    ("IQ", "iraq"),
    ("IE", "ireland"),
    ("IL", "israel"),
    ("IT", "italy"),
    ("JM", "jamaica"),
    ("JP", "japan"),
    ("JO", "jordan"),
    ("KZ", "kazakhstan"),
    ("KE", "kenya"),
    ("KW", "kuwait"),
    ("KG", "kyrgyzstan"),
    ("LA", "laos"),
    ("LV", "latvia"),
    ("LB", "lebanon"),
    ("LS", "lesotho"),
    ("LR", "liberia"),
    ("LY", "libya"),
    ("LI", "liechtenstein"),
    ("LT", "lithuania"),
    ("LU", "luxembourg"),
    ("MO", "macao"),
    ("MK", "north-macedonia"),
    ("MG", "madagascar"),
    ("MW", "malawi"),
    ("MY", "malaysia"),
    ("MV", "maldives"),
    ("ML", "mali"),
    ("MT", "malta"),
    ("MH", "marshall-islands"),
    ("MR", "mauritania"),
    ("MU", "mauritius"),
    ("MX", "mexico"),
    ("FM", "micronesia"),
    ("MD", "moldova"),
    ("MN", "mongolia"),
    ("ME", "montenegro"),
    ("MA", "morocco"),
    ("MZ", "mozambique"),
    ("MM", "myanmar"),
    ("NA", "namibia"),
    ("NP", "nepal"),
    ("NL", "netherlands"),
    ("NZ", "new-zealand"),
    ("NI", "nicaragua"),
    ("NE", "niger"),
    ("NG", "nigeria"),
    ("NO", "norway"),
    ("OM", "oman"),
    ("PK", "pakistan"),
    ("PA", "panama"),
    ("PG", "papua-new-guinea"),
    ("PY", "paraguay"),
    ("PE", "peru"),
    ("PH", "philippines"),
    ("PL", "poland"),
    ("PT", "portugal"),
    ("QA", "qatar"),
    ("RO", "romania"),
    ("RU", "russia"),
    ("RW", "rwanda"),
    ("WS", "samoa"),
    ("SM", "san-marino"),
    ("SA", "saudi-arabia"),
    ("SN", "senegal"),
    ("RS", "serbia"),
    ("SC", "seychelles"),
    ("SL", "sierra-leone"),
    ("SG", "singapore"),
    ("SK", "slovakia"),
    ("SI", "slovenia"),
    ("SB", "solomon-islands"),
    ("SO", "somalia"),
    ("ZA", "south-africa"),
    ("KR", "south-korea"),
    ("ES", "spain"),
    ("LK", "sri-lanka"),
    ("KN", "saint-kitts-and-nevis"),
    ("LC", "saint-lucia"),
    ("SD", "sudan"),
    ("SR", "suriname"),
    ("SE", "sweden"),
    ("CH", "switzerland"),
    ("SY", "syria"),
    ("TW", "taiwan"),
    ("TJ", "tajikistan"),
    ("TZ", "tanzania"),
    ("TH", "thailand"),
    ("TG", "togo"),
    ("TO", "tonga"),
    ("TT", "trinidad-and-tobago"),
    ("TN", "tunisia"),
    ("TR", "turkey"),
    ("TM", "turkmenistan"),
    ("TC", "turks-and-caicos-islands"),
    ("UG", "uganda"),
    ("UA", "ukraine"),
    ("AE", "united-arab-emirates"),
    ("GB", "united-kingdom"),
    ("US", "united-states"),
    ("UY", "uruguay"),
    ("UZ", "uzbekistan"),
    ("VU", "vanuatu"),
    ("VA", "vatican-city"),
    ("VE", "venezuela"),
    ("VN", "vietnam"),
    ("YE", "yemen"),
    ("ZM", "zambia"),
    ("ZW", "zimbabwe"),
]

COUNTRY_MAP = {iso2: slug for iso2, slug in COUNTRIES}

COUNTRY_BATCHES = {
    "batch_01_europe_north_west": [
        "GB", "IE", "IS", "NO", "SE", "FI", "DK", "NL", "BE", "LU"
    ],
    "batch_02_europe_central": [
        "DE", "AT", "CH", "LI", "CZ", "PL", "SK", "HU"
    ],
    "batch_03_europe_south_west": [
        "FR", "ES", "PT", "IT", "SM", "VA", "MT"
    ],
    "batch_04_europe_south_east": [
        "RO", "BG", "GR", "HR", "SI", "RS", "BA", "ME", "MK", "AL", "CY"
    ],
    "batch_05_europe_east_caucasus": [
        "UA", "BY", "MD", "LT", "LV", "EE", "GE", "AM", "AZ", "RU"
    ],
    "batch_06_middle_east": [
        "TR", "IL", "JO", "LB", "SY", "IQ", "SA", "AE", "QA", "KW", "OM", "BH", "YE"
    ],
    "batch_07_central_south_asia": [
        "IN", "PK", "BD", "LK", "NP", "KZ", "KG", "TJ", "TM", "UZ"
    ],
    "batch_08_east_south_east_asia": [
        "CN", "JP", "KR", "TW", "HK", "MO", "TH", "VN", "MY", "SG", "ID", "PH", "KH", "LA", "MM"
    ],
    "batch_09_africa_north_west": [
        "DZ", "EG", "MA", "TN", "LY", "SD", "MR", "ML", "NE", "TD"
    ],
    "batch_10_africa_west": [
        "NG", "GH", "SN", "GM", "GN", "GW", "SL", "LR", "TG", "BJ", "BF", "CV"
    ],
    "batch_11_africa_central_east": [
        "CM", "GA", "CG", "CD", "DJ", "ER", "SO", "KE", "UG", "RW", "TZ"
    ],
    "batch_12_africa_south_indian_ocean": [
        "AO", "ZA", "BW", "NA", "LS", "MZ", "MW", "ZM", "ZW", "MG", "MU", "SC"
    ],
    "batch_13_north_america": [
        "US", "CA", "MX"
    ],
    "batch_14_central_america_caribbean": [
        "AG", "BS", "BZ", "CR", "CU", "DM", "DO", "GD", "GT", "HN", "HT",
        "JM", "KN", "KY", "LC", "NI", "PA", "SV", "TC", "TT", "VG"
    ],
    "batch_15_south_america": [
        "AR", "BO", "BR", "CL", "CO", "EC", "PE", "PY", "UY", "VE", "SR"
    ],
    "batch_16_oceania_pacific": [
        "AU", "NZ", "FJ", "PG", "SB", "TO", "VU", "WS", "MH", "FM"
    ],
    "batch_17_misc_small_states": [
        "AW", "GI", "KM", "MV", "MN"
    ],
}

COUNTRY_FILTER = {
    token.strip().upper()
    for token in os.getenv("COUNTRY_FILTER", "").split(",")
    if token.strip()
}

BATCH_NAME = os.getenv("COUNTRY_BATCH", "").strip()
FORCE_DOWNLOAD = os.getenv("FORCE_DOWNLOAD", "").strip().lower() in {"1", "true", "yes"}
SKIP_EXISTING = os.getenv("SKIP_EXISTING", "").strip().lower() in {"1", "true", "yes"}


def ensure_output_root():
    os.makedirs("countries", exist_ok=True)


def selected_countries():
    if COUNTRY_FILTER:
        return [
            (iso2, slug)
            for (iso2, slug) in COUNTRIES
            if iso2.upper() in COUNTRY_FILTER
        ]

    if BATCH_NAME:
        if BATCH_NAME not in COUNTRY_BATCHES:
            raise RuntimeError(
                f"Unknown COUNTRY_BATCH '{BATCH_NAME}'. "
                f"Known batches: {', '.join(sorted(COUNTRY_BATCHES.keys()))}"
            )

        batch_iso2s = COUNTRY_BATCHES[BATCH_NAME]
        missing = [iso2 for iso2 in batch_iso2s if iso2 not in COUNTRY_MAP]
        if missing:
            raise RuntimeError(
                f"Batch '{BATCH_NAME}' references unknown country codes: {', '.join(missing)}"
            )

        return [(iso2, COUNTRY_MAP[iso2]) for iso2 in batch_iso2s]

    return COUNTRIES


def manifest_path_for(iso2):
    return os.path.join("countries", iso2, "manifest.json")


def should_skip_existing(iso2):
    return SKIP_EXISTING and os.path.exists(manifest_path_for(iso2))


def write_index(manifests):
    ensure_output_root()

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "countryCount": len(manifests),
        "countries": sorted(manifests, key=lambda x: x["countryIso2"]),
    }

    with open("countries/index.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def write_failures(failures):
    ensure_output_root()

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "failureCount": len(failures),
        "failures": failures,
    }

    with open("countries/failures.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_existing_manifest(iso2):
    path = manifest_path_for(iso2)
    if not os.path.exists(path):
        return None

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_existing_index_manifests():
    path = os.path.join("countries", "index.json")
    if not os.path.exists(path):
        return {}

    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    return {
        manifest["countryIso2"]: manifest
        for manifest in payload.get("countries", [])
        if manifest.get("countryIso2")
    }


def load_existing_failures():
    path = os.path.join("countries", "failures.json")
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    return payload.get("failures", [])


def init_country_state(iso2, slug):
    return {
        "countryIso2": iso2,
        "slug": slug,
        "seen": set(),
        "items": [],
        "matchedProducts": 0,
        "mappedProducts": 0,
        "dedupedProducts": 0,
        "skippedNoNutrition": 0,
    }


def build_token_to_iso_map(countries_to_build):
    token_to_iso = {}

    for iso2, slug in countries_to_build:
        token_to_iso[iso2.lower()] = iso2
        token_to_iso[slug.lower()] = iso2

    return token_to_iso


def matched_country_isos(product, token_to_iso):
    tokens = product_country_tokens(product)
    return {token_to_iso[token] for token in tokens if token in token_to_iso}


def single_pass_collect(countries_to_build):
    dump_path = ensure_dump(
        download_if_missing=True,
        force_download=FORCE_DOWNLOAD,
    )

    token_to_iso = build_token_to_iso_map(countries_to_build)
    states = {
        iso2: init_country_state(iso2, slug)
        for iso2, slug in countries_to_build
    }

    scanned_products = 0

    for _, product in iter_dump_products(dump_path):
        scanned_products += 1

        matched_isos = matched_country_isos(product, token_to_iso)
        if not matched_isos:
            continue

        mapped = map_product(product)

        for iso2 in matched_isos:
            states[iso2]["matchedProducts"] += 1

        if not mapped:
            for iso2 in matched_isos:
                states[iso2]["skippedNoNutrition"] += 1
            continue

        key = normalize_key(mapped)
        if not key:
            continue

        for iso2 in matched_isos:
            state = states[iso2]
            state["mappedProducts"] += 1

            if key in state["seen"]:
                state["dedupedProducts"] += 1
                continue

            state["seen"].add(key)
            state["items"].append(dict(mapped))

    return dump_path, scanned_products, states


def build_meta_for_country(dump_path, scanned_products, state):
    sorted_items = sort_discovered_items(state["items"])
    discovered_items = strip_internal_fields(sorted_items)

    return discovered_items, {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "discoveryMethod": "off_jsonl_dump_single_pass_country_filter",
        "coverageNote": (
            "This build is generated from a single pass over the OFF JSONL dump with "
            "country filtering, app-field reduction, nutrition filtering, and per-country "
            "deduplication. Products with completely empty calories/protein/carbs/fat are "
            "skipped unless they appear to be plain water. Large countries are popularity-sorted "
            "using OFF popularity fields when available before budget-based packaging."
        ),
        "dumpUrl": DUMP_URL,
        "dumpCachePath": dump_path,
        "fullPackMaxItems": FULL_PACK_MAX_ITEMS,
        "targetTotalBytes": TARGET_TOTAL_BYTES,
        "targetMainBytes": TARGET_MAIN_BYTES,
        "scannedProducts": scanned_products,
        "matchedProducts": state["matchedProducts"],
        "mappedProducts": state["mappedProducts"],
        "dedupedProducts": state["dedupedProducts"],
        "skippedNoNutrition": state.get("skippedNoNutrition", 0),
        "discoveredItemCount": len(discovered_items),
        "discoveredBytes": json_bytes(discovered_items),
    }


def main():
    ensure_output_root()

    existing_manifest_map = load_existing_index_manifests()
    existing_failures = load_existing_failures()

    manifests_by_iso = dict(existing_manifest_map)
    failures_by_iso = {
        failure["countryIso2"]: failure
        for failure in existing_failures
        if failure.get("countryIso2")
    }

    countries_to_build = selected_countries()
    total = len(countries_to_build)

    if total == 0:
        raise RuntimeError(
            "No countries selected. Set COUNTRY_FILTER or COUNTRY_BATCH."
        )

    print(f"Selected countries: {total}")
    print(f"COUNTRY_BATCH={BATCH_NAME}")
    print(f"FORCE_DOWNLOAD={FORCE_DOWNLOAD}")
    print(f"SKIP_EXISTING={SKIP_EXISTING}")

    countries_to_scan = []
    for iso2, slug in countries_to_build:
        if should_skip_existing(iso2):
            existing = load_existing_manifest(iso2)
            if existing:
                manifests_by_iso[iso2] = existing
                failures_by_iso.pop(iso2, None)
                print(f"SKIPPED {iso2} (existing manifest retained)")
                continue

        countries_to_scan.append((iso2, slug))

    if countries_to_scan:
        print("=" * 80)
        print(f"Single-pass scan for {len(countries_to_scan)} countries starting")

        dump_path, scanned_products, states = single_pass_collect(countries_to_scan)

        for index, (iso2, slug) in enumerate(countries_to_scan, start=1):
            print("=" * 80)
            print(f"[{index}/{len(countries_to_scan)}] Packaging {iso2} ({slug})")

            try:
                state = states[iso2]
                items, build_meta = build_meta_for_country(
                    dump_path=dump_path,
                    scanned_products=scanned_products,
                    state=state,
                )

                manifest = save_country(iso2, slug, items, build_meta)
                manifests_by_iso[iso2] = manifest
                failures_by_iso.pop(iso2, None)

                print(
                    f"[{index}/{len(countries_to_scan)}] SUCCESS {iso2} "
                    f"strategy={manifest['strategy']} "
                    f"packaged={manifest['itemCountTotal']}"
                )

            except Exception as e:
                failure = {
                    "countryIso2": iso2,
                    "slug": slug,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
                failures_by_iso[iso2] = failure

                print(f"[{index}/{len(countries_to_scan)}] FAILED {iso2} ({slug}): {e}")

            write_index(list(manifests_by_iso.values()))
            write_failures(list(failures_by_iso.values()))
    else:
        print("Nothing to scan. All selected countries were skipped.")

    print("=" * 80)
    print(
        f"Finished. Success={len(manifests_by_iso)} "
        f"Failed={len(failures_by_iso)}"
    )


if __name__ == "__main__":
    main()
