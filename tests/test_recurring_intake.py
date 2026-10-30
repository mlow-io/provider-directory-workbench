"""N1 recurring clinic delivery contracts, with fixture-owned storage only."""

import csv
import hashlib
import io
import json
import sqlite3

import pytest

from provider_directory_truth_layer.intake_store import Conflict, IntakeStore, SCHEMA, VERSION


SOURCE = "clinic:recurring-fixture"
SCOPE = {"clinic": "north"}
HEADERS = {
    "record_id": "Clinic ID", "npi": "NPI", "provider_name": "Provider",
    "address": "Street", "city": "City", "state": "State", "zip": "ZIP",
    "phone": "Phone", "location_id": "Site",
}


@pytest.fixture
def store(tmp_path):
    return IntakeStore(tmp_path / "intake.sqlite3", tmp_path / "artifacts")


def row(record_id="001", location_id="NORTH", phone="5550100000", **changes):
    return {
        "record_id": record_id, "npi": "1000000001", "provider_name": "Synthetic Clinic",
        "address": "10 Fiction St", "city": "Example", "state": "TN", "zip": "01234",
        "phone": phone, "location_id": location_id, **changes,
    }


def payload(rows, headers=None, extras=None):
    headers = headers or HEADERS
    extras = extras or {}
    fields = list(headers.values()) + list(extras)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for item in rows:
        writer.writerow({**{column: item.get(field, "") for field, column in headers.items()}, **extras})
    return output.getvalue().encode()


def receive(store, rows, *, headers=None, extras=None, scope=SCOPE, source=SOURCE):
    return store.receive(payload(rows, headers, extras), "synthetic-clinic.csv", source=source,
                         metadata={"scope": scope})


def accept(store, receipt):
    return store.commit(receipt["id"], {"actor": "operator", "reason": "Reviewed fixture",
                                        "policy": "valid_rows", "expected_attempt": receipt["attempt_id"]})


def reviewed_revision(store, receipt, mapping=HEADERS):
    preview = store.mapping(receipt["id"], {"mapping": mapping})
    assert preview["state"] == "preview_ready"
    revision = store.save_mapping(receipt["id"], {
        "name": "Clinic recurring CSV", "actor": "operator", "reason": "Reviewed supplier headers",
        "expected_attempt": preview["attempt_id"],
    })
    assert revision["source"] == SOURCE
    assert revision["profile"] == "flat"
    assert revision["scope"] == SCOPE
    assert revision["settings"]["mapping"] == mapping
    assert revision["actor"] == "operator"
    assert revision["reason"] == "Reviewed supplier headers"
    assert revision in store.saved_mappings(receipt["id"])["items"]
    return preview, revision


def _counts(store):
    with store.db() as conn:
        return {table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                for table in ("receipt", "attempt", "observation", "work_case", "work_event")}


