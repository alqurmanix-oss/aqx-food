#!/usr/bin/env python3
"""Import a bounded 100-record-per-dataset sample to measure actual PostgreSQL growth."""
import json
import os
import pathlib
import tempfile
import zipfile

import ijson
import requests

GATEWAY = os.environ["AQX_FOOD_SAMPLE_URL"].rstrip("/")
AUDIENCE = "aqx-food-usda-import"
DATASETS = {
    "FOUNDATION": ("FoundationFoods.item", "FoodData_Central_foundation_food_json_"),
    "SR_LEGACY": ("SRLegacyFoods.item", "FoodData_Central_sr_legacy_food_json_"),
    "FNDDS": ("SurveyFoods.item", "surveyDownload.json"),
}
SAMPLE_LIMIT = 100


def oidc_token():
    response = requests.get(
        os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"],
        headers={"Authorization": f"Bearer {os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']}"},
        params={"audience": AUDIENCE},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["value"]


def gateway(action, **payload):
    response = requests.post(
        GATEWAY,
        headers={"Authorization": f"Bearer {oidc_token()}"},
        json={"action": action, **payload},
        timeout=180,
    )
    response.raise_for_status()
    return response.json()


def normalize(record):
    category = record.get("foodCategory")
    if isinstance(category, dict):
        category = category.get("description") or category.get("name")
    elif category is not None:
        category = str(category)
    excluded = {
        "fdcId", "description", "dataType", "publicationDate",
        "foodCategory", "foodNutrients",
    }
    metadata = {key: value for key, value in record.items() if key not in excluded}
    return {
        "fdc_id": str(record["fdcId"]),
        "description": str(record["description"]),
        "data_type": record.get("dataType"),
        "publication_date": record.get("publicationDate"),
        "food_category": category,
        "nutrients": record.get("foodNutrients") or [],
        "source_metadata": metadata,
    }


def main():
    status = gateway("status").get("status")
    if not isinstance(status, dict):
        raise RuntimeError("Gateway returned no dataset status map")
    results = []
    with tempfile.TemporaryDirectory(prefix="aqx-food-sample-") as temp_dir:
        for code, (prefix, expected_member) in DATASETS.items():
            item = status.get(code)
            if not isinstance(item, dict):
                raise RuntimeError(f"{code}: missing dataset status")
            if item.get("status") == "imported":
                raise RuntimeError(f"{code}: already marked imported; sample aborted")
            version = item.get("version") or item.get("dataset_version")
            if not version:
                raise RuntimeError(f"{code}: trusted dataset version missing")
            url = item.get("signed_url")
            if not url:
                raise RuntimeError(f"{code}: signed archive URL missing")
            archive_path = pathlib.Path(temp_dir) / f"{code}.zip"
            with requests.get(url, stream=True, timeout=(30, 300)) as response:
                response.raise_for_status()
                with archive_path.open("wb") as target:
                    for chunk in response.iter_content(1024 * 1024):
                        if chunk:
                            target.write(chunk)
            with zipfile.ZipFile(archive_path) as archive:
                matches = [
                    member for member in archive.infolist()
                    if not member.is_dir()
                    and (member.filename == expected_member or member.filename.startswith(expected_member))
                ]
                if len(matches) != 1:
                    raise RuntimeError(f"{code}: expected one JSON member, found {[m.filename for m in matches]}")
                records = []
                with archive.open(matches[0]) as stream:
                    for record in ijson.items(stream, prefix, use_float=True):
                        if not isinstance(record, dict) or not record.get("fdcId") or not record.get("description"):
                            raise RuntimeError(f"{code}: invalid required fields in sample")
                        records.append(normalize(record))
                        if len(records) == SAMPLE_LIMIT:
                            break
            if len(records) != SAMPLE_LIMIT:
                raise RuntimeError(f"{code}: expected {SAMPLE_LIMIT} records, got {len(records)}")
            result = gateway(
                "sample_batch",
                dataset_code=code,
                dataset_version=version,
                records=records,
            )
            results.append({
                "dataset": code,
                "version": version,
                "sample_records": len(records),
                "upserted": result.get("upserted"),
                "database_bytes_after_batch": result.get("database_bytes"),
            })
    print(json.dumps({
        "mode": "BOUNDED_STORAGE_SIZING_SAMPLE",
        "max_records_per_dataset": SAMPLE_LIMIT,
        "total_records_submitted": sum(x["sample_records"] for x in results),
        "results": results,
        "full_import_started": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
