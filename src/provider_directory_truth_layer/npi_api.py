from __future__ import annotations

import json
import ssl
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import certifi
import pandas as pd


NPI_API_URL = "https://npiregistry.cms.hhs.gov/api/"


def fetch_npi_records(
    city: str,
    state: str,
    limit: int = 50,
    version: str = "2.1",
    request_limit: int | None = None,
) -> list[dict[str, Any]]:
    api_limit = request_limit or limit
    params = urllib.parse.urlencode(
        {
            "version": version,
            "city": city,
            "state": state,
            "limit": api_limit,
        }
    )
    url = f"{NPI_API_URL}?{params}"
    context = ssl.create_default_context(cafile=certifi.where())
    request = urllib.request.Request(url, headers={"User-Agent": "provider-directory-truth-layer/0.1"})
    with urllib.request.urlopen(request, timeout=30, context=context) as response:
        payload = json.load(response)
    return list(payload.get("results", []))


def npi_records_to_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    rows = [map_npi_record(record) for record in records]
    return pd.DataFrame(rows, columns=list(map_npi_record({})))


def write_npi_sample_csv(
    records: list[dict[str, Any]],
    output_csv: Path,
    city_filter: str | None = None,
    state_filter: str | None = None,
    limit: int | None = None,
) -> Path:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    frame = npi_records_to_frame(records)
    if city_filter:
        frame = frame[frame["city"].str.upper() == city_filter.upper()]
    if state_filter:
        frame = frame[frame["state"].str.upper() == state_filter.upper()]
    if limit is not None:
        frame = frame.head(limit)
    frame.to_csv(output_csv, index=False)
    return output_csv


def map_npi_record(record: dict[str, Any], index: int | None = None) -> dict[str, str]:
    """Map the legacy one-location sample; index is retained for caller compatibility.

    Native NPI identity is independent of result order. Missing native identity
    remains missing rather than acquiring a misleading positional identifier.
    """
    basic = record.get("basic") or {}
    address = _location_address(record.get("addresses") or [])
    taxonomy = _primary_taxonomy(record.get("taxonomies") or [])
    status = {"A": "active", "I": "inactive"}.get(
        str(basic.get("status") or "").upper(), "unknown"
    )
    npi = str(record.get("number") or "").strip()

    return {
        "record_id": f"NPI-{npi}" if npi else "",
        "npi": npi,
        "provider_name": _provider_name(record),
        "specialty": str(taxonomy.get("desc") or ""),
        "address": _join_address(address),
        "city": str(address.get("city") or ""),
        "state": str(address.get("state") or ""),
        "zip": str(address.get("postal_code") or "")[:5],
        "phone": str(address.get("telephone_number") or ""),
        "accepting_new_patients": "unknown",
        "source": "NPI Registry API",
        "status": status,
        "last_verified_date": "",
        "source_updated_at": str(basic.get("last_updated") or ""),
    }


def _provider_name(record: dict[str, Any]) -> str:
    basic = record.get("basic") or {}
    if basic.get("organization_name"):
        return str(basic["organization_name"])

    parts = [
        basic.get("first_name"),
        basic.get("middle_name"),
        basic.get("last_name"),
        basic.get("credential"),
    ]
    return " ".join(str(part).strip() for part in parts if part).strip()


def _location_address(addresses: list[dict[str, Any]]) -> dict[str, Any]:
    for address in addresses:
        if str(address.get("address_purpose", "")).upper() == "LOCATION":
            return address
    return addresses[0] if addresses else {}


def _primary_taxonomy(taxonomies: list[dict[str, Any]]) -> dict[str, Any]:
    for taxonomy in taxonomies:
        if taxonomy.get("primary") is True:
            return taxonomy
    return taxonomies[0] if taxonomies else {}


def _join_address(address: dict[str, Any]) -> str:
    parts = [address.get("address_1"), address.get("address_2")]
    return " ".join(str(part).strip() for part in parts if part).strip()
