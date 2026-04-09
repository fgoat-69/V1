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

# OFF-supported countries you want to build.
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

COUNTRY_FILTER = {
    token.strip().upper()
    for token in os.getenv("COUNTRY_FILTER", "").split(",")
    if token.strip()
}

FORCE_DOWNLOAD = os.getenv("FORCE_DOWNLOAD", "").strip().lower() in {"1", "true", "yes"}
SKIP_EXISTING = os.getenv("SKIP_EXISTING", "").strip().lower() in {"1", "true", "yes"}


def ensure_output_root():
    os.makedirs("countries", exist_ok=True)


def selected_countries():
    if not COUNTRY_FILTER:
        return COUNTRIES

    return [
        (iso2, slug)
        for (iso2, slug) in COUNTRIES
        if iso2.upper() in COUNTRY_FILTER
    ]


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


def init_country_state(iso2, slug):
    return {
        "countryIso2": iso2,
        "slug": slug,
        "seen": set(),
        "items": [],
        "matchedProducts": 0,
        "mappedProducts": 0,
        "dedupedProducts": 0,
    }


def build_token_to_iso_map(countries_to_build):
    token_to_iso = {}

    for iso2, slug in countries_to_build:
        token_to_iso[iso2.lower()] = iso2
        token_to_iso[slug.lower()] = iso2

    return token_to_iso


def matched_country_isos(product, token_to_iso):
    tokens = product_country_tokens(product)
    matched = {token_to_iso[token] for token in tokens if token in token_to_iso}
    return matched


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
            "country filtering, app-field reduction, and per-country deduplication. "
            "Large countries are popularity-sorted using OFF popularity fields when available "
            "before budget-based packaging."
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
        "discoveredItemCount": len(discovered_items),
        "discoveredBytes": json_bytes(discovered_items),
    }


def main():
    ensure_output_root()

    manifests = []
    failures = []

    countries_to_build = selected_countries()
    total = len(countries_to_build)

    if total == 0:
        raise RuntimeError(
            "No countries selected. Check COUNTRY_FILTER env var, e.g. COUNTRY_FILTER=HU,RO"
        )

    print(f"Selected countries: {total}")
    print(f"FORCE_DOWNLOAD={FORCE_DOWNLOAD}")
    print(f"SKIP_EXISTING={SKIP_EXISTING}")

    countries_to_scan = []
    for iso2, slug in countries_to_build:
        if should_skip_existing(iso2):
            existing = load_existing_manifest(iso2)
            if existing:
                manifests.append(existing)
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
                manifests.append(manifest)

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
                failures.append(failure)

                print(f"[{index}/{len(countries_to_scan)}] FAILED {iso2} ({slug}): {e}")

            write_index(manifests)
            write_failures(failures)
    else:
        print("Nothing to scan. All selected countries were skipped.")

    print("=" * 80)
    print(f"Finished. Success={len(manifests)} Failed={len(failures)}")


if __name__ == "__main__":
    main()
