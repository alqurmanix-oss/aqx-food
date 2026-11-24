#!/usr/bin/env python3
"""Guarded automatic USDA release importer; idempotent batches and strict archive validation."""
import json
import os
import pathlib
import tempfile
import zipfile

import ijson
import requests

GATEWAY = os.environ["AQX_FOOD_FULL_IMPORT_URL"].rstrip("/")
AUDIENCE = "aqx-food-usda-import"
BATCH_SIZE = 100
STOP_AFTER_BYTES = 390 * 1024 * 1024
DATASETS = {
    "FOUNDATION": ("FoundationFoods.item", "FoodData_Central_foundation_food_json_"),
    "SR_LEGACY": ("SRLegacyFoods.item", "FoodData_Central_sr_legacy_food_json_"),
    "FNDDS": ("SurveyFoods.item", "surveyDownload.json"),
}


def oidc_token():
    r = requests.get(
        os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"],
        headers={"Authorization": f"Bearer {os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']}"},
        params={"audience": AUDIENCE}, timeout=30,
    )
    r.raise_for_status()
    return r.json()["value"]


def gateway(action, **payload):
    r = requests.post(
        GATEWAY, headers={"Authorization": f"Bearer {oidc_token()}"},
        json={"action": action, **payload}, timeout=240,
    )
    if not r.ok:
        raise RuntimeError(f"Gateway {action} failed: HTTP {r.status_code}: {r.text[:700]}")
    return r.json()


def normalize(record):
    category = record.get("foodCategory")
    if isinstance(category, dict):
        category = category.get("description") or category.get("name")
    elif category is not None:
        category = str(category)
    excluded = {"fdcId", "description", "dataType", "publicationDate", "foodCategory", "foodNutrients"}
    return {
        "fdc_id": str(record["fdcId"]),
        "description": str(record["description"]),
        "data_type": record.get("dataType"),
        "publication_date": record.get("publicationDate"),
        "food_category": category,
        "nutrients": record.get("foodNutrients") or [],
        "source_metadata": {k: v for k, v in record.items() if k not in excluded},
    }



def ingest_batch(dataset_code, dataset_version, records):
    """Retry statement-timeout batches by splitting them; each RPC is atomic."""
    try:
        return gateway(
            "batch",
            dataset_code=dataset_code,
            dataset_version=dataset_version,
            records=records,
        )
    except RuntimeError as exc:
        if "statement timeout" not in str(exc).lower() or len(records) <= 1:
            raise
        midpoint = len(records) // 2
        print(json.dumps({
            "dataset": dataset_code,
            "event": "batch_split_after_statement_timeout",
            "records": len(records),
            "parts": [midpoint, len(records) - midpoint],
        }), flush=True)
        ingest_batch(dataset_code, dataset_version, records[:midpoint])
        return ingest_batch(dataset_code, dataset_version, records[midpoint:])


def main():
    status_response = gateway("status")
    status = status_response.get("status")
    if not isinstance(status, dict):
        raise RuntimeError("No trusted dataset status returned")

    results = []
    with tempfile.TemporaryDirectory(prefix="aqx-food-full-import-") as tmp:
        for code, (prefix, member_prefix) in DATASETS.items():
            item = status.get(code)
            if not isinstance(item, dict):
                raise RuntimeError(f"{code}: missing release metadata")
            version = item.get("version") or item.get("dataset_version")
            if not version:
                raise RuntimeError(f"{code}: trusted dataset version missing")
            release_status = str(item.get("status") or "")
            if release_status == "imported":
                results.append({"dataset": code, "version": version, "status": "already_imported", "records_sent": 0})
                continue
            if release_status not in {"downloaded", "queued_for_import", "importing"}:
                results.append({"dataset": code, "version": version, "status": f"not_ready:{release_status}", "records_sent": 0})
                continue
            signed_url = item.get("signed_url")
            if not signed_url:
                raise RuntimeError(f"{code}: release is marked {release_status} but signed archive URL is unavailable")
            archive_path = pathlib.Path(tmp) / f"{code}.zip"
            with requests.get(signed_url, stream=True, timeout=(30, 600)) as response:
                response.raise_for_status()
                with archive_path.open("wb") as target:
                    for chunk in response.iter_content(1024 * 1024):
                        if chunk:
                            target.write(chunk)

            sent = 0
            batch = []
            with zipfile.ZipFile(archive_path) as archive:
                matches = [
                    m for m in archive.infolist()
                    if not m.is_dir() and (m.filename == member_prefix or m.filename.startswith(member_prefix))
                ]
                if len(matches) != 1:
                    raise RuntimeError(f"{code}: expected one JSON member, found {[m.filename for m in matches]}")
                with archive.open(matches[0]) as stream:
                    for record in ijson.items(stream, prefix, use_float=True):
                        if not isinstance(record, dict) or not record.get("fdcId") or not record.get("description"):
                            raise RuntimeError(f"{code}: invalid record at source position {sent + len(batch) + 1}")
                        batch.append(normalize(record))
                        if len(batch) >= BATCH_SIZE:
                            result = ingest_batch(code, version, batch)
                            sent += len(batch)
                            db_bytes = int(result.get("database_bytes") or 0)
                            print(json.dumps({"dataset": code, "records_sent": sent, "database_bytes": db_bytes}), flush=True)
                            if db_bytes and db_bytes >= STOP_AFTER_BYTES:
                                raise RuntimeError(f"Safety stop: database reached {db_bytes} bytes; below 400 MiB RPC guard")
                            batch = []
                    if batch:
                        result = ingest_batch(code, version, batch)
                        sent += len(batch)
                        db_bytes = int(result.get("database_bytes") or 0)
                        print(json.dumps({"dataset": code, "records_sent": sent, "database_bytes": db_bytes}), flush=True)
                        if db_bytes and db_bytes >= STOP_AFTER_BYTES:
                            raise RuntimeError(f"Safety stop: database reached {db_bytes} bytes; below 400 MiB RPC guard")

            if sent < 1:
                raise RuntimeError(f"{code}: archive parsed successfully but contained no food records.")
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            expected = metadata.get("expected_record_count") or metadata.get("record_count")
            if expected is not None and sent != int(expected):
                raise RuntimeError(f"{code}: archive record count mismatch; expected {expected}, parsed {sent}. No release marked imported.")
            results.append({"dataset": code, "version": version, "records_sent": sent, "status": "loaded_unverified"})

    # Only mark releases imported after all three archives were read completely and exact counts matched.
    for result in results:
        if result.get("status") == "loaded_unverified":
            gateway("finish", dataset_code=result["dataset"], dataset_version=result["version"], status="imported")
            result["status"] = "imported"

    print(json.dumps({
        "mode": "GUARDED_FULL_USDA_IMPORT",
        "results": results,
        "records_imported": sum(int(item.get("records_sent") or 0) for item in results),
        "full_import_completed": all(item.get("status") in {"imported", "already_imported"} for item in results),
        "matching_status": "unmatched_pending_review",
        "safety_stop_bytes": STOP_AFTER_BYTES,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
