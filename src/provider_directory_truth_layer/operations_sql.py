"""Read-only operational questions over the durable intake SQLite database."""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import date
import json
from pathlib import Path
import sqlite3
from urllib.parse import quote


SQL_DIR = Path(__file__).resolve().parents[2] / "sql" / "operations"


def _connect(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise ValueError(f"Database does not exist: {path}")
    # mode=ro prevents writes even when the caller supplies a writable database.
    uri = "file:" + quote(str(path.resolve()), safe="/") + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _query(conn: sqlite3.Connection, name: str, parameters: dict | None = None) -> list[dict]:
    statement = (SQL_DIR / f"{name}.sql").read_text(encoding="utf-8")
    return [dict(row) for row in conn.execute(statement, parameters or {})]


def _selected_attempt(conn: sqlite3.Connection, attempt_id: str) -> tuple[str, dict]:
    row = conn.execute(
        """SELECT a.id, a.state, a.preview, a.receipt_id, r.source, r.profile, r.metadata
           FROM attempt AS a JOIN receipt AS r ON r.id = a.receipt_id WHERE a.id = ?""",
        (attempt_id,),
    ).fetchone()
    if row is None or row["state"] not in {"committed", "duplicate_delivery"}:
        raise ValueError(f"Attempt {attempt_id!r} is not an accepted delivery")
    canonical = row["id"]
    if row["state"] == "duplicate_delivery":
        canonical = json.loads(row["preview"]).get("reuses_attempt")
        reused = conn.execute(
            """SELECT a.state, r.source, r.profile, r.metadata FROM attempt AS a
               JOIN receipt AS r ON r.id = a.receipt_id WHERE a.id = ?""",
            (canonical,),
        ).fetchone()
        if reused is None or reused["state"] != "committed":
            raise ValueError(f"Attempt {attempt_id!r} has no committed reuse target")
        if (reused["source"], reused["profile"], json.loads(reused["metadata"]).get("scope")) != (
            row["source"], row["profile"], json.loads(row["metadata"]).get("scope")
        ):
            raise ValueError("Duplicate delivery reuse target has incompatible scope")
    return canonical, {"source": row["source"], "profile": row["profile"],
                       "scope": json.loads(row["metadata"]).get("scope")}


def _check_unique_keys(conn: sqlite3.Connection, attempt_id: str) -> None:
    rows = conn.execute(
        """SELECT native_id, coalesce(cast(json_extract(normalized, '$.location_id') AS text), '') AS location_key,
                  count(*) AS copies FROM observation WHERE attempt_id = ?
           GROUP BY native_id, location_key""",
        (attempt_id,),
    ).fetchall()
    if any(row["native_id"] is None or str(row["native_id"]).strip() == "" or row["copies"] != 1 for row in rows):
        raise ValueError(f"Attempt {attempt_id!r} has unresolved or duplicate source-native keys")


def run(path: Path, question: str, **parameters: object) -> list[dict]:
    """Run one validated question and return JSON-serializable rows without opening IntakeStore."""
    with closing(_connect(path)) as conn:
        # A single read transaction pins validation and result rows to one WAL snapshot.
        conn.execute("BEGIN")
        if question == "follow-up":
            as_of = str(parameters.get("as_of") or date.today().isoformat())
            try:
                date.fromisoformat(as_of)
            except ValueError as error:
                raise ValueError("--as-of must be an ISO date (YYYY-MM-DD)") from error
            return _query(conn, "follow_up", {"as_of": as_of, "include_closed": int(bool(parameters.get("include_closed")))})
        if question == "lineage":
            return _query(conn, "lineage", {"case_id": parameters["case_id"]})
        if question == "latest-event":
            return _query(conn, "latest_event")
        if question == "compare":
            left, left_scope = _selected_attempt(conn, str(parameters["left_attempt"]))
            right, right_scope = _selected_attempt(conn, str(parameters["right_attempt"]))
            if left_scope != right_scope:
                raise ValueError("Selected deliveries must have the same source, profile, and scope")
            if left == right:
                raise ValueError("Selected deliveries resolve to the same accepted interpretation")
            _check_unique_keys(conn, left)
            _check_unique_keys(conn, right)
            return _query(conn, "selected_delivery_diff", {"left_attempt": left, "right_attempt": right})
        raise ValueError(f"Unknown question: {question}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path, help="Existing durable intake SQLite database")
    commands = parser.add_subparsers(dest="question", required=True)
    follow = commands.add_parser("follow-up", help="Cases needing assignment or overdue follow-up")
    follow.add_argument("--as-of", help="ISO operator date; defaults to today")
    follow.add_argument("--include-closed", action="store_true")
    lineage = commands.add_parser("lineage", help="Receipt and row evidence for a case")
    lineage.add_argument("--case-id", required=True)
    commands.add_parser("latest-event", help="Latest event per case")
    compare = commands.add_parser("compare", help="Compare two selected accepted attempts")
    compare.add_argument("--left-attempt", required=True)
    compare.add_argument("--right-attempt", required=True)
    args = parser.parse_args(argv)
    try:
        options = vars(args).copy()
        options.pop("db")
        options.pop("question")
        rows = run(args.db, args.question, **options)
    except (ValueError, sqlite3.Error, OSError, KeyError) as error:
        parser.error(str(error))
    print(json.dumps(rows, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
