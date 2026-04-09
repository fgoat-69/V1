import json
import os
import traceback
from datetime import datetime, timezone

from build_country_pack import build_country, save_country

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

    for index, (iso2, slug) in enumerate(countries_to_build, start=1):
        print("=" * 80)
        print(f"[{index}/{total}] Building {iso2} ({slug})")

        try:
            if should_skip_existing(iso2):
                existing = load_existing_manifest(iso2)
                if existing:
                    manifests.append(existing)
                    print(f"[{index}/{total}] SKIPPED {iso2} (existing manifest retained)")
                    write_index(manifests)
                    write_failures(failures)
                    continue

            items, build_meta = build_country(
                iso2,
                slug,
                download_if_missing=True,
                force_download=FORCE_DOWNLOAD,
            )
            manifest = save_country(iso2, slug, items, build_meta)
            manifests.append(manifest)

            print(
                f"[{index}/{total}] SUCCESS {iso2} "
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

            print(f"[{index}/{total}] FAILED {iso2} ({slug}): {e}")

        write_index(manifests)
        write_failures(failures)

    print("=" * 80)
    print(f"Finished. Success={len(manifests)} Failed={len(failures)}")


if __name__ == "__main__":
    main()
