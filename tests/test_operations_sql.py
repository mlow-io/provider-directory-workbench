"""Operational SQL uses a fixture-owned durable database and never changes it."""

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from provider_directory_truth_layer.intake_store import SCHEMA
from provider_directory_truth_layer.operations_sql import run


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def operations_db(tmp_path):
    db = tmp_path / "intake.sqlite3"
    artifact = tmp_path / "original.csv"
    artifact.write_text("id,phone\na,555-0100\n")
    with sqlite3.connect(db) as conn:
        conn.executescript(SCHEMA[0])
        conn.execute("INSERT INTO artifact VALUES (?,?,?)", ("sha", artifact.stat().st_size, artifact.name))
        receipts = [
            ("r1", "first.csv", "clinic", "local", "2026-01-01", "sha", "flat", None, '{"scope":"north"}'),
            ("r2", "second.csv", "clinic", "local", "2026-02-01", "sha", "flat", None, '{"scope":"north"}'),
            ("rdup", "copy.csv", "clinic", "local", "2026-02-02", "sha", "flat", "r2", '{"scope":"north"}'),
            ("rother", "other.csv", "clinic", "local", "2026-02-03", "sha", "flat", None, '{"scope":"south"}'),
        ]
        conn.executemany("INSERT INTO receipt VALUES (?,?,?,?,?,?,?,?,?)", receipts)
        attempts = [
            ("a1", "r1", "committed", "{}"),
            ("a2", "r2", "committed", "{}"),
            ("adup", "rdup", "duplicate_delivery", '{"reuses_attempt":"a2"}'),
            ("aother", "rother", "committed", "{}"),
            ("apreview", "r2", "preview_ready", "{}"),
        ]
        conn.executemany(
            "INSERT INTO attempt VALUES (?,?,?,?,?,?,?,?,?)",
            [(aid, rid, "{}", aid, state, preview, "2026-01-01", "2026-01-01" if state != "preview_ready" else None, "{}") for aid, rid, state, preview in attempts],
        )
        observations = [
            ("o1", "a1", "native-a", "row:2", '{"phone":"old"}', '{"location_id":"north","phone":"old"}'),
            ("o2", "a1", "native-b", "row:3", "{}", '{"location_id":"north","phone":null}'),
            ("o3", "a2", "native-a", "row:4", '{"phone":"new"}', '{"location_id":"north","phone":"new"}'),
            ("o4", "a2", "native-c", "row:5", "{}", '{"location_id":"north","phone":null}'),
            ("o5", "aother", "native-a", "row:2", "{}", '{"location_id":"south"}'),
        ]
        conn.executemany(
            "INSERT INTO observation VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [(oid, aid, native, locator, original, norm, None, None, None, "2026-01-01", None) for oid, aid, native, locator, original, norm in observations],
        )
        cases = [
            ("c1", "new", None, "2026-01-01"),
            ("c2", "new", "owner", None),
            ("c3", "new", "owner", "2026-12-01"),
            ("c4", "deferred", "owner", "2026-01-15"),
            ("c5", "resolved", None, "2026-01-01"),
            ("c6", "new", "owner", "2026-02-01"),
            ("c7", "new", None, "2026-02-01"),
        ]
        conn.executemany(
            "INSERT INTO work_case VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(cid, "qa", cid, "Synthetic Provider", None, "phone", "Review", "low", "Fixture", status, owner, due, 0, "{}", None, None, "2026-01-01", "2026-01-01") for cid, status, owner, due in cases],
        )
        conn.executemany("INSERT INTO work_evidence VALUES (?,?)", [("c1", "o1"), ("c1", "o2"), ("c1", "o3")])
        conn.executemany(
            "INSERT INTO work_event (case_id,action,actor,reason,payload,from_status,to_status,occurred_at) VALUES (?,?,?,?,?,?,?,?)",
            [("c1", "assign", "operator", "fixture", "{}", "new", "triaged", "2026-01-01T12:00:00"),
             ("c1", "note", "operator", "fixture", "{}", "triaged", "triaged", "2026-01-01T12:00:00")],
        )
    return db, artifact


