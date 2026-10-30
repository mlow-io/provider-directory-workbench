"""N2 source-asserted participation over fixture-owned SQLite and artifacts."""

import csv
import hashlib
import io
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from provider_directory_truth_layer.intake_api import create_workbench
from provider_directory_truth_layer.intake_store import Conflict, IntakeStore, SCHEMA
from provider_directory_truth_layer.recurring import MIGRATION_3


SOURCE = "payer:synthetic-roster"
SCOPE = {"dataset": "participation", "network_codes": ["CEDAR", "PINE"]}
FIELDS = ["record_id", "npi", "provider_name", "address", "city", "state", "zip", "phone",
          "location_id", "network_code", "organization_code", "participation_status",
          "effective_date", "end_date"]


@pytest.fixture
def store(tmp_path):
    return IntakeStore(tmp_path / "intake.sqlite3", tmp_path / "runtime")


def roster_row(network="CEDAR", location="NORTH", record_id="LIST-1", **changes):
    return {
        "record_id": record_id, "npi": "1000000001", "provider_name": "Synthetic Provider",
        "address": "10 Fiction St", "city": "Example", "state": "TN", "zip": "01234",
        "phone": "5550100000", "location_id": location, "network_code": network,
        "organization_code": "CLINIC", "participation_status": "listed",
        "effective_date": "2026-01-01", "end_date": "", **changes,
    }


def csv_payload(rows):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode()


def receive(store, rows, scope=SCOPE):
    return store.receive(csv_payload(rows), "synthetic-network.csv", source=SOURCE,
                         metadata={"scope": scope, "completeness": "bounded", "as_of": "2026-02-01"})


def accept(store, receipt):
    return store.commit(receipt["id"], {"actor": "operator", "reason": "Reviewed source assertion",
                                        "policy": "valid_rows", "expected_attempt": receipt["attempt_id"]})


def catalog_and_bindings(store):
    payer = store.create_catalog("organizations", {"label": "Synthetic Payer", "kind": "payer",
                                                  "actor": "operator", "reason": "Fixture"})
    clinic = store.create_catalog("organizations", {"label": "Synthetic Clinic", "kind": "clinic",
                                                   "actor": "operator", "reason": "Fixture"})
    cedar = store.create_catalog("networks", {"label": "CEDAR", "payer_organization_id": payer["id"],
                                               "actor": "operator", "reason": "Fixture"})
    pine = store.create_catalog("networks", {"label": "PINE", "payer_organization_id": payer["id"],
                                              "actor": "operator", "reason": "Fixture"})
    north = store.create_catalog("locations", {"label": "NORTH", "organization_id": clinic["id"],
                                               "actor": "operator", "reason": "Fixture"})
    south = store.create_catalog("locations", {"label": "SOUTH", "organization_id": clinic["id"],
                                               "actor": "operator", "reason": "Fixture"})
    targets = {"network": {"CEDAR": cedar, "PINE": pine},
               "location": {"NORTH": north, "SOUTH": south},
               "organization": {"CLINIC": clinic}}
    bindings = {}
    for kind, values in targets.items():
        bindings[kind] = {}
        for code, target in values.items():
            binding = store.bind_source({"source": SOURCE, "kind": kind, "source_key": code,
                                         "target_id": target["id"], "actor": "operator",
                                         "reason": "Reviewed source code"})
            bindings[kind][code] = binding["id"]
    return {"payer": payer, "clinic": clinic, "cedar": cedar, "pine": pine,
            "north": north, "south": south}, bindings


def mapped(store, receipt, bindings, **settings):
    return store.mapping(receipt["id"], {"mapping": {field: field for field in FIELDS},
                                         "roster_kind": "network", "bindings": bindings, **settings})


