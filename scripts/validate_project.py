from __future__ import annotations

import csv
import os
import sqlite3
import sys
from pathlib import Path


REQUIRED_OUTPUTS = [
    Path("exports/normalized_provider_records.csv"),
    Path("exports/provider_directory_exceptions.csv"),
    Path("exports/duplicate_candidates.csv"),
    Path("exports/quality_summary.csv"),
    Path("exports/operations_review_memo.md"),
    Path("exports/provider_directory_review_pack.xlsx"),
    Path("data/processed/provider_directory_truth_layer.sqlite3"),
]

REMEDIATION_OUTPUTS = [
    Path("exports/synthetic_payer_directory_listings.csv"),
    Path("exports/payer_listing_identity_results.csv"),
    Path("exports/field_source_precedence.csv"),
    Path("exports/provider_field_reference_values.csv"),
    Path("exports/payer_listing_field_comparisons.csv"),
    Path("exports/payer_directory_discrepancies.csv"),
    Path("exports/directory_remediation_risk_summary.csv"),
]

REQUIRED_TABLES = {
    "normalized_provider_records",
    "provider_directory_exceptions",
    "duplicate_candidates",
    "quality_summary",
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


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"[FAIL] {message}")


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def main() -> None:
    root = Path(os.environ["PDTL_ROOT"]).resolve()
    def owned(path):
        return root / ("directory.sqlite3" if str(path).endswith(".sqlite3") else "exports/" + path.name)
    global REQUIRED_OUTPUTS, REMEDIATION_OUTPUTS
    REQUIRED_OUTPUTS = [owned(p) for p in REQUIRED_OUTPUTS]
    REMEDIATION_OUTPUTS = [owned(p) for p in REMEDIATION_OUTPUTS]
    public_mode = "--public" in sys.argv
    required_outputs = REQUIRED_OUTPUTS if public_mode else REQUIRED_OUTPUTS + REMEDIATION_OUTPUTS
    for path in required_outputs:
        require(path.exists(), f"Missing expected output: {path}")
        require(path.stat().st_size > 0, f"Output is empty: {path}")

    exceptions = read_csv_rows(root / Path("exports/provider_directory_exceptions.csv"))
    duplicate_candidates = read_csv_rows(root / Path("exports/duplicate_candidates.csv"))
    summary = read_csv_rows(root / Path("exports/quality_summary.csv"))

    issue_codes = {row["issue_code"] for row in exceptions}
    require(exceptions, "Expected at least one exception row")
    require(
        {"review_status", "assigned_to", "recommended_action", "priority_rank"}.issubset(
            exceptions[0].keys()
        ),
        "Expected review workflow fields in exception report",
    )

    if public_mode:
        require((root / "npi_registry_sample_nashville.csv").exists(), "Missing NPI sample CSV")
        normalized = read_csv_rows(root / Path("exports/normalized_provider_records.csv"))
        require(len(normalized) > 0, "Expected public NPI normalized records")
        require(
            not any(path.exists() for path in REMEDIATION_OUTPUTS),
            "Public NPI run must not emit payer-listing remediation outputs",
        )
    else:
        require("missing_required_field" in issue_codes, "Expected missing_required_field issue")
        require("possible_duplicate_provider_location" in issue_codes, "Expected duplicate issue")
        require(len(duplicate_candidates) >= 1, "Expected at least one duplicate candidate")

        summary_metrics = {row["metric"]: row["value"] for row in summary}
        require(summary_metrics.get("total_records") in {"12", "12.0"}, "Expected 12 sample records")
        require(
            summary_metrics.get("total_issues") in {"11", "11.0"},
            "Expected 11 sample issues",
        )
        field_precedence = read_csv_rows(root / Path("exports/field_source_precedence.csv"))
        identity_results = read_csv_rows(root / Path("exports/payer_listing_identity_results.csv"))
        comparisons = read_csv_rows(root / Path("exports/payer_listing_field_comparisons.csv"))
        discrepancies = read_csv_rows(root / Path("exports/payer_directory_discrepancies.csv"))
        risk_summary = read_csv_rows(root / Path("exports/directory_remediation_risk_summary.csv"))
        require(field_precedence, "Expected configured field-source precedence rows")
        require(comparisons, "Expected payer-listing field comparison rows")
        require(
            {"comparison_status", "is_discrepancy", "risk_level", "risk_reason"}.issubset(
                comparisons[0].keys()
            ),
            "Expected comparison and risk fields in payer-listing evidence",
        )
        require(
            {"high", "medium", "low"}.issubset({row["risk_level"] for row in risk_summary}),
            "Expected high, medium, and low remediation risk summary rows",
        )
        require(len(discrepancies) == 6, "Expected six deterministic field discrepancies")
        require(
            {"npi", "phone", "state", "status", "accepting_new_patients"}.issubset(
                {row["field_name"] for row in discrepancies}
            ),
            "Expected sample discrepancies across configured directory fields",
        )
        require(
            len([row for row in identity_results if row["is_actionable"] == "True"]) == 1,
            "Expected one unmatched payer-listing identity",
        )

    sqlite_path = root / "directory.sqlite3"
    with sqlite3.connect(sqlite_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "select name from sqlite_master where type = 'table'"
            ).fetchall()
        }
    required_tables = REQUIRED_TABLES if public_mode else REQUIRED_TABLES | REMEDIATION_TABLES
    missing = required_tables - tables
    require(not missing, f"Missing SQLite tables: {', '.join(sorted(missing))}")
    if public_mode:
        require(
            not (REMEDIATION_TABLES & tables),
            "Public NPI run must not retain payer-listing remediation tables",
        )

    print("[OK] Provider Directory Truth Layer validation passed")
    print("[OK] Outputs present and exception report populated")
    print("[OK] SQLite review database contains expected tables")


if __name__ == "__main__":
    main()
