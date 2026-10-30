from datetime import datetime
from pathlib import Path

import pandas as pd

from provider_directory_truth_layer.pipeline import run_pipeline
from provider_directory_truth_layer.cli import build_parser


def test_payer_listings_are_opt_in_for_run_and_public_fetch_commands():
    parser = build_parser()

    assert parser.parse_args(["run"]).payer_listings is None
    assert parser.parse_args(["fetch-npi"]).payer_listings is None


def test_pipeline_writes_expected_outputs(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    result = run_pipeline(
        input_csv=repo / "data/raw/sample_provider_directory.csv",
        config_path=repo / "config/qa_rules.yml",
        output_dir=tmp_path / "outputs",
        sqlite_path=tmp_path / "provider_directory_truth_layer.sqlite3",
        as_of=datetime(2026, 6, 26),
    )

    assert len(result.clean_records) == 12
    assert not result.exceptions.empty
    assert "missing_required_field" in set(result.exceptions["issue_code"])
    assert "invalid_or_missing_phone" in set(result.exceptions["issue_code"])
    assert "possible_duplicate_provider_location" in set(result.exceptions["issue_code"])
    assert {"review_status", "assigned_to", "recommended_action", "priority_rank"}.issubset(
        result.exceptions.columns
    )
    assert (tmp_path / "outputs/provider_directory_exceptions.csv").exists()
    assert (tmp_path / "outputs/operations_review_memo.md").exists()
    assert (tmp_path / "outputs/provider_directory_review_pack.xlsx").exists()
    assert (tmp_path / "provider_directory_truth_layer.sqlite3").exists()
    assert result.remediation is None
    assert not (tmp_path / "outputs/payer_directory_discrepancies.csv").exists()


def test_summary_contains_issue_rate(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    result = run_pipeline(
        input_csv=repo / "data/raw/sample_provider_directory.csv",
        config_path=repo / "config/qa_rules.yml",
        output_dir=tmp_path / "outputs",
        sqlite_path=tmp_path / "provider_directory_truth_layer.sqlite3",
        as_of=datetime(2026, 6, 26),
    )
    metrics = set(result.summary["metric"])
    assert "total_records" in metrics
    assert "records_with_issues" in metrics
    assert "issue_rate" in metrics


def test_csv_and_payer_identifiers_preserve_blanks_zeroes_and_literal_na(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    providers = tmp_path / "providers.csv"
    payers = tmp_path / "payers.csv"
    pd.DataFrame([
        {"record_id": "0001", "npi": "", "provider_name": "NA", "zip": "02108"},
        {"record_id": "0002", "npi": "1234567890", "provider_name": "Clinic", "zip": "00501"},
    ]).to_csv(providers, index=False)
    pd.DataFrame([
        {"listing_id": "0003", "reference_provider_key": "npi:1234567890",
         "npi": "", "provider_name": "NA", "zip": "02108"},
    ]).to_csv(payers, index=False)
    result = run_pipeline(providers, repo / "config/qa_rules.yml", tmp_path / "outputs",
                          tmp_path / "test.sqlite3", payer_listings_csv=payers,
                          as_of=datetime(2026, 6, 26))

    assert result.clean_records["record_id"].tolist() == ["0001", "0002"]
    assert result.clean_records["npi"].tolist() == ["", "1234567890"]
    assert result.clean_records["zip"].tolist() == ["02108", "00501"]
    assert result.clean_records.loc[0, "provider_name"] == "NA"
    missing_npi = result.exceptions.loc[
        (result.exceptions["record_id"] == "0001")
        & (result.exceptions["field_name"] == "npi")
        & (result.exceptions["issue_code"] == "missing_required_field")
    ]
    assert len(missing_npi) == 1
    listing = result.remediation.payer_listings.iloc[0]
    assert listing["listing_id"] == "0003"
    assert listing["npi"] == ""
    assert listing["zip"] == "02108"
    assert listing["provider_name"] == "NA"
