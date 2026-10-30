"""Bounded public reference reads and explicit saved-JSON interpretation.

Adapters preserve source grain and never write storage. A timestamp in a public
source is publication/update evidence, never a directory verification date.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import ssl
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener, HTTPSHandler

import certifi

VERSION = "intake-public-v1"
MAX_BYTES = 10 * 1024 * 1024
MAX_RECORDS = 200
NPPES_URL = "https://npiregistry.cms.hhs.gov/api/"
CMS_BASE = "https://data.cms.gov/provider-data/api/1"
CMS_DATASET = "mj5m-pzi6"


class PublicFetchError(ValueError):
    """A failed public read with bounded, retainable evidence, never accepted data.

    ``payload`` is the exact response body unless metadata marks it truncated;
    connection failures have no body. ``metadata`` is JSON-serializable. Source,
    profile and label are populated by fetch_public (not the HTTP helper).
    """
    def __init__(self, message, *, payload=None, metadata=None, source=None, profile=None, label=None):
        super().__init__(message)
        self.payload: bytes | None = payload
        self.metadata: dict = dict(metadata or {})
        self.source = source
        self.profile = profile
        self.label = label


def _text(value):
    return "" if value is None else str(value).strip()


def _objects(value, label):
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(f"{label} must be a JSON array of objects")
    return value


def _decode(payload):
    if len(payload) > MAX_BYTES:
        raise ValueError("JSON response exceeds 10 MiB limit")
    try:
        return json.loads(payload.decode("utf-8-sig"))
    except (UnicodeError, ValueError) as exc:
        raise ValueError("Invalid UTF-8 JSON payload") from exc


def _location(row):
    return {
        "address": " ".join(_text(row.get(k)) for k in ("address_1", "address_2") if row.get(k)),
        "city": _text(row.get("city")), "state": _text(row.get("state")),
        "zip": _text(row.get("postal_code")), "phone": _text(row.get("telephone_number")),
        "purpose": _text(row.get("address_purpose")),
    }


def parse_json(payload: bytes, profile: str) -> list[dict]:
    """Interpret only a named envelope; preserve missing IDs and all source rows."""
    data = _decode(payload)
    if profile not in {"flat", "nppes", "cms"}:
        raise ValueError("Unsupported JSON profile; choose flat, nppes, or cms")
    if isinstance(data, dict) and any(key in data for key in ("Errors", "errors", "error")):
        raise ValueError(f"{profile} API error envelope: {str(data)[:500]}")
    if profile == "flat":
        rows = _objects(data, "Flat records")
    elif profile == "nppes":
        if not isinstance(data, dict) or "result_count" not in data:
            raise ValueError("NPPES response requires result_count and results")
        rows = _objects(data.get("results", [] if data["result_count"] == 0 else None), "NPPES results")
        if not isinstance(data["result_count"], int) or data["result_count"] != len(rows):
            raise ValueError("NPPES result_count does not match results")
    else:
        if not isinstance(data, dict) or "results" not in data:
            raise ValueError("CMS datastore response requires a results array")
        rows = _objects(data["results"], "CMS results")
    result = []
    for index, row in enumerate(rows):
        original = copy.deepcopy(row)
        updated = None
        if profile == "flat":
            normalized = copy.deepcopy(row)
            native_id = _text(row.get("record_id") or row.get("id")) or None
        elif profile == "nppes":
            basic = row.get("basic") or {}
            if not isinstance(basic, dict):
                raise ValueError(f"NPPES results[{index}].basic must be an object")
            addresses = _objects(row.get("addresses", []), "NPPES addresses")
            practice = _objects(row.get("practiceLocations", []), "NPPES practiceLocations")
            taxonomies = _objects(row.get("taxonomies", []), "NPPES taxonomies")
            locations = [{**_location(a), "source_path": f"addresses[{j}]"} for j,a in enumerate(addresses)] + [{**_location(a), "source_path": f"practiceLocations[{j}]"} for j,a in enumerate(practice)]
            primary = next((a for a in locations if a["purpose"] == "LOCATION"), locations[0] if locations else {})
            taxonomy = next((t for t in taxonomies if t.get("primary") is True), taxonomies[0] if taxonomies else {})
            native_id = _text(row.get("number")) or None
            normalized = {
                "npi": native_id or "", "provider_name": _text(basic.get("organization_name")) or
                    " ".join(_text(basic.get(k)) for k in ("first_name", "middle_name", "last_name", "credential") if basic.get(k)),
                "specialty": _text(taxonomy.get("desc")), **primary,
                "locations": locations, "taxonomies": copy.deepcopy(taxonomies),
                "status": {"A": "active", "I": "inactive"}.get(_text(basic.get("status")).upper(), "unknown"),
                "source": "NPPES Registry API", "accepting_new_patients": "unknown",
            }
            updated = _text(basic.get("last_updated")) or None
        else:
            # Column labels are the published CMS National Downloadable File labels.
            # IDs can be absent. The composite identifies native grain, never NPI alone.
            def column_key(value):
                return re.sub(r"[^a-z0-9]", "", str(value).lower())
            lower = {column_key(k): v for k, v in row.items()}
            def get(*keys):
                return next((_text(lower[column_key(k)]) for k in keys if column_key(k) in lower), "")
            native_parts = [get("NPI"), get("Ind_enrl_ID"), get("Org_PAC_ID"), get("adrs_id")]
            native_id = "|".join(native_parts) if all(native_parts) else None
            location = {"address": " ".join(filter(None, [get("adr_ln_1"), get("adr_ln_2")])),
                        "city": get("City/Town", "city"), "state": get("State"),
                        "zip": get("ZIP Code", "zip"), "phone": get("Telephone Number", "phn_numbr")}
            normalized = {"npi": get("NPI"), "provider_name": " ".join(filter(None, [get("Provider First Name", "frst_nm"), get("Provider Middle Name", "mid_nm"), get("Provider Last Name", "lst_nm")])),
                          "specialty": get("pri_spec", "Primary specialty"), **location,
                          "locations": [location], "status": "unknown", "accepting_new_patients": "unknown",
                          "source": "CMS Doctors and Clinicians", "enrollment_id": get("Ind_enrl_ID"),
                          "organization_pac_id": get("Org_PAC_ID"), "address_id": get("adrs_id")}
        result.append({"native_id": native_id, "locator": f"$[{index}]" if profile == "flat" else f"$.results[{index}]",
                       "original": original, "normalized": normalized, "source_updated_at": updated})
    return result


class _OwnedRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old, new = urlparse(req.full_url), urlparse(newurl)
        if new.scheme != "https" or new.hostname != old.hostname or new.port not in (None, 443):
            raise ValueError("Public source redirect outside connector-owned HTTPS host refused")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _read_url(url):
    context = ssl.create_default_context(cafile=certifi.where())
    opener = build_opener(HTTPSHandler(context=context), _OwnedRedirects())
    for attempt in range(3):
        try:
            with opener.open(Request(url, headers={"User-Agent": "ProviderDirectoryIntake/2.0", "Accept": "application/json"}), timeout=15) as response:
                payload = response.read(MAX_BYTES + 1)
                if len(payload) > MAX_BYTES:
                    raise PublicFetchError("Public source response exceeds 10 MiB limit", payload=payload[:MAX_BYTES], metadata={"request_url": url, "response_payload_truncated": True})
                return payload
        except HTTPError as exc:
            body = exc.read(MAX_BYTES + 1)
            exc.close()
            evidence = {"request_url": url, "http_status": exc.code,
                        "response_payload_truncated": len(body) > MAX_BYTES}
            body = body[:MAX_BYTES]
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                detail = body.decode("utf-8", errors="replace")
                raise PublicFetchError(f"Public source HTTP {exc.code}: {detail[:500]}", payload=body, metadata=evidence) from exc
            raw = exc.headers.get("Retry-After", "")
            try:
                delay = max(0, float(raw))
            except ValueError:
                try:
                    delay = max(0, (parsedate_to_datetime(raw) - datetime.now(timezone.utc)).total_seconds())
                except (ValueError, TypeError):
                    delay = 2 ** attempt
            if delay > 30:
                raise PublicFetchError(f"Public source requested Retry-After {raw}; retry later", payload=body, metadata={**evidence, "retry_after": raw}) from exc
            time.sleep(delay)
        except (URLError, TimeoutError, OSError) as exc:
            if attempt == 2:
                raise PublicFetchError(f"Public source connection failed after 3 attempts: {exc}", metadata={"request_url": url, "attempts": 3}) from exc
            time.sleep(2 ** attempt)


def fetch_public(source: str, query: dict) -> dict:
    """Fetch one bounded page, retaining scope and conservative completeness state.

    The caller persists returned bytes and metadata together. No arbitrary URL,
    bulk download, or unbounded pagination is accepted.
    """
    if source not in {"nppes", "cms"}:
        raise ValueError("Public source must be nppes or cms")
    allowed = {"limit", "number", "first_name", "last_name", "organization_name", "city", "state", "postal_code", "enumeration_type", "taxonomy_description", "skip"} if source == "nppes" else {"limit", "offset", "state", "npi"}
    if set(query) - allowed:
        raise ValueError(f"Unsupported {source} query parameters: {sorted(set(query) - allowed)}")
    try:
        limit = int(query.get("limit", 25))
        offset_key = "skip" if source == "nppes" else "offset"
        offset = int(query.get(offset_key, 0))
    except (ValueError, TypeError) as exc:
        raise ValueError("limit and offset must be integers") from exc
    if not 1 <= limit <= MAX_RECORDS or not 0 <= offset <= (1000 if source == "nppes" else 1000000):
        raise ValueError("Query limit must be 1–200 and offset within the bounded connector range")
    params = {k: str(v) for k, v in query.items() if v is not None}
    params.update({"limit": limit, offset_key: offset})
    metadata = {"adapter_version": VERSION, "source": source, "scope": dict(params), "retrieved_at": datetime.now(timezone.utc).isoformat(), "cache_status": "fresh_network", "completeness": "bounded page; not a complete directory"}
    label = "NPPES public registry" if source == "nppes" else "CMS Medicare clinician evidence"
    payload = None
    try:
        if source == "nppes":
            params["version"] = "2.1"
            url = NPPES_URL + "?" + urlencode(params)
        else:
            metadata_url = f"{CMS_BASE}/metastore/schemas/dataset/items/{CMS_DATASET}"
            metadata["request_url"] = metadata_url
            payload = _read_url(metadata_url)
            dataset = _decode(payload)
            if not isinstance(dataset, dict) or dataset.get("identifier") != CMS_DATASET or not dataset.get("distribution"):
                raise ValueError("CMS dataset metadata schema does not identify the expected distribution")
            metadata.update({"dataset_id": CMS_DATASET, "distribution_index": 0, "dataset_metadata": dataset, "dataset_metadata_url": metadata_url, "source_publication_date": dataset.get("released"), "source_modified_date": dataset.get("modified")})
            params = {"limit": limit, "offset": offset, "count": "true", "results": "true"}
            for index, (name, column) in enumerate((('state', 'state'), ('npi', 'npi'))):
                if query.get(name):
                    params.update({f"conditions[{index}][property]": column, f"conditions[{index}][value]": str(query[name]), f"conditions[{index}][operator]": "="})
            url = f"{CMS_BASE}/datastore/query/{CMS_DATASET}/0?" + urlencode(params)
        metadata["request_url"] = url
        payload = None
        payload = _read_url(url)
        rows = parse_json(payload, source)
        if len(rows) > limit:
            raise ValueError("Public source returned more records than the requested cap")
        decoded = _decode(payload)
        total = decoded.get("count") if source == "cms" else None
        try:
            total = int(total) if total is not None else None
        except (ValueError, TypeError):
            total = None
        metadata.update({"request_url": url, "returned_count": len(rows), "total_matches": total,
                         "truncated": offset + len(rows) < total if total is not None else len(rows) >= limit,
                         "response_sha256": hashlib.sha256(payload).hexdigest()})
        return {"payload": payload, "metadata": metadata, "label": "NPPES public registry" if source == "nppes" else "CMS Medicare clinician evidence", "profile": source}
    except ValueError as exc:
        evidence = {**metadata, **getattr(exc, "metadata", {}), "error": str(exc), "state": "failed"}
        failed_payload = getattr(exc, "payload", payload)
        if failed_payload is not None:
            evidence["response_sha256"] = hashlib.sha256(failed_payload).hexdigest()
        raise PublicFetchError(str(exc), payload=failed_payload, metadata=evidence,
                               source=source, profile=source, label=label) from exc