def test_catalog_ids_and_binding_revisions_are_explicit(store):
    catalog, bindings = catalog_and_bindings(store)
    same_label = store.create_catalog("networks", {"label": "CEDAR", "actor": "operator", "reason": "Distinct fixture"})
    assert same_label["id"] != catalog["cedar"]["id"]
    assert same_label["payer_organization_id"] is None
    with pytest.raises(ValueError, match="payer"):
        store.create_catalog("networks", {"label": "Invalid owner", "payer_organization_id": catalog["clinic"]["id"],
                                          "actor": "operator", "reason": "Invalid fixture"})
    assert len(store.catalog()["networks"]) == 3
    with pytest.raises((ValueError, Conflict)):
        store.bind_source({"source": SOURCE, "kind": "network", "source_key": "CEDAR",
                           "target_id": same_label["id"], "actor": "operator", "reason": "Missing expected revision"})
    revised = store.bind_source({"source": SOURCE, "kind": "network", "source_key": "CEDAR",
                                 "target_id": same_label["id"], "expected_binding_id": bindings["network"]["CEDAR"],
                                 "actor": "operator", "reason": "Source confirmed changed network"})
    assert revised["id"] != bindings["network"]["CEDAR"]
    assert revised["revision"] == 2
    assert revised["previous_id"] == bindings["network"]["CEDAR"]
    assert any(item["id"] == bindings["network"]["CEDAR"] for item in store.catalog()["bindings"])
    with pytest.raises((ValueError, Conflict)):
        store.bind_source({"source": SOURCE, "kind": "network", "source_key": "CEDAR",
                           "target_id": catalog["pine"]["id"],
                           "expected_binding_id": bindings["network"]["CEDAR"],
                           "actor": "operator", "reason": "Stale edit"})
    client = TestClient(create_workbench(store.path, store.root))
    response = client.post("/api/catalog/bindings", json={
        "source": SOURCE, "kind": "network", "source_key": "CEDAR",
        "target_id": catalog["pine"]["id"],
        "expected_binding_id": bindings["network"]["CEDAR"],
        "actor": "operator", "reason": "Stale HTTP edit",
    })
    assert response.status_code == 409
    with store.db() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE identity_binding SET source_key='REWRITTEN' WHERE id=?", (bindings["network"]["CEDAR"],))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM identity_binding WHERE id=?", (bindings["network"]["CEDAR"],))


def test_three_participation_scopes_are_distinct_and_source_asserted(store):
    catalog, bindings = catalog_and_bindings(store)
    receipt = receive(store, [roster_row(), roster_row("CEDAR", "SOUTH"), roster_row("PINE", "NORTH")])
    preview = mapped(store, receipt, bindings)
    assert preview["state"] == "preview_ready"
    assert preview["preview"]["valid_count"] == 3
    accepted = accept(store, preview)
    assert len(accepted["observations"]) == len(accepted["linked_cases"]) == 3
    assert all(case["kind"] == "qa" and case["field_name"] == "participation"
               for case in accepted["linked_cases"])
    assert all(case["status"] == "new" for case in accepted["linked_cases"])
    scopes = set()
    with store.db() as conn:
        rows = conn.execute("""SELECT p.network_id,p.practice_location_id,p.organization_id,p.listed_status,
                                      p.raw_labels,o.locator,o.human_verified_at,c.id
                               FROM participation_observation p
                               JOIN observation o ON o.id=p.observation_id
                               JOIN work_evidence e ON e.observation_id=o.id
                               JOIN work_case c ON c.id=e.case_id""").fetchall()
        assert len(rows) == 3
        for row in rows:
            scopes.add((row["network_id"], row["practice_location_id"]))
            assert row["organization_id"] == catalog["clinic"]["id"]
            assert row["listed_status"] == "listed"
            assert row["human_verified_at"] is None
            assert row["locator"].startswith("row:")
            assert "CEDAR" in row["raw_labels"] or "PINE" in row["raw_labels"]
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert scopes == {(catalog["cedar"]["id"], catalog["north"]["id"]),
                      (catalog["cedar"]["id"], catalog["south"]["id"]),
                      (catalog["pine"]["id"], catalog["north"]["id"])}


