from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pandas as pd

from .config import RemediationConfig
from .normalize import normalize_provider_frame


REFERENCE_COLUMNS = [
    "provider_key",
    "field_name",
    "reference_value",
    "reference_comparison_value",
    "reference_source",
    "reference_record_id",
    "precedence_rank",
    "candidate_source_count",
]

COMPARISON_COLUMNS = [
    "listing_id",
    "provider_key",
    "field_name",
    "listing_value",
    "listing_comparison_value",
    "reference_value",
    "reference_comparison_value",
    "reference_source",
    "reference_record_id",
    "precedence_rank",
    "comparison_status",
    "is_discrepancy",
    "risk_level",
    "risk_reason",
]

IDENTITY_COLUMNS = [
    "listing_id",
    "reference_provider_key",
    "published_npi",
    "identity_status",
    "is_actionable",
    "risk_level",
    "risk_reason",
]

RISK_ORDER = {"high": 0, "medium": 1, "low": 2}

RISK_REASONS = {
    "npi": "An NPI discrepancy can misidentify the provider record.",
    "provider_name": "A provider-name discrepancy can impair directory search and matching.",
    "specialty": "A specialty discrepancy can misroute care or referrals.",
    "address": "An address discrepancy can direct patients to the wrong location.",
    "city": "A city discrepancy can direct patients to the wrong location.",
    "state": "A state discrepancy can direct patients to the wrong location.",
    "zip": "A ZIP discrepancy can direct patients to the wrong location.",
    "phone": "A phone discrepancy can prevent patient access.",
    "accepting_new_patients": "An accepting-new-patients discrepancy can create access friction.",
    "status": "A status discrepancy can expose an inactive provider in the directory.",
}


@dataclass(frozen=True)
class RemediationResult:
    payer_listings: pd.DataFrame
    listing_identity_results: pd.DataFrame
    field_source_precedence: pd.DataFrame
    reference_values: pd.DataFrame
    field_comparisons: pd.DataFrame
    discrepancies: pd.DataFrame
    risk_summary: pd.DataFrame


def run_remediation_checks(
    records: pd.DataFrame,
    payer_listings: pd.DataFrame,
    config: RemediationConfig,
) -> RemediationResult:
    """Compare synthetic payer listings without modifying source or normalized records."""
    normalized_listings = normalize_provider_frame(payer_listings)
    if "listing_id" not in normalized_listings.columns:
        normalized_listings.insert(
            0,
            "listing_id",
            [f"PAYER-{index + 1:05d}" for index in range(len(normalized_listings))],
        )
    normalized_listings["listing_id"] = normalized_listings["listing_id"].map(_display_value)

    source_precedence = build_field_source_precedence(config)
    reference_values = build_reference_values(records, config)
    listing_identity_results = assess_listing_identity(normalized_listings, reference_values)
    matched_listing_ids = set(
        listing_identity_results.loc[
            listing_identity_results["identity_status"] == "matched_reference_provider",
            "listing_id",
        ]
    )
    comparisons = compare_payer_listings(
        normalized_listings,
        reference_values,
        config,
        matched_listing_ids,
    )
    discrepancies = comparisons.loc[comparisons["is_discrepancy"]].copy()
    discrepancies = _sort_discrepancies(discrepancies)
    risk_summary = summarize_remediation_risk(discrepancies, listing_identity_results, config)

    return RemediationResult(
        payer_listings=normalized_listings.sort_values("listing_id", kind="stable").reset_index(drop=True),
        listing_identity_results=listing_identity_results,
        field_source_precedence=source_precedence,
        reference_values=reference_values,
        field_comparisons=comparisons,
        discrepancies=discrepancies,
        risk_summary=risk_summary,
    )


def assess_listing_identity(
    listings: pd.DataFrame,
    reference_values: pd.DataFrame,
) -> pd.DataFrame:
    reference_keys = set(reference_values["provider_key"])
    rows: list[dict[str, object]] = []
    for _, listing in listings.sort_values("listing_id", kind="stable").iterrows():
        reference_provider_key = _display_value(listing.get("reference_provider_key", ""))
        matched = reference_provider_key in reference_keys
        rows.append(
            {
                "listing_id": _display_value(listing.get("listing_id", "")),
                "reference_provider_key": reference_provider_key,
                "published_npi": _display_value(listing.get("npi", "")),
                "identity_status": (
                    "matched_reference_provider" if matched else "unmatched_reference_provider"
                ),
                "is_actionable": not matched,
                "risk_level": "none" if matched else "high",
                "risk_reason": (
                    "Crosswalk key matched source-record evidence."
                    if matched
                    else "No source-record evidence matches the explicit reference provider key."
                ),
            }
        )
    return pd.DataFrame(rows, columns=IDENTITY_COLUMNS)


