from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

import pandas as pd

from .config import RuleConfig

if TYPE_CHECKING:
    from .remediation import RemediationResult


@dataclass(frozen=True)
class QAResult:
    clean_records: pd.DataFrame
    exceptions: pd.DataFrame
    duplicate_candidates: pd.DataFrame
    summary: pd.DataFrame
    remediation: RemediationResult | None = None


def _exception(
    row: pd.Series,
    issue_code: str,
    severity: str,
    field_name: str,
    issue_detail: str,
) -> dict[str, object]:
    recommended_action = recommended_action_for(issue_code)
    return {
        "record_id": row.get("record_id", ""),
        "npi": row.get("npi", ""),
        "provider_name": row.get("provider_name", ""),
        "specialty": row.get("specialty", ""),
        "address": row.get("address", ""),
        "city": row.get("city", ""),
        "state": row.get("state", ""),
        "source": row.get("source", ""),
        "issue_code": issue_code,
        "severity": severity,
        "field_name": field_name,
        "issue_detail": issue_detail,
        "review_status": "new",
        "assigned_to": "unassigned",
        "recommended_action": recommended_action,
        "priority_rank": priority_rank_for(severity, issue_code),
    }


def run_quality_checks(
    records: pd.DataFrame,
    config: RuleConfig,
    as_of: datetime | None = None,
) -> QAResult:
    as_of = as_of or datetime.utcnow()
    df = records.copy()
    if "record_id" not in df.columns:
        df.insert(0, "record_id", [f"REC-{i + 1:05d}" for i in range(len(df))])

    exceptions: list[dict[str, object]] = []

    for _, row in df.iterrows():
        for field in config.required_fields:
            value = row.get(field, "")
            if pd.isna(value) or str(value).strip() == "":
                exceptions.append(
                    _exception(
                        row,
                        "missing_required_field",
                        "high",
                        field,
                        f"{field} is required for directory confidence.",
                    )
                )

        if len(str(row.get("phone_digits", ""))) < config.phone_min_digits:
            exceptions.append(
                _exception(
                    row,
                    "invalid_or_missing_phone",
                    "high",
                    "phone",
                    "Phone number is missing or has too few digits for patient access.",
                )
            )

        if str(row.get("status", "")).lower() not in config.active_status_values:
            exceptions.append(
                _exception(
                    row,
                    "inactive_or_unknown_status",
                    "medium",
                    "status",
                    "Status is not an active directory value.",
                )
            )

        last_verified = row.get("last_verified_date")
        if pd.isna(last_verified):
            exceptions.append(
                _exception(
                    row,
                    "missing_verification_date",
                    "medium",
                    "last_verified_date",
                    "Record has no last verification date.",
                )
            )
        else:
            age_days = (pd.Timestamp(as_of) - pd.Timestamp(last_verified)).days
            if age_days > config.stale_days_threshold:
                exceptions.append(
                    _exception(
                        row,
                        "stale_verification",
                        "medium",
                        "last_verified_date",
                        f"Record was last verified {age_days} days ago.",
                    )
                )

        accepting = str(row.get("accepting_new_patients", "")).lower()
        if accepting not in {"yes", "no", "unknown"}:
            exceptions.append(
                _exception(
                    row,
                    "invalid_accepting_new_patients",
                    "low",
                    "accepting_new_patients",
                    "Accepting-new-patients value should be yes, no, or unknown.",
                )
            )

    duplicate_candidates = find_duplicate_candidates(df, config)
    for _, row in duplicate_candidates.iterrows():
        exceptions.append(
            {
                "record_id": row["record_ids"],
                "npi": row["npis"],
                "provider_name": row["provider_key"],
                "specialty": "",
                "address": row["address_key"],
                "city": row["city_key"],
                "state": row["state"],
                "source": row["sources"],
                "issue_code": "possible_duplicate_provider_location",
                "severity": "medium",
                "field_name": "provider/location",
                "issue_detail": "Multiple records share the same normalized provider/location key.",
                "review_status": "new",
                "assigned_to": "unassigned",
                "recommended_action": recommended_action_for("possible_duplicate_provider_location"),
                "priority_rank": priority_rank_for(
                    "medium", "possible_duplicate_provider_location"
                ),
            }
        )

    exception_df = pd.DataFrame(exceptions)
    if exception_df.empty:
        exception_df = pd.DataFrame(
            columns=[
                "record_id",
                "npi",
                "provider_name",
                "specialty",
                "address",
                "city",
                "state",
                "source",
                "issue_code",
                "severity",
                "field_name",
                "issue_detail",
                "review_status",
                "assigned_to",
                "recommended_action",
                "priority_rank",
            ]
        )

    summary = summarize_quality(df, exception_df)
    return QAResult(
        clean_records=df,
        exceptions=exception_df,
        duplicate_candidates=duplicate_candidates,
        summary=summary,
    )