def test_saved_mapping_reordered_columns_and_single_accepted_baseline(store):
    first = receive(store, [row("001"), row("002", "SOUTH", "5550100002"),
                            row("003", "NORTH", "5550100003")])
    first, revision = reviewed_revision(store, first)
    accepted = accept(store, first)
    case_id = accepted["linked_cases"][0]["id"]
    initial_case = store.case(case_id)
    assigned = store.event(case_id, {"action": "assign", "owner": "reviewer",
                                     "actor": "operator", "reason": "Fixture assignment", "expected_version": 0})
    new_headers = dict(reversed(list(HEADERS.items())))
    second = receive(store, [row("004", "WEST", "5550100004"), row("001", phone="5550100009"),
                             row("002", "SOUTH", "5550100002")],
                     headers=new_headers, extras={"Supplier Comment": "retained"})
    second = store.mapping(second["id"], {"mapping_revision_id": revision["id"]})
    assert second["state"] == "preview_ready"
    assert second["preview"]["rows"][0]["original"]["Supplier Comment"] == "retained"
    comparison = second["preview"]["comparison"]
    assert comparison["baseline"]["attempt_id"] == accepted["attempt_id"]
    assert comparison["baseline"]["receipt_id"] == accepted["id"]
    assert comparison["raw_row_count"] == comparison["unique_identity_count"] == 3
    assert {key: comparison[key] for key in ("new", "changed", "unchanged", "unresolved",
                                              "blocked_invalid", "missing_from_this_delivery")} == {
        "new": 1, "changed": 1, "unchanged": 1, "unresolved": 0,
        "blocked_invalid": 0, "missing_from_this_delivery": 1,
    }
    statuses = {entry["key"]: entry for entry in comparison["entries"]}
    assert {entry["status"] for entry in statuses.values()} == {
        "new", "changed", "unchanged", "missing"
    }
    changed = next(entry for entry in statuses.values() if entry["status"] == "changed")
    assert any(field["field"] == "phone" and field["old"] == "5550100000" and
               field["new"] == "5550100009" for field in changed["fields"])
    assert changed["previous_receipt_id"] == accepted["id"]
    assert changed["previous_locator"] and changed["current_locator"]
    assert changed["mapping_revision_id"] == revision["id"]
    second = accept(store, second)
    restarted = IntakeStore(store.path, store.root)
    assert restarted.case(case_id)["owner"] == assigned["owner"] == "reviewer"
    assert restarted.case(case_id)["history"] == assigned["history"]
    assert restarted.case(case_id)["evidence"] == initial_case["evidence"]
    assert restarted.artifacts.joinpath(accepted["artifact_sha"]).read_bytes() == payload(
        [row("001"), row("002", "SOUTH", "5550100002"), row("003", "NORTH", "5550100003")])
    assert restarted.artifacts.joinpath(second["artifact_sha"]).read_bytes() == payload(
        [row("004", "WEST", "5550100004"), row("001", phone="5550100009"), row("002", "SOUTH", "5550100002")],
        headers=new_headers, extras={"Supplier Comment": "retained"})


def test_saved_mapping_missing_required_header_pauses_and_scope_must_match(store):
    first = receive(store, [row()])
    first, revision = reviewed_revision(store, first)
    accept(store, first)
    missing_phone = {key: value for key, value in HEADERS.items() if key != "phone"}
    drift = receive(store, [row(phone="5550100008")], headers=missing_phone)
    drift = store.mapping(drift["id"], {"mapping_revision_id": revision["id"]})
    assert drift["state"] == "needs_mapping"
    assert "Phone" in drift["preview"]["error"] or "phone" in drift["preview"]["error"]
    with pytest.raises(ValueError):
        accept(store, drift)
    other_scope = receive(store, [row(phone="5550100008")], scope={"clinic": "south"})
    with pytest.raises((ValueError, Conflict)):
        store.mapping(other_scope["id"], {"mapping_revision_id": revision["id"]})
    other_source = receive(store, [row(phone="5550100008")], source="clinic:other")
    with pytest.raises((ValueError, Conflict)):
        store.mapping(other_source["id"], {"mapping_revision_id": revision["id"]})


def test_invalid_known_key_blocks_baseline_and_unresolved_cannot_hide_missing(store):
    first = receive(store, [row("001"), row("002", "SOUTH"), row("003", "WEST")])
    first, revision = reviewed_revision(store, first)
    accept(store, first)
    incoming = receive(store, [row("001", phone="bad"), row("", "SOUTH", phone="bad")])
    incoming = store.mapping(incoming["id"], {"mapping_revision_id": revision["id"]})
    comparison = incoming["preview"]["comparison"]
    assert incoming["preview"]["valid_count"] == 0
    assert incoming["preview"]["quarantined_count"] == 2
    assert comparison["raw_row_count"] == 2
    assert comparison["blocked_invalid"] == 1
    assert comparison["unresolved"] == 1
    assert comparison["missing_from_this_delivery"] == 2
    assert comparison["new"] == comparison["changed"] == 0
    assert any(entry["status"] == "blocked_invalid" for entry in comparison["entries"])


@pytest.mark.parametrize("contradictory", [False, True])
def test_duplicate_identity_rows_are_quarantined_and_counted_once(store, contradictory):
    incoming = receive(store, [row("001"), row("001", phone="5550100008" if contradictory else "5550100000")])
    incoming = store.mapping(incoming["id"], {"mapping": HEADERS})
    comparison = incoming["preview"]["comparison"]
    assert comparison["raw_row_count"] == 2
    assert comparison["unique_identity_count"] == 1
    assert incoming["preview"]["valid_count"] == 0
    assert incoming["preview"]["quarantined_count"] == 2
    assert all(any("duplicate" in problem.lower() for problem in item["problems"])
               for item in incoming["preview"]["rows"])
    with pytest.raises(ValueError):
        accept(store, incoming)


