#!/usr/bin/env python3
"""Read-only USDA archive format probe for AQX Food.

This script never writes to Supabase. It obtains short-lived download URLs from
the AQX Food OIDC gateway, downloads the existing private archives, and reports
ZIP members plus a bounded JSON prefix for format verification.
"""
import json
import os
import pathlib
import sys
import zipfile
import requests

GATEWAY = os.environ["AQX_FOOD_INGEST_URL"].rstrip("/")
AUDIENCE = "aqx-food-usda-import"
OUT = pathlib.Path("usda-probe")
OUT.mkdir(exist_ok=True)

def oidc_token():
    url = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"]
    request_token = os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]
    response = requests.get(url, headers={"Authorization": f"Bearer {request_token}"},
                            params={"audience": AUDIENCE}, timeout=30)
    response.raise_for_status()
    return response.json()["value"]

def main():
    token = oidc_token()
    response = requests.post(GATEWAY, headers={"Authorization": f"Bearer {token}"},
                             json={"action": "status"}, timeout=60)
    response.raise_for_status()
    status = response.json()["status"]
    for code, item in sorted(status.items()):
        if item.get("status") == "imported":
            print(f"{code}: already imported; skipped")
            continue
        url = item.get("signed_url")
        if not url:
            print(f"{code}: no signed URL; skipped")
            continue
        archive_path = OUT / f"{code}.zip"
        with requests.get(url, stream=True, timeout=(30, 300)) as download:
            download.raise_for_status()
            with archive_path.open("wb") as target:
                for chunk in download.iter_content(1024 * 1024):
                    if chunk:
                        target.write(chunk)
        print(f"\n[{code}] version={item.get('dataset_version')} archive_bytes={archive_path.stat().st_size}")
        with zipfile.ZipFile(archive_path) as archive:
            members = [m for m in archive.infolist() if not m.is_dir()]
            for member in members:
                print(f"member={member.filename} compressed={member.compress_size} uncompressed={member.file_size}")
                if member.filename.lower().endswith(".json") and ("food" in member.filename.lower() or len(members) == 1):
                    with archive.open(member) as stream:
                        prefix = stream.read(8192).decode("utf-8-sig", errors="replace")
                    print("json_prefix=" + json.dumps(prefix[:4000], ensure_ascii=False))
                    break
    print("\nPROBE_ONLY: no database records were inserted or modified.")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"probe_failed: {exc}", file=sys.stderr)
        raise
