from __future__ import annotations

from pathlib import Path

import pandas as pd
import pandas.testing as pdt
import pytest

from provider_directory_truth_layer.config import load_rule_config
from provider_directory_truth_layer.normalize import normalize_provider_frame
from provider_directory_truth_layer.remediation import run_remediation_checks


def remediation_result():
    repo = Path(__file__).resolve().parents[1]
    config = load_rule_config(repo / "config/qa_rules.yml")
    records = normalize_provider_frame(pd.read_csv(repo / "data/raw/sample_provider_directory.csv"))
    listings = pd.read_csv(repo / "data/raw/synthetic_payer_directory_listings.csv")
    return records, listings, run_remediation_checks(records, listings, config.remediation)


def test_field_source_precedence_selects_configured_source_per_field():
    _, _, result = remediation_result()

    sarah_phone = result.reference_values.loc[
        (result.reference_values["provider_key"] == "npi:1234567890")
        & (result.reference_values["field_name"] == "phone")
    ].iloc[0]
    sarah_accepting = result.reference_values.loc[
        (result.reference_values["provider_key"] == "npi:1234567890")
        & (result.reference_values["field_name"] == "accepting_new_patients")
    ].iloc[0]

    assert sarah_phone["reference_source"] == "NPPES-like export"
    assert sarah_phone["reference_record_id"] == "REC-00001"
    assert sarah_phone["precedence_rank"] == 3
    assert sarah_accepting["reference_source"] == "payer directory"
    assert sarah_accepting["precedence_rank"] == 3
    keisha_phone = result.reference_values.loc[
        (result.reference_values["provider_key"] == "npi:9234567898")
        & (result.reference_values["field_name"] == "phone")
    ].iloc[0]
    assert keisha_phone["reference_source"] == "clinic directory"
    assert keisha_phone["precedence_rank"] == 1


def test_remediation_detects_expected_field_discrepancies_and_risks():
    _, _, result = remediation_result()

    actual = {
        (row.listing_id, row.field_name): row.risk_level
        for row in result.discrepancies.itertuples(index=False)
    }
    assert actual == {
        ("PAYER-00001", "phone"): "high",
        ("PAYER-00002", "state"): "high",
        ("PAYER-00003", "status"): "high",
        ("PAYER-00004", "accepting_new_patients"): "medium",
        ("PAYER-00005", "phone"): "high",
        ("PAYER-00006", "npi"): "high",
    }

    equivalent_address = result.field_comparisons.loc[
        (result.field_comparisons["listing_id"] == "PAYER-00005")
        & (result.field_comparisons["field_name"] == "address")
    ].iloc[0]
    assert equivalent_address["comparison_status"] == "match"

    unavailable_phone = result.field_comparisons.loc[
        (result.field_comparisons["listing_id"] == "PAYER-00007")
        & (result.field_comparisons["field_name"] == "phone")
    ].iloc[0]
    assert unavailable_phone["comparison_status"] == "reference_unavailable"
    assert unavailable_phone["risk_level"] == "unverified"
    assert not unavailable_phone["is_discrepancy"]


def test_wrong_published_npi_uses_crosswalk_and_is_high_risk():
    _, _, result = remediation_result()

    wrong_npi = result.field_comparisons.loc[
        (result.field_comparisons["listing_id"] == "PAYER-00006")
        & (result.field_comparisons["field_name"] == "npi")
    ].iloc[0]

    assert wrong_npi["provider_key"] == "npi:1034567899"
    assert wrong_npi["listing_value"] == "1034567890"
    assert wrong_npi["reference_value"] == "1034567899"
    assert wrong_npi["comparison_status"] == "discrepancy"
    assert wrong_npi["risk_level"] == "high"


def test_unmatched_listing_is_reported_once_at_listing_identity_level():
    _, _, result = remediation_result()

    identity = result.listing_identity_results.loc[
        result.listing_identity_results["listing_id"] == "PAYER-00008"
    ].iloc[0]
    assert identity["identity_status"] == "unmatched_reference_provider"
    assert identity["is_actionable"]
    assert identity["risk_level"] == "high"
    assert "PAYER-00008" not in set(result.field_comparisons["listing_id"])


def test_remediation_treats_a_missing_payer_value_as_an_actionable_discrepancy():
    records, listings, _ = remediation_result()
    listings.loc[listings["listing_id"] == "PAYER-00001", "phone"] = ""
    config = load_rule_config(Path(__file__).resolve().parents[1] / "config/qa_rules.yml")

    result = run_remediation_checks(records, listings, config.remediation)
    missing_phone = result.field_comparisons.loc[
        (result.field_comparisons["listing_id"] == "PAYER-00001")
        & (result.field_comparisons["field_name"] == "phone")
    ].iloc[0]

    assert missing_phone["comparison_status"] == "listing_missing"
    assert missing_phone["is_discrepancy"]
    assert missing_phone["risk_level"] == "high"


def test_remediation_is_deterministic_and_does_not_mutate_inputs():
    records, listings, first = remediation_result()
    original_records = records.copy(deep=True)
    original_listings = listings.copy(deep=True)
    config = load_rule_config(Path(__file__).resolve().parents[1] / "config/qa_rules.yml")
    second = run_remediation_checks(records, listings, config.remediation)

    pdt.assert_frame_equal(records, original_records)
    pdt.assert_frame_equal(listings, original_listings)
    for name in (
        "payer_listings",
        "listing_identity_results",
        "field_source_precedence",
        "reference_values",
        "field_comparisons",
        "discrepancies",
        "risk_summary",
    ):
        pdt.assert_frame_equal(getattr(first, name), getattr(second, name))


def test_remediation_config_rejects_missing_field_precedence(tmp_path):
    config_path = tmp_path / "rules.yml"
    config_path.write_text(
        """
remediation:
  comparison_fields: [phone]
  field_source_precedence:
    phone: []
  risk_by_field:
    phone: high
"""
    )

    with pytest.raises(ValueError, match="Field source precedence is required"):
        load_rule_config(config_path)