def test_newer_accepted_baseline_rejects_stale_acceptance_without_writes(store):
    first = receive(store, [row()])
    first, revision = reviewed_revision(store, first)
    accept(store, first)
    stale = receive(store, [row(phone="5550100008")])
    stale = store.mapping(stale["id"], {"mapping_revision_id": revision["id"]})
    newer = receive(store, [row(phone="5550100009")])
    newer = store.mapping(newer["id"], {"mapping_revision_id": revision["id"]})
    accept(store, newer)
    before = _counts(store)
    with pytest.raises(Conflict, match="baseline|newer|stale"):
        accept(store, stale)
    assert _counts(store) == before
    assert store.detail(stale["id"])["state"] == "preview_ready"


def test_mapping_revision_changes_interpretation_and_repeat_is_idempotent(store):
    first = receive(store, [row(phone="5550100000")], extras={"Alternate": "5550100009"})
    first, normal = reviewed_revision(store, first)
    accept(store, first)
    alternate_map = {**HEADERS, "phone": "Alternate"}
    alternate = store.mapping(first["id"], {"mapping": alternate_map})
    assert alternate["state"] == "preview_ready"
    changed = store.save_mapping(first["id"], {"name": "Alternative phone", "actor": "operator",
                                               "reason": "Corrected field selection", "expected_attempt": alternate["attempt_id"]})
    assert changed["id"] != normal["id"]
    with store.db() as conn:
        table = next(name for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%mapping%revision%'") )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(f"UPDATE {table} SET name='rewritten' WHERE id=?", (normal["id"],))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(f"DELETE FROM {table} WHERE id=?", (normal["id"],))
    second = receive(store, [row(phone="5550100000")], extras={"Alternate": "5550100009"})
    normal_attempt = store.mapping(second["id"], {"mapping_revision_id": normal["id"]})
    alternate_attempt = store.mapping(second["id"], {"mapping_revision_id": changed["id"]})
    assert normal_attempt["attempts"][-1]["fingerprint"] != alternate_attempt["attempts"][-1]["fingerprint"]
    accepted = accept(store, alternate_attempt)
    repeated = receive(store, [row(phone="5550100000")], extras={"Alternate": "5550100009"})
    repeated = store.mapping(repeated["id"], {"mapping_revision_id": changed["id"]})
    before = _counts(store)
    repeated = accept(store, repeated)
    assert repeated["state"] == "duplicate_delivery"
    after = _counts(store)
    assert after["observation"] == before["observation"]
    assert repeated["observations"] == accepted["observations"]


def test_baseline_is_one_accepted_delivery_not_a_history_union(store):
    first = receive(store, [row("001"), row("002", "SOUTH")])
    first, revision = reviewed_revision(store, first)
    accept(store, first)
    second = receive(store, [row("001", phone="5550100008")])
    second = store.mapping(second["id"], {"mapping_revision_id": revision["id"]})
    second = accept(store, second)
    duplicate = receive(store, [row("001", phone="5550100008")])
    duplicate = store.mapping(duplicate["id"], {"mapping_revision_id": revision["id"]})
    duplicate = accept(store, duplicate)
    assert duplicate["state"] == "duplicate_delivery"
    third = receive(store, [row("002", "SOUTH")])
    third = store.mapping(third["id"], {"mapping_revision_id": revision["id"]})
    comparison = third["preview"]["comparison"]
    assert comparison["baseline"]["attempt_id"] == second["attempt_id"]
    assert comparison["baseline"]["receipt_id"] == second["id"]
    assert comparison["new"] == 1
    assert comparison["missing_from_this_delivery"] == 1
    assert {entry["status"] for entry in comparison["entries"]} == {"new", "missing"}


def test_failed_acceptance_rolls_back_all_rows_cases_and_artifact(store, monkeypatch):
    first = receive(store, [row("001")])
    first, revision = reviewed_revision(store, first)
    accept(store, first)
    incoming = receive(store, [row("002", "SOUTH"), row("003", "WEST")])
    incoming = store.mapping(incoming["id"], {"mapping_revision_id": revision["id"]})
    artifact = store.artifacts / incoming["artifact_sha"]
    artifact_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
    before = _counts(store)
    original_link = store.link_work
    calls = 0

    def fail_second(conn, receipt, observation):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("Injected second-row failure")
        return original_link(conn, receipt, observation)

    monkeypatch.setattr(store, "link_work", fail_second)
    with pytest.raises(RuntimeError, match="Injected second-row failure"):
        accept(store, incoming)
    assert _counts(store) == before
    assert store.detail(incoming["id"])["state"] == "preview_ready"
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == artifact_hash
    monkeypatch.setattr(store, "link_work", original_link)
    assert len(accept(store, incoming)["observations"]) == 2


def test_migrate_populated_v2_preserves_records_and_backup(tmp_path):
    db = tmp_path / "intake.sqlite3"
    root = tmp_path / "runtime"
    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True)
    original = payload([row()])
    sha = hashlib.sha256(original).hexdigest()
    (artifacts / sha).write_bytes(original)
    with sqlite3.connect(db) as conn:
        conn.executescript(SCHEMA[0])
        conn.execute("ALTER TABLE relationship ADD COLUMN location_index integer")
        conn.execute("PRAGMA user_version=2")
        conn.execute("INSERT INTO schema_migration VALUES (1,'2026-01-01')")
        conn.execute("INSERT INTO schema_migration VALUES (2,'2026-01-02')")
        conn.execute("INSERT INTO artifact VALUES (?,?,?)", (sha, len(original), sha))
        conn.execute("INSERT INTO receipt VALUES (?,?,?,?,?,?,?,?,?)", (
            "r1", "original.csv", SOURCE, "synthetic", "2026-01-01", sha, "flat", None,
            json.dumps({"scope": SCOPE})))
        conn.execute("INSERT INTO attempt VALUES (?,?,?,?,?,?,?,?,?)", (
            "a1", "r1", "{}", "fp", "committed", "{}", "2026-01-01", "2026-01-01", "{}"))
        conn.execute("INSERT INTO observation VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
            "o1", "a1", "001", "row:2", json.dumps(row()), json.dumps(row()),
            "NPI:1000000001", SOURCE + ":NORTH", None, "2026-01-01", None))
        conn.execute("INSERT INTO work_case VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            "c1", "qa", "stable", "Synthetic Clinic", SOURCE + ":NORTH", "record", "Review",
            "low", "Fixture", "triaged", "reviewer", None, 1, '{"original":"preserved"}',
            None, None, "2026-01-01", "2026-01-01"))
        conn.execute("INSERT INTO work_evidence VALUES (?,?)", ("c1", "o1"))
        conn.execute("INSERT INTO work_event (case_id,action,actor,reason,payload,from_status,to_status,occurred_at) VALUES (?,?,?,?,?,?,?,?)", (
            "c1", "assign", "operator", "Fixture", "{}", "new", "triaged", "2026-01-01"))
    before = {"artifact": original, "case": None}
    with sqlite3.connect(db) as conn:
        before["case"] = conn.execute("SELECT * FROM work_case WHERE id='c1'").fetchone()
        before["observation"] = conn.execute("SELECT * FROM observation WHERE id='o1'").fetchone()
        before["event"] = conn.execute("SELECT * FROM work_event WHERE case_id='c1'").fetchone()
    migrated = IntakeStore(db, root)
    backup = db.with_name(db.name + ".pre-intake-v3.bak")
    assert backup.exists()
    with sqlite3.connect(backup) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    with migrated.db() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == VERSION
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert tuple(conn.execute("SELECT * FROM work_case WHERE id='c1'").fetchone()) == before["case"]
        assert tuple(conn.execute("SELECT * FROM observation WHERE id='o1'").fetchone()) == before["observation"]
        assert tuple(conn.execute("SELECT * FROM work_event WHERE case_id='c1'").fetchone()) == before["event"]
    assert (artifacts / sha).read_bytes() == before["artifact"]
