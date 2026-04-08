import json
import os
from datetime import datetime, timezone

from build_country_pack import build_country, save_country

COUNTRIES = [
    ("HU", "hungary"),
    ("DE", "germany"),
    ("AL", "albania"),
    ("FR", "france"),
    ("HN", "honduras"),
]


def write_index(manifests):
    os.makedirs("countries", exist_ok=True)

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "countries": sorted(manifests, key=lambda x: x["countryIso2"]),
    }

    with open("countries/index.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def main():
    manifests = []

    for iso2, slug in COUNTRIES:
        try:
            items, build_meta = build_country(iso2, slug)
            manifest = save_country(iso2, slug, items, build_meta)
            manifests.append(manifest)
        except Exception as e:
            print(f"FAILED {iso2} ({slug}): {e}")

    write_index(manifests)
    print("Done building all packs")


if __name__ == "__main__":
    main()