def build_field_source_precedence(config: RemediationConfig) -> pd.DataFrame:
    rows = [
        {"field_name": field, "source": source, "precedence_rank": rank}
        for field in config.comparison_fields
        for rank, source in enumerate(config.field_source_precedence[field], start=1)
    ]
    return pd.DataFrame(rows, columns=["field_name", "source", "precedence_rank"])


def build_reference_values(records: pd.DataFrame, config: RemediationConfig) -> pd.DataFrame:
    working = records.copy(deep=True)
    working["_provider_key"] = working.apply(_provider_key_for, axis=1)
    rows: list[dict[str, object]] = []

    for provider_key, provider_rows in working.groupby("_provider_key", sort=True, dropna=False):
        for field in config.comparison_fields:
            candidates = [
                row
                for _, row in provider_rows.iterrows()
                if _is_present(row.get(field, ""))
                and _source_rank(row.get("source", ""), field, config)
                <= len(config.field_source_precedence[field])
            ]
            selected = _select_reference_candidate(candidates, field, config)
            if selected is None:
                rows.append(
                    {
                        "provider_key": provider_key,
                        "field_name": field,
                        "reference_value": "",
                        "reference_comparison_value": "",
                        "reference_source": "",
                        "reference_record_id": "",
                        "precedence_rank": "",
                        "candidate_source_count": 0,
                    }
                )
                continue

            selected_rank = _source_rank(selected.get("source", ""), field, config)
            rows.append(
                {
                    "provider_key": provider_key,
                    "field_name": field,
                    "reference_value": _display_value(selected.get(field, "")),
                    "reference_comparison_value": _comparison_value(selected, field),
                    "reference_source": _display_value(selected.get("source", "")),
                    "reference_record_id": _display_value(selected.get("record_id", "")),
                    "precedence_rank": selected_rank,
                    "candidate_source_count": len(candidates),
                }
            )

    reference_values = pd.DataFrame(rows, columns=REFERENCE_COLUMNS)
    field_order = {field: index for index, field in enumerate(config.comparison_fields)}
    return (
        reference_values.assign(_field_order=reference_values["field_name"].map(field_order))
        .sort_values(["provider_key", "_field_order"], kind="stable")
        .drop(columns="_field_order")
        .reset_index(drop=True)
    )


def compare_payer_listings(
    listings: pd.DataFrame,
    reference_values: pd.DataFrame,
    config: RemediationConfig,
    matched_listing_ids: set[str],
) -> pd.DataFrame:
    reference_lookup = {
        (str(row["provider_key"]), str(row["field_name"])): row
        for _, row in reference_values.iterrows()
    }
    rows: list[dict[str, object]] = []
    for _, listing in listings.sort_values("listing_id", kind="stable").iterrows():
        listing_id = _display_value(listing.get("listing_id", ""))
        if listing_id not in matched_listing_ids:
            continue
        provider_key = _display_value(listing.get("reference_provider_key", ""))
        for field in config.comparison_fields:
            reference = reference_lookup.get((provider_key, field))
            listing_value = _display_value(listing.get(field, ""))
            listing_comparison_value = _comparison_value(listing, field)
            reference_value = _reference_value(reference, "reference_value")
            reference_comparison_value = _reference_value(reference, "reference_comparison_value")
            status = _comparison_status(
                listing_comparison_value,
                reference_comparison_value,
            )
            is_discrepancy = status in {"discrepancy", "listing_missing"}
            risk_level = config.risk_by_field[field] if is_discrepancy else "none"
            if status == "reference_unavailable":
                risk_level = "unverified"
            rows.append(
                {
                    "listing_id": listing_id,
                    "provider_key": provider_key,
                    "field_name": field,
                    "listing_value": listing_value,
                    "listing_comparison_value": listing_comparison_value,
                    "reference_value": reference_value,
                    "reference_comparison_value": reference_comparison_value,
                    "reference_source": _reference_value(reference, "reference_source"),
                    "reference_record_id": _reference_value(reference, "reference_record_id"),
                    "precedence_rank": _reference_value(reference, "precedence_rank"),
                    "comparison_status": status,
                    "is_discrepancy": is_discrepancy,
                    "risk_level": risk_level,
                    "risk_reason": _risk_reason(field, status),
                }
            )

    comparisons = pd.DataFrame(rows, columns=COMPARISON_COLUMNS)
    field_order = {field: index for index, field in enumerate(config.comparison_fields)}
    return (
        comparisons.assign(_field_order=comparisons["field_name"].map(field_order))
        .sort_values(["listing_id", "_field_order"], kind="stable")
        .drop(columns="_field_order")
        .reset_index(drop=True)
    )


