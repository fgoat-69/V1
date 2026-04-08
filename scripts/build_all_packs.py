import json
import os

from build_country_pack import build_country, save_country

COUNTRIES = [
    ("HU", "hungary"),
    ("DE", "germany"),
    ("AL", "albania"),
    ("FR", "france"),
    ("HN", "honduras"),
]


def main():
    manifests = []

    for iso2, slug in COUNTRIES:
        try:
            items = build_country(iso2, slug)
            manifest = save_country(iso2, slug, items)
            manifests.append(manifest)
        except Exception as e:
            print(f"FAILED {iso2} ({slug}): {e}")

    os.makedirs("countries", exist_ok=True)
    with open("countries/index.json", "w", encoding="utf-8") as f:
        json.dump(manifests, f, ensure_ascii=False)

    print("Done building all packs")


if __name__ == "__main__":
    main()