def test_follow_up_lineage_latest_and_read_only(operations_db):
    db, artifact = operations_db
    before = (_hash(db), _hash(artifact))
    assert [row["case_id"] for row in run(db, "follow-up", as_of="2026-02-01")] == ["c1", "c4", "c7"]
    assert [row["case_id"] for row in run(db, "follow-up", as_of="2026-02-01", include_closed=True)] == ["c1", "c5", "c4", "c7"]
    assert [row["observation_id"] for row in run(db, "lineage", case_id="c1")] == ["o1", "o2", "o3"]
    assert run(db, "lineage", case_id="c2")[0]["observation_id"] is None
    latest = {row["case_id"]: row for row in run(db, "latest-event")}
    assert len(latest) == 7
    assert latest["c1"]["action"] == "note"
    assert latest["c2"]["event_id"] is None
    assert (_hash(db), _hash(artifact)) == before


def test_selected_delivery_diff_and_rejections(operations_db):
    db, artifact = operations_db
    before = (_hash(db), _hash(artifact))
    rows = run(db, "compare", left_attempt="a1", right_attempt="a2")
    assert {row["native_id"]: row["difference"] for row in rows} == {
        "native-a": "changed", "native-b": "missing_from_right", "native-c": "new"
    }
    assert run(db, "compare", left_attempt="a1", right_attempt="adup") == rows
    for left, right in [("a1", "apreview"), ("a1", "aother"), ("a2", "adup")]:
        with pytest.raises(ValueError):
            run(db, "compare", left_attempt=left, right_attempt=right)
    assert (_hash(db), _hash(artifact)) == before


def test_ambiguous_keys_are_rejected(operations_db):
    db, _ = operations_db
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO observation VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("duplicate", "a2", "native-a", "row:6", "{}", '{"location_id":"north"}', None, None, None, "2026-02-01", None),
        )
    with pytest.raises(ValueError, match="duplicate"):
        run(db, "compare", left_attempt="a1", right_attempt="a2")


def test_unresolved_key_is_rejected(operations_db):
    db, _ = operations_db
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO observation VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("unresolved", "a2", None, "row:7", "{}", "{}", None, None, None, "2026-02-01", None),
        )
    with pytest.raises(ValueError, match="unresolved"):
        run(db, "compare", left_attempt="a1", right_attempt="a2")


def test_null_and_empty_field_values_are_distinct(operations_db):
    db, _ = operations_db
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE observation SET native_id='native-b' WHERE id='o4'")
        conn.execute("UPDATE observation SET normalized=? WHERE id='o4'", ('{"location_id":"north","phone":""}',))
    rows = run(db, "compare", left_attempt="a1", right_attempt="a2")
    assert next(row for row in rows if row["native_id"] == "native-b")["difference"] == "changed"


def test_cli_and_open_wal_remain_read_only(operations_db):
    db, artifact = operations_db
    source_root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(source_root / "src")}
    help_result = subprocess.run(
        [sys.executable, "-m", "provider_directory_truth_layer.operations_sql", "--help"],
        cwd=source_root, env=env, capture_output=True, text=True, check=True,
    )
    assert "compare" in help_result.stdout
    with sqlite3.connect(db) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("INSERT INTO schema_migration VALUES (1,'fixture')")
        writer.commit()
        # SQLite may update transient -shm reader locks; durable DB/WAL/artifact bytes must not change.
        tracked = [path for path in (db, Path(str(db) + "-wal"), artifact) if path.exists()]
        before = {path: _hash(path) for path in tracked}
        result = subprocess.run(
            [sys.executable, "-m", "provider_directory_truth_layer.operations_sql", "--db", str(db),
             "compare", "--left-attempt", "a1", "--right-attempt", "a2"],
            cwd=source_root, env=env, capture_output=True, text=True, check=True,
        )
        assert {row["difference"] for row in json.loads(result.stdout)} == {"new", "changed", "missing_from_right"}
        assert {path: _hash(path) for path in tracked} == before