def test_unknown_bindings_bad_dates_and_fixed_network_conflict_quarantine(store):
    catalog, bindings = catalog_and_bindings(store)
    rows = [roster_row(network="UNKNOWN", record_id="U-NET"),
            roster_row(location="UNKNOWN", record_id="U-LOC"),
            roster_row(organization_code="UNKNOWN", record_id="U-ORG"),
            roster_row(effective_date="not-date", record_id="BAD-DATE"),
            roster_row(effective_date="2026-05-01", end_date="2026-04-01", record_id="BAD-RANGE"),
            roster_row(network="PINE", record_id="CONFLICT")]
    receipt = receive(store, rows)
    preview = mapped(store, receipt, bindings, fixed_network_binding_id=bindings["network"]["CEDAR"])
    assert preview["preview"]["quarantined_count"] == len(rows)
    assert preview["preview"]["valid_count"] == 0
    assert all(item["original"] for item in preview["preview"]["rows"])
    assert any("network" in str(item["problems"]).lower() for item in preview["preview"]["rows"])
    with pytest.raises(ValueError):
        accept(store, preview)
    assert (store.artifacts / preview["artifact_sha"]).read_bytes() == csv_payload(rows)


def test_known_invalid_participation_blocks_baseline_but_unbound_row_does_not(store):
    _, bindings = catalog_and_bindings(store)
    first = receive(store, [roster_row(), roster_row("CEDAR", "SOUTH"), roster_row("PINE", "NORTH")])
    first = accept(store, mapped(store, first, bindings))
    incoming = receive(store, [roster_row(effective_date="bad-date"),
                               roster_row(network="UNKNOWN", record_id="LIST-9")])
    incoming = mapped(store, incoming, bindings)
    comparison = incoming["preview"]["comparison"]
    assert comparison["baseline"]["attempt_id"] == first["attempt_id"]
    assert incoming["preview"]["quarantined_count"] == 2
    assert comparison["blocked_invalid"] == 1
    assert comparison["unresolved"] == 1
    assert comparison["missing_from_this_delivery"] == 2
    assert comparison["new"] == comparison["changed"] == 0
    assert any(entry["status"] == "blocked_invalid" and entry["previous_locator"]
               for entry in comparison["entries"])


def test_absent_organization_stays_unknown_and_restart_retains_work(store):
    _, bindings = catalog_and_bindings(store)
    first = receive(store, [roster_row(organization_code="")])
    first = accept(store, mapped(store, first, bindings))
    case_id = first["linked_cases"][0]["id"]
    initial = store.case(case_id)["evidence"]
    first_bytes = (store.artifacts / first["artifact_sha"]).read_bytes()
    store.event(case_id, {"action": "assign", "owner": "reviewer", "actor": "operator",
                          "reason": "Source follow-up", "expected_version": 0})
    later = receive(store, [roster_row(organization_code="", participation_status="not_listed")])
    later = accept(store, mapped(store, later, bindings))
    later_bytes = (store.artifacts / later["artifact_sha"]).read_bytes()
    assert later["linked_cases"][0]["id"] == case_id
    restarted = IntakeStore(store.path, store.root)
    case = restarted.case(case_id)
    assert case["owner"] == "reviewer"
    assert case["evidence"] == initial
    assert len(case["history"]) == 1
    assert len(case["later_evidence"]) == 1
    assert case["later_evidence"][0]["original"]["participation_status"] == "not_listed"
    assert (restarted.artifacts / first["artifact_sha"]).read_bytes() == first_bytes
    assert (restarted.artifacts / later["artifact_sha"]).read_bytes() == later_bytes
    with restarted.db() as conn:
        assert conn.execute("SELECT organization_id FROM case_scope WHERE case_id=?", (case_id,)).fetchone()[0] is None
        assert conn.execute("SELECT count(*) FROM participation_observation WHERE organization_id IS NULL").fetchone()[0] == 2


def test_binding_source_and_kind_mismatch_cannot_be_applied(store):
    catalog, bindings = catalog_and_bindings(store)
    foreign = store.bind_source({"source": "other:source", "kind": "network", "source_key": "CEDAR",
                                 "target_id": catalog["cedar"]["id"], "actor": "operator", "reason": "Other source"})
    receipt = receive(store, [roster_row()])
    wrong_source = {**bindings, "network": {**bindings["network"], "CEDAR": foreign["id"]}}
    with pytest.raises(ValueError, match="incompatible source"):
        mapped(store, receipt, wrong_source)
    wrong_kind = {**bindings, "network": {**bindings["network"], "CEDAR": bindings["organization"]["CLINIC"]}}
    with pytest.raises(ValueError, match="incompatible source, kind"):
        mapped(store, receipt, wrong_kind)
    assert _counts(store)["participation_observation"] == 0


