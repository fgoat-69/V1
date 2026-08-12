import hashlib
import os
from datetime import datetime, timezone
from typing import Any


MANIFEST_SCHEMA_VERSION = 1

ALLOWED_PACK_TYPES = {
    "openfoodfacts",
    "national",
    "bundled",
    "custom",
}

CANONICAL_SOURCE_IDS = {
    "usda_fdc",
    "openfoodfacts",
    "germany_bls",
    "france_ciqual",
    "canada_cnf",
    "uk_cofid_2021",
    "fineli_thl",
    "custom",
}

PROHIBITED_SOURCE_IDS = {
    "github_country_pack",
    "downloaded_pack",
    "national_pack",
    "country_pack",
    "off_local",
    "open_food_facts",
    "fooddata_central",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_source_id(source: str) -> None:
    normalized_source = source.strip()

    if not normalized_source:
        raise ValueError("Manifest source must not be empty.")

    if normalized_source in PROHIBITED_SOURCE_IDS:
        raise ValueError(
            f"Source '{normalized_source}' describes transport or legacy storage, "
            "not the original dataset."
        )

    if normalized_source not in CANONICAL_SOURCE_IDS:
        raise ValueError(
            f"Unknown source identifier '{normalized_source}'. "
            "Add approved new identifiers to CANONICAL_SOURCE_IDS first."
        )


def validate_pack_type(pack_type: str) -> None:
    normalized_pack_type = pack_type.strip()

    if not normalized_pack_type:
        raise ValueError("Manifest packType must not be empty.")

    if normalized_pack_type not in ALLOWED_PACK_TYPES:
        raise ValueError(
            f"Unknown pack type '{normalized_pack_type}'. "
            f"Allowed values: {', '.join(sorted(ALLOWED_PACK_TYPES))}"
        )


def sha256_file(file_path: str) -> str:
    if not os.path.isfile(file_path):
        raise FileNotFoundError(
            f"Cannot calculate SHA-256 for missing file: {file_path}"
        )

    digest = hashlib.sha256()

    with open(file_path, "rb") as source_file:
        while True:
            chunk = source_file.read(1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def build_file_entry(
    *,
    file_path: str,
    relative_path: str,
    kind: str,
    record_count: int,
) -> dict[str, Any]:
    if not os.path.isfile(file_path):
        raise FileNotFoundError(
            f"Cannot create manifest entry for missing file: {file_path}"
        )

    if not relative_path.strip():
        raise ValueError("Manifest file path must not be empty.")

    if not kind.strip():
        raise ValueError("Manifest file kind must not be empty.")

    if record_count < 0:
        raise ValueError("Manifest file record count must not be negative.")

    return {
        "name": os.path.basename(file_path),
        "path": relative_path.replace("\\", "/"),
        "kind": kind.strip(),
        "recordCount": int(record_count),
        "bytes": os.path.getsize(file_path),
        "sha256": sha256_file(file_path),
    }


def build_standard_manifest(
    *,
    pack_id: str,
    pack_type: str,
    country_iso2: str,
    source: str,
    source_name: str,
    publisher: str,
    dataset_version: str,
    license_id: str,
    source_url: str,
    license_url: str,
    modified: bool,
    modifications: list[str],
    generated_at: str,
    record_count: int,
    files: list[dict[str, Any]],
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_pack_id = pack_id.strip()
    normalized_pack_type = pack_type.strip()
    normalized_country = country_iso2.strip().upper()
    normalized_source = source.strip()
    normalized_source_name = source_name.strip()
    normalized_publisher = publisher.strip()
    normalized_dataset_version = dataset_version.strip()
    normalized_license_id = license_id.strip()
    normalized_source_url = source_url.strip()
    normalized_license_url = license_url.strip()
    normalized_generated_at = generated_at.strip()

    validate_source_id(normalized_source)
    validate_pack_type(normalized_pack_type)

    if not normalized_pack_id:
        raise ValueError("Manifest packId must not be empty.")

    if len(normalized_country) != 2 or not normalized_country.isalpha():
        raise ValueError(
            "countryIso2 must contain exactly two alphabetic characters."
        )

    if not normalized_source_name:
        raise ValueError("Manifest sourceName must not be empty.")

    if not normalized_publisher:
        raise ValueError("Manifest publisher must not be empty.")

    if not normalized_dataset_version:
        raise ValueError("Manifest datasetVersion must not be empty.")

    if not normalized_license_id:
        raise ValueError("Manifest license must not be empty.")

    if not normalized_source_url:
        raise ValueError("Manifest sourceUrl must not be empty.")

    if not normalized_license_url:
        raise ValueError("Manifest licenseUrl must not be empty.")

    if not normalized_generated_at:
        raise ValueError("Manifest generatedAt must not be empty.")

    if record_count < 0:
        raise ValueError("Manifest recordCount must not be negative.")

    cleaned_modifications = [
        modification.strip()
        for modification in modifications
        if modification and modification.strip()
    ]

    if modified and not cleaned_modifications:
        raise ValueError(
            "A modified pack must describe at least one modification."
        )

    if not files:
        raise ValueError("Manifest must contain at least one generated file.")

    calculated_record_count = sum(
        int(file_entry.get("recordCount", 0))
        for file_entry in files
    )

    if calculated_record_count != int(record_count):
        raise ValueError(
            "Manifest recordCount does not match the combined record count "
            f"of its files: manifest={record_count}, "
            f"files={calculated_record_count}"
        )

    manifest: dict[str, Any] = {
        "schemaVersion": MANIFEST_SCHEMA_VERSION,
        "packId": normalized_pack_id,
        "packType": normalized_pack_type,
        "countryIso2": normalized_country,
        "source": normalized_source,
        "sourceName": normalized_source_name,
        "publisher": normalized_publisher,
        "datasetVersion": normalized_dataset_version,
        "license": normalized_license_id,
        "sourceUrl": normalized_source_url,
        "licenseUrl": normalized_license_url,
        "modified": bool(modified),
        "modifications": cleaned_modifications,
        "generatedAt": normalized_generated_at,
        "recordCount": int(record_count),
        "files": files,
    }

    if extra_fields:
        protected_fields = set(manifest.keys())
        conflicting_fields = protected_fields.intersection(extra_fields.keys())

        if conflicting_fields:
            joined_fields = ", ".join(sorted(conflicting_fields))

            raise ValueError(
                "extra_fields cannot replace standard manifest fields: "
                f"{joined_fields}"
            )

        manifest.update(extra_fields)

    return manifest
