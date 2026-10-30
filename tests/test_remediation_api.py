from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from provider_directory_truth_layer.pipeline import run_pipeline
from provider_directory_truth_layer.remediation_api import RemediationStore, create_remediation_app


def remediation_client(tmp_path: Path) -> tuple[TestClient, Path]:
    repo = Path(__file__).resolve().parents[1]
    sqlite_path = tmp_path / "provider_directory_truth_layer.sqlite3"
    run_pipeline(
        input_csv=repo / "data/raw/sample_provider_directory.csv",
        config_path=repo / "config/qa_rules.yml",
        output_dir=tmp_path / "outputs",
        sqlite_path=sqlite_path,
        payer_listings_csv=repo / "data/raw/synthetic_payer_directory_listings.csv",
        as_of=datetime(2026, 6, 26),
    )
    return TestClient(create_remediation_app(sqlite_path)), sqlite_path


def cases(client: TestClient) -> list[dict[str, object]]:
    response = client.get("/api/remediation/cases")
    assert response.status_code == 200
    return response.json()["items"]


def transition(client: TestClient, case_id: str, action: str, **extra: str) -> dict[str, object]:
    response = client.post(
        f"/api/remediation/cases/{case_id}/transitions",
        json={"action": action, "actor": "Morgan Reviewer", "reason": f"{action} with documented evidence", **extra},
    )
    assert response.status_code == 200, response.text
    return response.json()


def evidence_for(client: TestClient, case_id: str) -> dict[str, object]:
    response = client.get(f"/api/remediation/cases/{case_id}")
    assert response.status_code == 200
    return response.json()["evidence"]["values"]


