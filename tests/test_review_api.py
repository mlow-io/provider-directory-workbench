from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from provider_directory_truth_layer.pipeline import run_pipeline
from provider_directory_truth_layer.review_api import create_app


def review_client(tmp_path: Path) -> TestClient:
    repo = Path(__file__).resolve().parents[1]
    sqlite_path = tmp_path / "provider_directory_truth_layer.sqlite3"
    run_pipeline(
        input_csv=repo / "data/raw/sample_provider_directory.csv",
        config_path=repo / "config/qa_rules.yml",
        output_dir=tmp_path / "outputs",
        sqlite_path=sqlite_path,
        as_of=datetime(2026, 6, 26),
    )
    return TestClient(create_app(sqlite_path))


def case_id_for(client: TestClient, issue_code: str) -> str:
    response = client.get("/api/cases", params={"issue_code": issue_code})
    assert response.status_code == 200
    return response.json()["items"][0]["case_id"]


def test_batch_and_case_exports_are_derived_from_qa_sqlite(tmp_path: Path) -> None:
    client = review_client(tmp_path)

    batch = client.get("/api/batches/current")
    assert batch.status_code == 200
    assert batch.json()["record_count"] == 12
    assert batch.json()["exception_count"] == 11
    assert "synthetic" in batch.json()["data_notice"].lower()

    cases = client.get("/api/cases", params={"severity": "high", "sort": "provider"})
    assert cases.status_code == 200
    assert cases.json()["total"] >= 1
    assert all(item["severity"] == "high" for item in cases.json()["items"])

    filtered_export = client.get("/api/exports/cases.csv", params={"severity": "high"})
    assert filtered_export.status_code == 200
    assert "case_id,record_id" in filtered_export.text

    batch_export = client.get("/api/exports/batch.csv")
    assert batch_export.status_code == 200
    assert batch.json()["batch_id"] in batch_export.text


def test_transitions_require_reason_and_append_auditable_events(tmp_path: Path) -> None:
    client = review_client(tmp_path)
    case_id = case_id_for(client, "missing_required_field")

    rejected = client.post(
        f"/api/cases/{case_id}/transitions",
        json={"action": "assign", "assignee": "Avery", "reason": ""},
    )
    assert rejected.status_code == 422

    assigned = client.post(
        f"/api/cases/{case_id}/transitions",
        json={"action": "assign", "assignee": "Avery", "reason": "Route to field verification", "note": "Confirm against source."},
    )
    assert assigned.status_code == 200
    assert assigned.json()["case"]["review_status"] == "assigned"
    assert assigned.json()["case"]["assigned_to"] == "Avery"

    started = client.post(
        f"/api/cases/{case_id}/transitions",
        json={"action": "start_review", "reason": "Source owner confirmed review start"},
    )
    assert started.status_code == 200
    resolved = client.post(
        f"/api/cases/{case_id}/transitions",
        json={"action": "resolve", "reason": "Verified and queued for source correction"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["case"]["review_status"] == "resolved"

    detail = client.get(f"/api/cases/{case_id}")
    assert detail.status_code == 200
    assert [event["event_type"] for event in detail.json()["history"]] == ["assign", "start_review", "resolve"]
    assert detail.json()["notes"] == "Confirm against source."

    deferred_case_id = case_id_for(client, "stale_verification")
    deferred = client.post(
        f"/api/cases/{deferred_case_id}/transitions",
        json={"action": "defer", "reason": "Wait for scheduled source refresh"},
    )
    assert deferred.status_code == 200
    assert deferred.json()["case"]["review_status"] == "deferred"
    reopened = client.post(
        f"/api/cases/{deferred_case_id}/transitions",
        json={"action": "start_review", "reason": "Source refresh is available for review"},
    )
    assert reopened.status_code == 200
    assert reopened.json()["case"]["review_status"] == "in_review"


def test_duplicate_case_keeps_side_by_side_provenance_and_no_merge_warning(tmp_path: Path) -> None:
    client = review_client(tmp_path)
    case_id = case_id_for(client, "possible_duplicate_provider_location")

    detail = client.get(f"/api/cases/{case_id}")
    assert detail.status_code == 200
    duplicate = detail.json()["duplicate"]
    assert duplicate is not None
    assert len(duplicate["records"]) == 2
    assert "no automatic merge" in duplicate["warning"].lower()