def summarize_remediation_risk(
    discrepancies: pd.DataFrame,
    listing_identity_results: pd.DataFrame,
    config: RemediationConfig,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    field_order = {field: index for index, field in enumerate(config.comparison_fields)}
    for risk_level in ("high", "medium", "low"):
        risk_rows = discrepancies.loc[discrepancies["risk_level"] == risk_level]
        unmatched_rows = listing_identity_results.loc[
            (listing_identity_results["is_actionable"])
            & (listing_identity_results["risk_level"] == risk_level)
        ]
        fields = sorted(
            set(risk_rows["field_name"]),
            key=lambda field: field_order[str(field)],
        )
        rows.append(
            {
                "risk_level": risk_level,
                "field_discrepancy_count": len(risk_rows),
                "unmatched_listing_count": len(unmatched_rows),
                "total_actionable_findings": len(risk_rows) + len(unmatched_rows),
                "affected_listings": len(
                    set(risk_rows["listing_id"]).union(unmatched_rows["listing_id"])
                ),
                "affected_provider_keys": len(
                    set(risk_rows["provider_key"]).union(
                        unmatched_rows["reference_provider_key"]
                    )
                ),
                "field_names": ";".join(fields),
            }
        )
    return pd.DataFrame(rows)


def _select_reference_candidate(
    candidates: list[pd.Series],
    field: str,
    config: RemediationConfig,
) -> pd.Series | None:
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda row: (
            _source_rank(row.get("source", ""), field, config),
            _display_value(row.get("source", "")).casefold(),
            _display_value(row.get("record_id", "")),
        ),
    )


def _source_rank(source: object, field: str, config: RemediationConfig) -> int:
    sources = config.field_source_precedence[field]
    source_key = _display_value(source).casefold()
    for rank, configured_source in enumerate(sources, start=1):
        if configured_source.casefold() == source_key:
            return rank
    return len(sources) + 1


def _provider_key_for(row: pd.Series, missing_prefix: str = "record") -> str:
    npi = _display_value(row.get("npi", ""))
    if len(npi) == 10 and npi.isdigit():
        return f"npi:{npi}"
    return f"{missing_prefix}:{_display_value(row.get('record_id', row.get('listing_id', '')))}"


def _comparison_value(row: pd.Series, field: str) -> str:
    normalized_columns = {
        "provider_name": "normalized_provider_name",
        "specialty": "normalized_specialty",
        "address": "normalized_address",
        "city": "normalized_city",
        "phone": "phone_digits",
    }
    value = row.get(normalized_columns.get(field, field), "")
    return _display_value(value)


def _comparison_status(listing_value: str, reference_value: str) -> str:
    if not _is_present(reference_value):
        return "reference_unavailable"
    if not _is_present(listing_value):
        return "listing_missing"
    return "match" if listing_value == reference_value else "discrepancy"


def _reference_value(reference: pd.Series | None, column: str) -> str | int:
    if reference is None:
        return ""
    value = reference.get(column, "")
    return _display_value(value) if column != "precedence_rank" else value


def _risk_reason(field: str, status: str) -> str:
    if status == "match":
        return "No discrepancy detected after normalized comparison."
    if status == "reference_unavailable":
        return "No nonblank reference value is available under the configured source precedence."
    if status == "listing_missing":
        return f"The payer listing is missing a value. {_field_risk_reason(field)}"
    return _field_risk_reason(field)


def _field_risk_reason(field: str) -> str:
    return RISK_REASONS.get(field, "The configured field discrepancy requires verification.")


def _sort_discrepancies(discrepancies: pd.DataFrame) -> pd.DataFrame:
    if discrepancies.empty:
        return discrepancies.reset_index(drop=True)
    return (
        discrepancies.assign(_risk_order=discrepancies["risk_level"].map(RISK_ORDER))
        .sort_values(["_risk_order", "listing_id", "field_name"], kind="stable")
        .drop(columns="_risk_order")
        .reset_index(drop=True)
    )


def _display_value(value: Any) -> str:
    if not _is_present(value):
        return ""
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.date().isoformat() if isinstance(value, (pd.Timestamp, datetime)) else value.isoformat()
    return str(value).strip()


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return str(value).strip().casefold() not in {"", "nan", "nat", "none"}
