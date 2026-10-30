from __future__ import annotations

import sqlite3
from .storage import connect
from pathlib import Path

import pandas as pd

from .config import RuleConfig
from .excel_export import write_review_workbook
from .qa import QAResult


REMEDIATION_OUTPUTS = {
    "synthetic_payer_directory_listings.csv",
    "payer_listing_identity_results.csv",
    "field_source_precedence.csv",
    "provider_field_reference_values.csv",
    "payer_listing_field_comparisons.csv",
    "payer_directory_discrepancies.csv",
    "directory_remediation_risk_summary.csv",
}

REMEDIATION_TABLES = {
    "synthetic_payer_directory_listings",
    "payer_listing_identity_results",
    "field_source_precedence",
    "provider_field_reference_values",
    "payer_listing_field_comparisons",
    "payer_directory_discrepancies",
    "directory_remediation_risk_summary",
}


def write_outputs(
    result: QAResult,
    output_dir: Path,
    sqlite_path: Path,
    config: RuleConfig,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    result.clean_records.to_csv(output_dir / "normalized_provider_records.csv", index=False)
    result.exceptions.sort_values(["priority_rank", "issue_code"]).to_csv(
        output_dir / "provider_directory_exceptions.csv", index=False
    )
    result.duplicate_candidates.to_csv(output_dir / "duplicate_candidates.csv", index=False)
    result.summary.to_csv(output_dir / "quality_summary.csv", index=False)
    write_review_memo(result, output_dir / "operations_review_memo.md")
    write_review_workbook(
        result,
        config,
        output_dir / "provider_directory_review_pack.xlsx",
        remediation=result.remediation,
    )

    if result.remediation is not None:
        result.remediation.payer_listings.to_csv(
            output_dir / "synthetic_payer_directory_listings.csv", index=False
        )
        result.remediation.listing_identity_results.to_csv(
            output_dir / "payer_listing_identity_results.csv", index=False
        )
        result.remediation.field_source_precedence.to_csv(
            output_dir / "field_source_precedence.csv", index=False
        )
        result.remediation.reference_values.to_csv(
            output_dir / "provider_field_reference_values.csv", index=False
        )
        result.remediation.field_comparisons.to_csv(
            output_dir / "payer_listing_field_comparisons.csv", index=False
        )
        result.remediation.discrepancies.to_csv(
            output_dir / "payer_directory_discrepancies.csv", index=False
        )
        result.remediation.risk_summary.to_csv(
            output_dir / "directory_remediation_risk_summary.csv", index=False
        )
    else:
        for filename in REMEDIATION_OUTPUTS:
            (output_dir / filename).unlink(missing_ok=True)

    with connect(sqlite_path) as conn:
        result.clean_records.to_sql("normalized_provider_records", conn, if_exists="replace", index=False)
        result.exceptions.to_sql("provider_directory_exceptions", conn, if_exists="replace", index=False)
        result.duplicate_candidates.to_sql("duplicate_candidates", conn, if_exists="replace", index=False)
        result.summary.to_sql("quality_summary", conn, if_exists="replace", index=False)
        if result.remediation is not None:
            result.remediation.payer_listings.to_sql(
                "synthetic_payer_directory_listings", conn, if_exists="replace", index=False
            )
            result.remediation.listing_identity_results.to_sql(
                "payer_listing_identity_results", conn, if_exists="replace", index=False
            )
            result.remediation.field_source_precedence.to_sql(
                "field_source_precedence", conn, if_exists="replace", index=False
            )
            result.remediation.reference_values.to_sql(
                "provider_field_reference_values", conn, if_exists="replace", index=False
            )
            result.remediation.field_comparisons.to_sql(
                "payer_listing_field_comparisons", conn, if_exists="replace", index=False
            )
            result.remediation.discrepancies.to_sql(
                "payer_directory_discrepancies", conn, if_exists="replace", index=False
            )
            result.remediation.risk_summary.to_sql(
                "directory_remediation_risk_summary", conn, if_exists="replace", index=False
            )
        else:
            for table in REMEDIATION_TABLES:
                conn.execute(f"drop table if exists {table}")


def write_review_memo(result: QAResult, path: Path) -> None:
    summary = {row["metric"]: row["value"] for _, row in result.summary.iterrows()}
    issue_counts = (
        result.exceptions["issue_code"].value_counts().head(5).to_dict()
        if not result.exceptions.empty
        else {}
    )

    lines = [
        "# Provider Directory QA Operations Review",
        "",
        "## Summary",
        "",
        f"- Total records reviewed: {summary.get('total_records', 0)}",
        f"- Records with at least one issue: {summary.get('records_with_issues', 0)}",
        f"- Total issues found: {summary.get('total_issues', 0)}",
        f"- Record issue rate: {float(summary.get('issue_rate', 0)):.1%}",
        "",
        "## Top Issue Types",
        "",
    ]
    if issue_counts:
        for issue, count in issue_counts.items():
            lines.append(f"- `{issue}`: {count}")
    else:
        lines.append("- No issues found.")

    lines.extend(
        [
            "",
        "## Recommended Operations Follow-Up",
        "",
        "1. Resolve high-severity missing phone, NPI, specialty, and address issues first.",
        "2. Route possible duplicate provider/location records to a human review queue.",
        "3. Re-verify stale records before using them in patient-facing directories.",
        "4. Track recurring issue codes by source to identify upstream data quality problems.",
        "5. Use `review_status`, `assigned_to`, `recommended_action`, and `priority_rank` to manage cleanup work.",
        "",
        "## Notes",
            "",
            "This memo is generated from sample public-provider-style data. It is designed to show the workflow pattern, not to certify any real provider record.",
        ]
    )
    if result.remediation is not None:
        risk_counts = {
            row["risk_level"]: row["total_actionable_findings"]
            for _, row in result.remediation.risk_summary.iterrows()
        }
        unmatched_listings = result.remediation.listing_identity_results.loc[
            result.remediation.listing_identity_results["is_actionable"]
        ]
        lines.extend(
            [
                "",
                "## Payer Directory Verification",
                "",
                f"- Synthetic payer listings compared: {len(result.remediation.payer_listings)}",
                f"- Field-level discrepancies: {len(result.remediation.discrepancies)}",
                f"- Unmatched listing identities: {len(unmatched_listings)}",
                f"- High-risk discrepancies: {risk_counts.get('high', 0)}",
                f"- Medium-risk discrepancies: {risk_counts.get('medium', 0)}",
                f"- Low-risk discrepancies: {risk_counts.get('low', 0)}",
                "- These outputs identify review candidates only; they do not update source, normalized, or payer-listing records.",
            ]
        )
    path.write_text("\n".join(lines) + "\n")