def test_clinic_and_different_network_sets_have_separate_baselines(store):
    _, bindings = catalog_and_bindings(store)
    clinic = receive(store, [roster_row()])
    clinic = store.mapping(clinic["id"], {"mapping": {field: field for field in FIELDS}})
    clinic = accept(store, clinic)
    cedar_only = {**bindings, "network": {"CEDAR": bindings["network"]["CEDAR"]}}
    first_network = receive(store, [roster_row(phone="5550100008")])
    first_network = mapped(store, first_network, cedar_only)
    assert first_network["preview"]["comparison"]["baseline"] is None
    first_network = accept(store, first_network)
    both_networks = receive(store, [roster_row(phone="5550100009")])
    both_networks = mapped(store, both_networks, bindings)
    assert both_networks["preview"]["comparison"]["baseline"] is None
    both_networks = accept(store, both_networks)
    another_both = receive(store, [roster_row(phone="5550100001")])
    another_both = mapped(store, another_both, bindings)
    assert another_both["preview"]["comparison"]["baseline"]["attempt_id"] == both_networks["attempt_id"]
    assert another_both["preview"]["comparison"]["baseline"]["attempt_id"] not in {
        clinic["attempt_id"], first_network["attempt_id"]}


def test_conflicting_fixed_network_does_not_mask_missing_baseline(store):
    _, bindings = catalog_and_bindings(store)
    first = receive(store, [roster_row()])
    first = mapped(store, first, bindings, fixed_network_binding_id=bindings["network"]["CEDAR"])
    first = accept(store, first)
    incoming = receive(store, [roster_row(network="PINE")])
    incoming = mapped(store, incoming, bindings, fixed_network_binding_id=bindings["network"]["CEDAR"])
    comparison = incoming["preview"]["comparison"]
    assert comparison["baseline"]["attempt_id"] == first["attempt_id"]
    assert incoming["preview"]["quarantined_count"] == 1
    assert comparison["unresolved"] == 1
    assert comparison["missing_from_this_delivery"] == 1
    assert comparison["blocked_invalid"] == 0


def test_rebinding_changes_interpretation_and_stale_acceptance_is_rejected(store):
    catalog, bindings = catalog_and_bindings(store)
    raw = [roster_row()]
    receipt = receive(store, raw)
    old_preview = mapped(store, receipt, bindings)
    old_fingerprint = old_preview["attempts"][-1]["fingerprint"]
    replacement = store.create_catalog("networks", {"label": "CEDAR", "payer_organization_id": catalog["payer"]["id"],
                                                    "actor": "operator", "reason": "Corrected identity fixture"})
    new_binding = store.bind_source({"source": SOURCE, "kind": "network", "source_key": "CEDAR",
                                     "target_id": replacement["id"],
                                     "expected_binding_id": bindings["network"]["CEDAR"],
                                     "actor": "operator", "reason": "Reviewed correction"})
    before = _counts(store)
    with pytest.raises((ValueError, Conflict)):
        accept(store, old_preview)
    assert _counts(store) == before
    assert store.detail(receipt["id"])["state"] == "preview_ready"
    fresh_bindings = {**bindings, "network": {**bindings["network"], "CEDAR": new_binding["id"]}}
    fresh_preview = mapped(store, receipt, fresh_bindings)
    assert fresh_preview["attempts"][-1]["fingerprint"] != old_fingerprint
    accepted = accept(store, fresh_preview)
    assert accepted["observations"][0]["normalized"]["participation"]["network_id"] == replacement["id"]
    repeated = receive(store, raw)
    repeated = mapped(store, repeated, fresh_bindings)
    before_repeat = _counts(store)
    repeated = accept(store, repeated)
    assert repeated["state"] == "duplicate_delivery"
    assert _counts(store)["observation"] == before_repeat["observation"]
    assert repeated["observations"] == accepted["observations"]


def _counts(store):
    with store.db() as conn:
        return {table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                for table in ("observation", "work_case", "work_event", "participation_observation")}


