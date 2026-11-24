#!/usr/bin/env python3
"""Read-only USDA archive sizing pass. Never calls a database write endpoint."""
import json
import os
import pathlib
import tempfile
import zipfile

import ijson
import requests

GATEWAY = os.environ["AQX_FOOD_INGEST_URL"].rstrip("/")
AUDIENCE = "aqx-food-usda-import"
DATASETS = {
    "FOUNDATION": ("FoundationFoods.item", "FoodData_Central_foundation_food_json_"),
    "SR_LEGACY": ("SRLegacyFoods.item", "FoodData_Central_sr_legacy_food_json_"),
    "FNDDS": ("SurveyFoods.item", "surveyDownload.json"),
}


def get_oidc_token():
    response = requests.get(
        os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"],
        headers={"Authorization": f"Bearer {os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']}"},
        params={"audience": AUDIENCE},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["value"]


def fetch_status():
    response = requests.post(
        GATEWAY,
        headers={"Authorization": f"Bearer {get_oidc_token()}"},
        json={"action": "status"},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload.get("status"), dict):
        raise RuntimeError("Gateway response did not contain a status map")
    return payload["status"]


def inspect_dataset(code, item, temp_dir):
    prefix, expected_member = DATASETS[code]
    url = item.get("signed_url")
    if not url:
        raise RuntimeError(f"{code}: gateway did not provide a signed archive URL")

    archive_path = pathlib.Path(temp_dir) / f"{code}.zip"
    with requests.get(url, stream=True, timeout=(30, 300)) as response:
        response.raise_for_status()
        with archive_path.open("wb") as target:
            for chunk in response.iter_content(1024 * 1024):
                if chunk:
                    target.write(chunk)

    with zipfile.ZipFile(archive_path) as archive:
        candidates = [
            member for member in archive.infolist()
            if not member.is_dir()
            and (member.filename == expected_member or member.filename.startswith(expected_member))
        ]
        if len(candidates) != 1:
            raise RuntimeError(
                f"{code}: expected exactly one JSON member matching {expected_member!r}; "
                f"found {[m.filename for m in candidates]}"
            )
        member = candidates[0]
        record_count = 0
        nutrient_count = 0
        missing_id = 0
        missing_description = 0
        serialized_bytes = 0
        max_record_bytes = 0
        seen_ids = set()
        duplicate_ids = 0

        with archive.open(member) as stream:
            # use_float avoids Decimal objects that json.dumps cannot serialize.
            # It is used only for this read-only size estimate, not for ingestion.
            for record in ijson.items(stream, prefix, use_float=True):
                if not isinstance(record, dict):
                    raise RuntimeError(f"{code}: encountered a non-object food record")
                record_count += 1
                record_id = record.get("fdcId")
                if record_id is None:
                    missing_id += 1
                elif record_id in seen_ids:
                    duplicate_ids += 1
                else:
                    seen_ids.add(record_id)
                if not record.get("description"):
                    missing_description += 1
                nutrients = record.get("foodNutrients") or []
                if isinstance(nutrients, list):
                    nutrient_count += len(nutrients)
                row_bytes = len(json.dumps(
                    record, ensure_ascii=False, separators=(",", ":"), allow_nan=False
                ).encode("utf-8"))
                serialized_bytes += row_bytes
                max_record_bytes = max(max_record_bytes, row_bytes)

        if record_count == 0:
            raise RuntimeError(f"{code}: parser found zero food records")

    return {
        "dataset": code,
        "dataset_version_reported_by_gateway": item.get("dataset_version"),
        "archive_bytes": archive_path.stat().st_size,
        "json_member": member.filename,
        "json_uncompressed_bytes": member.file_size,
        "food_records": record_count,
        "nutrient_entries": nutrient_count,
        "serialized_record_payload_bytes": serialized_bytes,
        "average_record_payload_bytes": round(serialized_bytes / record_count, 1),
        "largest_record_payload_bytes": max_record_bytes,
        "missing_fdc_id": missing_id,
        "missing_description": missing_description,
        "duplicate_fdc_ids_within_dataset": duplicate_ids,
        "note": "Serialized source-record payload only; not a PostgreSQL/JSONB storage estimate.",
    }


def main():
    status = fetch_status()
    summaries = []
    with tempfile.TemporaryDirectory(prefix="aqx-food-sizing-") as temp_dir:
        for code in DATASETS:
            item = status.get(code)
            if not isinstance(item, dict):
                raise RuntimeError(f"{code}: dataset missing from gateway status")
            if item.get("status") == "imported":
                raise RuntimeError(
                    f"{code}: already marked imported; refusing to size against a changing state"
                )
            summaries.append(inspect_dataset(code, item, temp_dir))

    total_records = sum(x["food_records"] for x in summaries)
    total_payload = sum(x["serialized_record_payload_bytes"] for x in summaries)
    print(json.dumps({
        "mode": "READ_ONLY_DRY_RUN",
        "database_writes": False,
        "datasets": summaries,
        "totals": {
            "food_records": total_records,
            "nutrient_entries": sum(x["nutrient_entries"] for x in summaries),
            "serialized_record_payload_bytes": total_payload,
            "serialized_record_payload_mib": round(total_payload / (1024 * 1024), 2),
        },
        "safety": (
            "No Supabase database write endpoint was called. Payload bytes are not a "
            "database-size prediction; a measured pilot would be required before import."
        ),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