def case_for(client: TestClient, listing_id: str, field_name: str) -> dict[str, object]:
    response = client.get(
        "/api/remediation/cases",
        params={"listing_id": listing_id, "field_name": field_name},
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1
    return response.json()["items"][0]


def test_case_ids_are_deterministic_and_one_case_exists_per_field_discrepancy(tmp_path: Path) -> None:
    first, first_sqlite = remediation_client(tmp_path / "first")
    second, _ = remediation_client(tmp_path / "second")

    first_items = cases(first)
    second_items = cases(second)
    assert len(first_items) == 6
    assert [(item["case_id"], item["listing_id"], item["reference_provider_key"], item["field_name"]) for item in first_items] == [
        (item["case_id"], item["listing_id"], item["reference_provider_key"], item["field_name"])
        for item in second_items
    ]
    assert len({item["case_id"] for item in first_items}) == 6
    assert all(item["listing_id"] != "PAYER-00008" for item in first_items)

    with sqlite3.connect(first_sqlite) as conn:
        discrepancy_count = conn.execute("select count(*) from payer_directory_discrepancies").fetchone()[0]
        workflow_count = conn.execute("select count(*) from remediation_case").fetchone()[0]
    assert discrepancy_count == workflow_count == 6
    assert RemediationStore.case_id("PAYER-00006", "npi:1034567899", "npi") in {
        item["case_id"] for item in first_items
    }
    filtered = first.get(
        "/api/remediation/cases",
        params={"status": "new", "risk_level": "high", "listing_id": "PAYER-00006", "field_name": "npi"},
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["reference_provider_key"] == "npi:1034567899"


def test_transition_requirements_and_all_allowed_state_paths(tmp_path: Path) -> None:
    client, _ = remediation_client(tmp_path)
    first_case = case_for(client, "PAYER-00002", "state")
    second_case = case_for(client, "PAYER-00003", "status")
    first_id = str(first_case["case_id"])
    second_id = str(second_case["case_id"])

    missing_reason = client.post(
        f"/api/remediation/cases/{first_id}/transitions",
        json={"action": "triage", "actor": "Morgan", "reason": "   "},
    )
    assert missing_reason.status_code == 422
    missing_actor = client.post(
        f"/api/remediation/cases/{first_id}/transitions",
        json={"action": "triage", "actor": "   ", "reason": "Need an accountable reviewer"},
    )
    assert missing_actor.status_code == 422
    invalid_approval = client.post(
        f"/api/remediation/cases/{first_id}/transitions",
        json={"action": "approve", "actor": "Morgan", "reason": "Skipping triage is invalid", "proposed_correction_value": "x"},
    )
    assert invalid_approval.status_code == 409

    transition(client, first_id, "triage")
    missing_proposal = client.post(
        f"/api/remediation/cases/{first_id}/transitions",
        json={"action": "approve", "actor": "Morgan", "reason": "Reviewed evidence"},
    )
    assert missing_proposal.status_code == 422
    first_evidence = evidence_for(client, first_id)
    approval = transition(
        client,
        first_id,
        "approve",
        proposed_correction_value=str(first_evidence["reference_value"]),
    )
    approval_event = approval["event"]
    assert approval_event["original_payer_value"] == first_evidence["listing_value"]
    assert approval_event["reference_value"] == first_evidence["reference_value"]
    assert approval_event["proposed_correction_value"] == first_evidence["reference_value"]
    assert approval["case"]["active_proposed_correction_value"] == first_evidence["reference_value"]
    missing_submission_reference = client.post(
        f"/api/remediation/cases/{first_id}/transitions",
        json={"action": "submit", "actor": "Morgan", "reason": "Ready for payer submission"},
    )
    assert missing_submission_reference.status_code == 422
    submitted = transition(client, first_id, "submit", submission_reference="PAYER-TICKET-101")
    assert submitted["event"]["submission_reference"] == "PAYER-TICKET-101"
    assert submitted["event"]["submitted_at"]
    missing_verification = client.post(
        f"/api/remediation/cases/{first_id}/transitions",
        json={"action": "verify", "actor": "Morgan", "reason": "Checking payer response"},
    )
    assert missing_verification.status_code == 422
    verified = transition(
        client,
        first_id,
        "verify",
        observed_payer_value=str(first_evidence["reference_value"]).lower(),
        verification_evidence_note="Payer response now matches the documented reference.",
    )
    assert verified["case"]["status"] == "verified"
    assert verified["event"]["event_type"] == "verify"
    assert verified["event"]["observed_payer_value"] == str(first_evidence["reference_value"]).lower()

    # The deferred and failed-verification paths are deliberately separate from successful verification.
    transition(client, second_id, "triage")
    transition(client, second_id, "defer")
    transition(client, second_id, "triage")
    transition(client, second_id, "approve", proposed_correction_value="hold")
    invalid_submit = client.post(
        f"/api/remediation/cases/{second_id}/transitions",
        json={"action": "defer", "actor": "Morgan", "reason": "Approved cases cannot be deferred"},
    )
    assert invalid_submit.status_code == 409
    transition(client, second_id, "submit", submission_reference="PAYER-TICKET-102")
    reopened = transition(
        client,
        second_id,
        "verify",
        observed_payer_value="pending",
        verification_evidence_note="Payer portal still displays a mismatching value.",
    )
    assert reopened["case"]["status"] == "reopened"
    assert reopened["event"]["event_type"] == "reopen"
    assert reopened["event"]["observed_payer_value"] == "pending"
    transition(client, second_id, "triage")

    history = client.get(f"/api/remediation/cases/{second_id}/history")
    assert history.status_code == 200
    events = history.json()
    assert [event["event_type"] for event in events] == [
        "triage",
        "defer",
        "triage",
        "approve",
        "submit",
        "reopen",
        "triage",
    ]
    assert [event["event_id"] for event in events] == sorted(event["event_id"] for event in events)


def test_verification_uses_the_active_approved_value_not_the_phase_one_reference(tmp_path: Path) -> None:
    client, _ = remediation_client(tmp_path)
    approved_case = case_for(client, "PAYER-00002", "state")
    approved_case_id = str(approved_case["case_id"])
    approved_evidence = evidence_for(client, approved_case_id)
    assert approved_evidence["reference_value"] == "TN"

    transition(client, approved_case_id, "triage")
    transition(client, approved_case_id, "approve", proposed_correction_value="GA")
    transition(client, approved_case_id, "submit", submission_reference="PAYER-TICKET-PROPOSAL")
    verified = transition(
        client,
        approved_case_id,
        "verify",
        observed_payer_value="ga",
        verification_evidence_note="The payer now displays the human-approved state value.",
    )
    assert verified["case"]["status"] == "verified"
    assert verified["case"]["active_proposed_correction_value"] == "GA"

    reference_case = case_for(client, "PAYER-00003", "status")
    reference_case_id = str(reference_case["case_id"])
    reference_evidence = evidence_for(client, reference_case_id)
    assert reference_evidence["reference_value"] != "hold"
    transition(client, reference_case_id, "triage")
    transition(client, reference_case_id, "approve", proposed_correction_value="hold")
    transition(client, reference_case_id, "submit", submission_reference="PAYER-TICKET-REFERENCE")
    reopened = transition(
        client,
        reference_case_id,
        "verify",
        observed_payer_value=str(reference_evidence["reference_value"]),
        verification_evidence_note="The payer reflects the old reference rather than the approved proposal.",
    )
    assert reopened["case"]["status"] == "reopened"
    assert reopened["event"]["event_type"] == "reopen"


def test_reapproval_updates_the_projection_and_preserves_every_proposal_event(tmp_path: Path) -> None:
    client, _ = remediation_client(tmp_path)
    case = case_for(client, "PAYER-00004", "accepting_new_patients")
    case_id = str(case["case_id"])

    transition(client, case_id, "triage")
    transition(client, case_id, "approve", proposed_correction_value="no")
    transition(client, case_id, "submit", submission_reference="PAYER-TICKET-FIRST")
    transition(
        client,
        case_id,
        "verify",
        observed_payer_value="yes",
        verification_evidence_note="The first approved proposal was not observed.",
    )
    transition(client, case_id, "triage")
    reapproval = transition(client, case_id, "approve", proposed_correction_value="yes")
    assert reapproval["case"]["active_proposed_correction_value"] == "yes"

    detail = client.get(f"/api/remediation/cases/{case_id}")
    assert detail.status_code == 200
    assert [event["proposed_correction_value"] for event in detail.json()["history"] if event["event_type"] == "approve"] == [
        "no",
        "yes",
    ]
    assert detail.json()["case"]["active_proposed_correction_value"] == "yes"


def test_workflow_does_not_mutate_phase_one_evidence_or_records_and_reruns_preserve_history(tmp_path: Path) -> None:
    client, sqlite_path = remediation_client(tmp_path)
    case = cases(client)[0]
    case_id = str(case["case_id"])
    repo = Path(__file__).resolve().parents[1]
    raw_source_before = (repo / "data/raw/sample_provider_directory.csv").read_bytes()
    payer_source_before = (repo / "data/raw/synthetic_payer_directory_listings.csv").read_bytes()
    with sqlite3.connect(sqlite_path) as conn:
        before = {
            table: conn.execute(f"select * from {table} order by rowid").fetchall()
            for table in (
                "payer_directory_discrepancies",
                "synthetic_payer_directory_listings",
                "normalized_provider_records",
            )
        }

    transition(client, case_id, "triage")
    transition(client, case_id, "defer")
    original_history = client.get(f"/api/remediation/cases/{case_id}/history").json()

    with sqlite3.connect(sqlite_path) as conn:
        after_transitions = {
            table: conn.execute(f"select * from {table} order by rowid").fetchall()
            for table in before
        }
    assert after_transitions == before
    assert (repo / "data/raw/sample_provider_directory.csv").read_bytes() == raw_source_before
    assert (repo / "data/raw/synthetic_payer_directory_listings.csv").read_bytes() == payer_source_before

    snapshot = evidence_for(client, case_id)
    with sqlite3.connect(sqlite_path) as conn:
        conn.execute(
            "update payer_directory_discrepancies set listing_value = 'CHANGED' where listing_id = ? and provider_key = ? and field_name = ?",
            (case["listing_id"], case["reference_provider_key"], case["field_name"]),
        )
        conn.commit()
    changed_evidence = evidence_for(client, case_id)
    assert changed_evidence == snapshot

    store = RemediationStore(sqlite_path)
    store.initialize()
    store.initialize()
    with sqlite3.connect(sqlite_path) as conn:
        conn.execute(
            "delete from payer_directory_discrepancies where listing_id = ? and provider_key = ? and field_name = ?",
            (case["listing_id"], case["reference_provider_key"], case["field_name"]),
        )
        conn.commit()
    assert evidence_for(client, case_id) == snapshot

    run_pipeline(
        input_csv=repo / "data/raw/sample_provider_directory.csv",
        config_path=repo / "config/qa_rules.yml",
        output_dir=tmp_path / "outputs",
        sqlite_path=sqlite_path,
        as_of=datetime(2026, 6, 26),
    )
    rerun_client = TestClient(create_remediation_app(sqlite_path))
    rerun_case = rerun_client.get(f"/api/remediation/cases/{case_id}")
    assert rerun_case.status_code == 200
    assert rerun_case.json()["case"]["status"] == "deferred"
    assert rerun_case.json()["history"] == original_history
    assert rerun_case.json()["evidence"]["values"] == snapshot
    assert len(cases(rerun_client)) == 6

    store.initialize()
    store.initialize()
    with sqlite3.connect(sqlite_path) as conn:
        tables = {row[0] for row in conn.execute("select name from sqlite_master where type = 'table'")}
        assert "payer_directory_discrepancies" not in tables
        assert conn.execute("select count(*) from remediation_case").fetchone()[0] == 6
        assert conn.execute("select count(*) from remediation_event where case_id = ?", (case_id,)).fetchone()[0] == 2


def test_remediation_api_is_unavailable_without_explicit_payer_evidence(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    sqlite_path = tmp_path / "qa_only.sqlite3"
    run_pipeline(
        input_csv=repo / "data/raw/sample_provider_directory.csv",
        config_path=repo / "config/qa_rules.yml",
        output_dir=tmp_path / "outputs",
        sqlite_path=sqlite_path,
        as_of=datetime(2026, 6, 26),
    )
    response = TestClient(create_remediation_app(sqlite_path)).get("/api/remediation/cases")
    assert response.status_code == 503
    assert "payer" in response.json()["detail"].lower()


def test_legacy_cases_remain_inspectable_after_snapshot_migration_without_phase_one_tables(
    tmp_path: Path,
) -> None:
    sqlite_path = tmp_path / "legacy_remediation.sqlite3"
    case_id = "remediation_legacy"
    with sqlite3.connect(sqlite_path) as conn:
        conn.executescript(
            """
            create table remediation_case (
                case_id text primary key,
                listing_id text not null,
                reference_provider_key text not null,
                field_name text not null,
                workflow_status text not null,
                initial_risk_level text not null,
                created_at text not null,
                updated_at text not null,
                unique (listing_id, reference_provider_key, field_name)
            );
            create table remediation_event (
                event_id integer primary key autoincrement,
                case_id text not null,
                event_type text not null,
                from_status text,
                to_status text not null,
                actor text not null,
                reason text not null,
                proposed_correction_value text,
                original_payer_value text,
                reference_value text,
                submission_reference text,
                submitted_at text,
                observed_payer_value text,
                verification_evidence_note text,
                occurred_at text not null
            );
            """
        )
        conn.execute(
            """
            insert into remediation_case
            (case_id, listing_id, reference_provider_key, field_name, workflow_status,
             initial_risk_level, created_at, updated_at)
            values (?, 'PAYER-LEGACY', 'npi:1234567890', 'phone', 'pending_verification', 'high', 'now', 'now')
            """,
            (case_id,),
        )
        conn.execute(
            """
            insert into remediation_event
            (case_id, event_type, from_status, to_status, actor, reason,
             proposed_correction_value, occurred_at)
            values (?, 'approve', 'triaged', 'approved', 'Morgan', 'Documented approval', '615-555-0111', 'now')
            """,
            (case_id,),
        )

    detail = TestClient(create_remediation_app(sqlite_path)).get(f"/api/remediation/cases/{case_id}")
    assert detail.status_code == 200
    assert detail.json()["case"]["active_proposed_correction_value"] == "615-555-0111"
    assert detail.json()["evidence"]["values"]["snapshot_status"] == "legacy_evidence_unavailable_when_snapshot_migrated"
    assert [event["event_type"] for event in detail.json()["history"]] == ["approve"]