def test_migration_four_preserves_populated_v3_and_backup(tmp_path):
    db = tmp_path / "intake.sqlite3"
    root = tmp_path / "runtime"
    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True)
    original = csv_payload([roster_row()])
    sha = hashlib.sha256(original).hexdigest()
    (artifacts / sha).write_bytes(original)
    with sqlite3.connect(db) as conn:
        conn.executescript(SCHEMA[0])
        conn.execute("ALTER TABLE relationship ADD COLUMN location_index integer")
        conn.executescript(MIGRATION_3)
        conn.execute("PRAGMA user_version=3")
        conn.executemany("INSERT INTO schema_migration VALUES (?,?)", [(1, "2026-01-01"), (2, "2026-01-02"), (3, "2026-01-03")])
        conn.execute("INSERT INTO artifact VALUES (?,?,?)", (sha, len(original), sha))
        conn.execute("INSERT INTO receipt VALUES (?,?,?,?,?,?,?,?,?)", (
            "r1", "old.csv", SOURCE, "synthetic", "2026-01-01", sha, "flat", None, "{}"))
        conn.execute("INSERT INTO attempt VALUES (?,?,?,?,?,?,?,?,?)", (
            "a1", "r1", "{}", "fp", "committed", "{}", "2026-01-01", "2026-01-01", "{}"))
        conn.execute("INSERT INTO observation VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
            "o1", "a1", "LIST-1", "row:2", json.dumps(roster_row()), json.dumps(roster_row()),
            "NPI:1000000001", SOURCE + ":NORTH", None, "2026-01-01", None))
        conn.execute("INSERT INTO work_case VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            "c1", "qa", "stable", "Synthetic Provider", SOURCE + ":NORTH", "record", "Review",
            "low", "Fixture", "triaged", "reviewer", None, 1, '{"original":"preserved"}',
            None, None, "2026-01-01", "2026-01-01"))
        conn.execute("INSERT INTO work_evidence VALUES (?,?)", ("c1", "o1"))
        conn.execute("INSERT INTO work_event (case_id,action,actor,reason,payload,from_status,to_status,occurred_at) VALUES (?,?,?,?,?,?,?,?)", (
            "c1", "assign", "operator", "Fixture", "{}", "new", "triaged", "2026-01-01"))
        before = {table: conn.execute(f"SELECT * FROM {table}").fetchall()
                  for table in ("artifact", "receipt", "attempt", "observation", "work_case", "work_evidence", "work_event")}
    migrated = IntakeStore(db, root)
    backup = db.with_name(db.name + ".pre-intake-v4.bak")
    assert backup.exists()
    with sqlite3.connect(backup) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    with migrated.db() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        for table, rows in before.items():
            assert [tuple(item) for item in conn.execute(f"SELECT * FROM {table}")] == rows
    assert (artifacts / sha).read_bytes() == original


def test_failed_migration_four_rolls_back_v3_and_retains_original(tmp_path, monkeypatch):
    from provider_directory_truth_layer import network_store

    db = tmp_path / "intake.sqlite3"
    root = tmp_path / "runtime"
    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True)
    original = csv_payload([roster_row()])
    sha = hashlib.sha256(original).hexdigest()
    (artifacts / sha).write_bytes(original)
    with sqlite3.connect(db) as conn:
        conn.executescript(SCHEMA[0])
        conn.execute("ALTER TABLE relationship ADD COLUMN location_index integer")
        conn.executescript(MIGRATION_3)
        conn.execute("PRAGMA user_version=3")
        conn.execute("INSERT INTO artifact VALUES (?,?,?)", (sha, len(original), sha))
        conn.execute("INSERT INTO receipt VALUES (?,?,?,?,?,?,?,?,?)", (
            "r1", "old.csv", SOURCE, "synthetic", "2026-01-01", sha, "flat", None, "{}"))
    monkeypatch.setattr(network_store, "MIGRATION_4", "CREATE TABLE partial_v4(id TEXT); INSERT INTO absent_table VALUES (1);")
    with pytest.raises(sqlite3.OperationalError, match="absent_table"):
        IntakeStore(db, root)
    with sqlite3.connect(db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT artifact_sha FROM receipt WHERE id='r1'").fetchone()[0] == sha
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='partial_v4'").fetchone() is None
    assert (artifacts / sha).read_bytes() == original
    assert db.with_name(db.name + ".pre-intake-v4.bak").exists()