def find_duplicate_candidates(records: pd.DataFrame, config: RuleConfig) -> pd.DataFrame:
    if records.empty:
        return pd.DataFrame()

    group_cols = config.duplicate_match_fields
    grouped = (
        records.groupby(group_cols, dropna=False)
        .agg(
            record_count=("record_id", "count"),
            record_ids=("record_id", lambda s: ";".join(map(str, s))),
            npis=("npi", lambda s: ";".join(sorted(set(map(str, s))))),
            sources=("source", lambda s: ";".join(sorted(set(map(str, s))))),
        )
        .reset_index()
    )
    dupes = grouped[grouped["record_count"] > 1].copy()
    if dupes.empty:
        return pd.DataFrame(
            columns=[
                "provider_key",
                "address_key",
                "city_key",
                "state",
                "record_count",
                "record_ids",
                "npis",
                "sources",
            ]
        )

    return dupes.rename(
        columns={
            "normalized_provider_name": "provider_key",
            "normalized_address": "address_key",
            "normalized_city": "city_key",
        }
    )


def summarize_quality(records: pd.DataFrame, exceptions: pd.DataFrame) -> pd.DataFrame:
    total_records = len(records)
    records_with_issues = exceptions["record_id"].nunique() if not exceptions.empty else 0
    issue_count = len(exceptions)
    severity_counts = (
        exceptions["severity"].value_counts().to_dict() if "severity" in exceptions else {}
    )
    issue_counts = (
        exceptions["issue_code"].value_counts().to_dict() if "issue_code" in exceptions else {}
    )

    rows = [
        {"metric": "total_records", "value": total_records},
        {"metric": "records_with_issues", "value": records_with_issues},
        {"metric": "total_issues", "value": issue_count},
        {
            "metric": "issue_rate",
            "value": round(records_with_issues / total_records, 4) if total_records else 0,
        },
    ]
    rows.extend({"metric": f"severity_{k}", "value": v} for k, v in severity_counts.items())
    rows.extend({"metric": f"issue_{k}", "value": v} for k, v in issue_counts.items())
    return pd.DataFrame(rows)


def recommended_action_for(issue_code: str) -> str:
    actions = {
        "missing_required_field": "verify_required_field",
        "invalid_or_missing_phone": "verify_phone",
        "inactive_or_unknown_status": "confirm_active_status",
        "missing_verification_date": "add_verification_date",
        "stale_verification": "refresh_stale_record",
        "invalid_accepting_new_patients": "confirm_accepting_new_patients",
        "possible_duplicate_provider_location": "review_duplicate_candidate",
    }
    return actions.get(issue_code, "review_record")


def priority_rank_for(severity: str, issue_code: str) -> int:
    severity_base = {"high": 100, "medium": 200, "low": 300}.get(severity, 400)
    issue_adjustments = {
        "missing_required_field": 0,
        "invalid_or_missing_phone": 5,
        "possible_duplicate_provider_location": 10,
        "stale_verification": 20,
        "inactive_or_unknown_status": 30,
        "missing_verification_date": 40,
        "invalid_accepting_new_patients": 50,
    }
    return severity_base + issue_adjustments.get(issue_code, 90)
