from __future__ import annotations

import argparse
import csv
import hashlib
import io
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import __version__
from .storage import database_path, connect


CaseStatus = Literal["new", "assigned", "in_review", "resolved", "deferred"]
CaseAction = Literal["assign", "start_review", "resolve", "defer", "add_note"]


class BatchSummary(BaseModel):
    batch_id: str
    source_label: str
    record_count: int
    exception_count: int
    records_with_issues: int
    issue_counts: dict[str, int]
    severity_mix: dict[str, int]
    source_summary: dict[str, int]
    data_notice: str
    limitations: str


class CaseListItem(BaseModel):
    case_id: str
    record_id: str
    provider_name: str
    issue_code: str
    severity: str
    field_name: str
    source: str
    review_status: CaseStatus
    assigned_to: str | None
    updated_at: str


class CasePage(BaseModel):
    items: list[CaseListItem]
    total: int


class RecordValue(BaseModel):
    values: dict[str, str | int | float | None]


class HistoryEvent(BaseModel):
    event_id: int
    event_type: str
    from_status: str | None
    to_status: str | None
    assigned_to: str | None
    reason: str
    note: str | None
    occurred_at: str


class DuplicateComparison(BaseModel):
    candidate: RecordValue
    records: list[RecordValue]
    warning: str


class CaseDetail(BaseModel):
    case: CaseListItem
    exception: RecordValue
    normalized_records: list[RecordValue]
    recommendation: str
    explanation: str
    notes: str | None
    history: list[HistoryEvent]
    duplicate: DuplicateComparison | None


class TransitionInput(BaseModel):
    action: CaseAction
    assignee: str | None = Field(default=None, max_length=120)
    reason: str = Field(min_length=3, max_length=500)
    note: str | None = Field(default=None, max_length=2_000)


class TransitionResult(BaseModel):
    case: CaseListItem
    event: HistoryEvent


class ReviewStore:
    def __init__(self, sqlite_path: Path) -> None:
        self.sqlite_path = sqlite_path

    def connect(self) -> sqlite3.Connection:
        if not self.sqlite_path.exists():
            raise HTTPException(
                status_code=503,
                detail="QA SQLite output is unavailable. Run `make demo` before starting the review API.",
            )
        conn = connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            available = {
                row[0]
                for row in conn.execute("select name from sqlite_master where type = 'table'")
            }
            required = {"provider_directory_exceptions", "normalized_provider_records", "quality_summary"}
            if not required.issubset(available):
                raise HTTPException(status_code=503, detail="QA SQLite output has incomplete source tables.")
            conn.executescript(
                """
                create table if not exists review_case (
                    case_id text primary key,
                    batch_id text not null,
                    review_status text not null,
                    assigned_to text,
                    latest_note text,
                    created_at text not null,
                    updated_at text not null
                );
                create table if not exists review_event (
                    event_id integer primary key autoincrement,
                    case_id text not null,
                    event_type text not null,
                    from_status text,
                    to_status text,
                    assigned_to text,
                    reason text not null,
                    note text,
                    occurred_at text not null,
                    foreign key(case_id) references review_case(case_id)
                );
                """
            )
            batch_id = self.batch_id(conn)
            for index, row in enumerate(self.rows(conn, "select * from provider_directory_exceptions order by priority_rank, issue_code, record_id")):
                case_id = self.case_id(batch_id, index, row)
                now = utc_now()
                conn.execute(
                    """
                    insert or ignore into review_case
                    (case_id, batch_id, review_status, assigned_to, latest_note, created_at, updated_at)
                    values (?, ?, 'new', null, null, ?, ?)
                    """,
                    (case_id, batch_id, now, now),
                )
            conn.commit()

    @staticmethod
    def rows(conn: sqlite3.Connection, query: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        return [dict(row) for row in conn.execute(query, params).fetchall()]

    @staticmethod
    def case_id(batch_id: str, index: int, row: dict[str, object]) -> str:
        seed = "|".join(str(row.get(key, "")) for key in ("record_id", "issue_code", "field_name", "source"))
        digest = hashlib.sha256(f"{batch_id}|{index}|{seed}".encode()).hexdigest()[:14]
        return f"case_{digest}"

    def batch_id(self, conn: sqlite3.Connection) -> str:
        rows = self.rows(
            conn,
            "select record_id, issue_code, field_name, source from provider_directory_exceptions order by priority_rank, issue_code, record_id",
        )
        fingerprint = "|".join("~".join(str(row.get(key) or "") for key in row) for row in rows)
        digest = hashlib.sha256(f"provider-directory-qa|{fingerprint}".encode()).hexdigest()[:10]
        return f"qa-{digest}"

    def batch_summary(self) -> BatchSummary:
        self.initialize()
        with self.connect() as conn:
            exceptions = self.rows(conn, "select * from provider_directory_exceptions")
            summary = {row["metric"]: row["value"] for row in self.rows(conn, "select * from quality_summary")}
            issue_counts = Counter(str(row["issue_code"]) for row in exceptions)
            severity_mix = Counter(str(row["severity"]) for row in exceptions)
            source_summary = Counter(str(row.get("source") or "Unknown") for row in exceptions)
            return BatchSummary(
                batch_id=self.batch_id(conn),
                source_label="Synthetic sample provider-directory batch",
                record_count=int(float(summary.get("total_records", 0))),
                exception_count=len(exceptions),
                records_with_issues=int(float(summary.get("records_with_issues", 0))),
                issue_counts=dict(issue_counts),
                severity_mix=dict(severity_mix),
                source_summary=dict(source_summary),
                data_notice="This console is using synthetic sample data unless a locally generated public NPI batch is selected.",
                limitations="NPI Registry records are public reference data, not certified provider truth. Duplicate candidates require human review and are never merged automatically.",
            )

    def list_cases(
        self,
        search: str | None,
        severity: str | None,
        issue_code: str | None,
        status: str | None,
        sort: str,
        direction: str,
    ) -> CasePage:
        self.initialize()
        sortable = {
            "priority": "e.priority_rank",
            "provider": "e.provider_name",
            "issue_code": "e.issue_code",
            "severity": "e.severity",
            "status": "c.review_status",
            "owner": "c.assigned_to",
            "updated": "c.updated_at",
        }
        if sort not in sortable or direction not in {"asc", "desc"}:
            raise HTTPException(status_code=422, detail="Unsupported sort order.")
        filters: list[str] = []
        params: list[object] = []
        if search:
            filters.append("(lower(e.provider_name) like ? or lower(e.record_id) like ? or lower(e.issue_code) like ?)")
            token = f"%{search.lower()}%"
            params.extend([token, token, token])
        for column, value in (("e.severity", severity), ("e.issue_code", issue_code), ("c.review_status", status)):
            if value:
                filters.append(f"{column} = ?")
                params.append(value)
        where = f"where {' and '.join(filters)}" if filters else ""
        with self.connect() as conn:
            # SQLite cannot invoke the Python case-id derivation in a join; map source rows in Python instead.
            all_rows = self.rows(conn, "select * from provider_directory_exceptions order by priority_rank, issue_code, record_id")
            cases = {row["case_id"]: row for row in self.rows(conn, "select * from review_case")}
            batch_id = self.batch_id(conn)
            items = [
                (self.list_item(row, cases[self.case_id(batch_id, index, row)]), int(row.get("priority_rank") or 0))
                for index, row in enumerate(all_rows)
            ]
        filtered = [pair for pair in items if self.matches(pair[0], search, severity, issue_code, status)]
        key_map = {
            "priority": lambda pair: pair[1],
            "provider": lambda pair: pair[0].provider_name.lower(),
            "issue_code": lambda pair: pair[0].issue_code,
            "severity": lambda pair: pair[0].severity,
            "status": lambda pair: pair[0].review_status,
            "owner": lambda pair: pair[0].assigned_to or "",
            "updated": lambda pair: pair[0].updated_at,
        }
        reverse = direction == "desc"
        sorted_items = sorted(filtered, key=key_map[sort], reverse=reverse)
        return CasePage(items=[item for item, _ in sorted_items], total=len(sorted_items))

    @staticmethod
    def matches(item: CaseListItem, search: str | None, severity: str | None, issue_code: str | None, status: str | None) -> bool:
        haystack = f"{item.provider_name} {item.record_id} {item.issue_code}".lower()
        return (
            (not search or search.lower() in haystack)
            and (not severity or item.severity == severity)
            and (not issue_code or item.issue_code == issue_code)
            and (not status or item.review_status == status)
        )

    @staticmethod
    def list_item(exception: dict[str, object], case: dict[str, object]) -> CaseListItem:
        return CaseListItem(
            case_id=str(case["case_id"]),
            record_id=str(exception.get("record_id") or ""),
            provider_name=str(exception.get("provider_name") or ""),
            issue_code=str(exception.get("issue_code") or ""),
            severity=str(exception.get("severity") or ""),
            field_name=str(exception.get("field_name") or ""),
            source=str(exception.get("source") or ""),
            review_status=str(case["review_status"]),
            assigned_to=case.get("assigned_to"),
            updated_at=str(case["updated_at"]),
        )

    def find_case(self, case_id: str) -> tuple[dict[str, object], dict[str, object], sqlite3.Connection]:
        self.initialize()
        conn = self.connect()
        case = conn.execute("select * from review_case where case_id = ?", (case_id,)).fetchone()
        if case is None:
            conn.close()
            raise HTTPException(status_code=404, detail="Review case not found.")
        batch_id = self.batch_id(conn)
        exceptions = self.rows(conn, "select * from provider_directory_exceptions order by priority_rank, issue_code, record_id")
        for index, exception in enumerate(exceptions):
            if self.case_id(batch_id, index, exception) == case_id:
                return exception, dict(case), conn
        conn.close()
        raise HTTPException(status_code=404, detail="Source exception for review case not found.")

    def detail(self, case_id: str) -> CaseDetail:
        exception, case, conn = self.find_case(case_id)
        try:
            record_ids = str(exception.get("record_id") or "").split(";")
            normalized = self.rows(
                conn,
                f"select * from normalized_provider_records where record_id in ({','.join('?' for _ in record_ids)})",
                tuple(record_ids),
            )
            history = [HistoryEvent(**row) for row in self.rows(conn, "select * from review_event where case_id = ? order by event_id", (case_id,))]
            duplicate = self.duplicate(conn, exception, normalized)
            return CaseDetail(
                case=self.list_item(exception, case),
                exception=RecordValue(values=clean_values(exception)),
                normalized_records=[RecordValue(values=clean_values(row)) for row in normalized],
                recommendation=str(exception.get("recommended_action") or "review_record"),
                explanation=str(exception.get("issue_detail") or "This QA rule requires human review."),
                notes=case.get("latest_note"),
                history=history,
                duplicate=duplicate,
            )
        finally:
            conn.close()

    def duplicate(self, conn: sqlite3.Connection, exception: dict[str, object], normalized: list[dict[str, object]]) -> DuplicateComparison | None:
        if exception.get("issue_code") != "possible_duplicate_provider_location":
            return None
        candidate = conn.execute(
            "select * from duplicate_candidates where record_ids = ?",
            (exception.get("record_id"),),
        ).fetchone()
        if candidate is None:
            return None
        return DuplicateComparison(
            candidate=RecordValue(values=clean_values(dict(candidate))),
            records=[RecordValue(values=clean_values(row)) for row in normalized],
            warning="Candidate only — no automatic merge. Compare source evidence and confirm the decision with a reviewer.",
        )

    def transition(self, case_id: str, payload: TransitionInput) -> TransitionResult:
        exception, case, conn = self.find_case(case_id)
        try:
            current = str(case["review_status"])
            rules: dict[str, tuple[set[str], str | None]] = {
                "assign": ({"new", "assigned", "in_review", "deferred"}, "assigned"),
                "start_review": ({"new", "assigned", "deferred", "resolved"}, "in_review"),
                "resolve": ({"in_review"}, "resolved"),
                "defer": ({"new", "assigned", "in_review"}, "deferred"),
                "add_note": ({"new", "assigned", "in_review", "resolved", "deferred"}, None),
            }
            allowed, target = rules[payload.action]
            if current not in allowed:
                raise HTTPException(status_code=409, detail=f"Cannot {payload.action.replace('_', ' ')} a {current} case.")
            if payload.action == "assign" and not payload.assignee:
                raise HTTPException(status_code=422, detail="An assignee is required when assigning a case.")
            if payload.action == "add_note" and not payload.note:
                raise HTTPException(status_code=422, detail="A note is required for an add-note event.")
            now = utc_now()
            next_status = target or current
            next_assignee = payload.assignee if payload.action == "assign" else case.get("assigned_to")
            next_note = payload.note if payload.note else case.get("latest_note")
            conn.execute(
                "update review_case set review_status = ?, assigned_to = ?, latest_note = ?, updated_at = ? where case_id = ?",
                (next_status, next_assignee, next_note, now, case_id),
            )
            cursor = conn.execute(
                """
                insert into review_event (case_id, event_type, from_status, to_status, assigned_to, reason, note, occurred_at)
                values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (case_id, payload.action, current if target else None, next_status if target else None, next_assignee, payload.reason, payload.note, now),
            )
            conn.commit()
            updated = dict(conn.execute("select * from review_case where case_id = ?", (case_id,)).fetchone())
            event = HistoryEvent(**dict(conn.execute("select * from review_event where event_id = ?", (cursor.lastrowid,)).fetchone()))
            return TransitionResult(case=self.list_item(exception, updated), event=event)
        finally:
            conn.close()

    def export_cases(self, **filters: str | None) -> str:
        cases = self.list_cases(**filters).items
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(["case_id", "record_id", "provider_name", "issue_code", "severity", "status", "assignee", "updated_at"])
        for item in cases:
            writer.writerow([item.case_id, item.record_id, item.provider_name, item.issue_code, item.severity, item.review_status, item.assigned_to or "", item.updated_at])
        return stream.getvalue()

    def export_batch(self) -> str:
        batch = self.batch_summary()
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(["batch_id", "source_label", "record_count", "exception_count", "records_with_issues", "data_notice", "limitations"])
        writer.writerow([batch.batch_id, batch.source_label, batch.record_count, batch.exception_count, batch.records_with_issues, batch.data_notice, batch.limitations])
        return stream.getvalue()

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def clean_values(row: dict[str, object]) -> dict[str, str | int | float | None]:
    cleaned: dict[str, str | int | float | None] = {}
    for key, value in row.items():
        cleaned[key] = None if value is None else value if isinstance(value, (str, int, float)) else str(value)
    return cleaned


def create_app(sqlite_path: Path | None = None) -> FastAPI:
    app = FastAPI(title="Directory Review Console API", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    store = ReviewStore(sqlite_path or database_path())

    def get_store() -> ReviewStore:
        return store

    @app.get("/api/health")
    def health(_: ReviewStore = Depends(get_store)) -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/batches/current", response_model=BatchSummary)
    def current_batch(store: ReviewStore = Depends(get_store)) -> BatchSummary:
        return store.batch_summary()

    @app.get("/api/cases", response_model=CasePage)
    def cases(
        store: ReviewStore = Depends(get_store),
        search: str | None = None,
        severity: str | None = None,
        issue_code: str | None = None,
        status: str | None = None,
        sort: str = "priority",
        direction: str = "asc",
    ) -> CasePage:
        return store.list_cases(search, severity, issue_code, status, sort, direction)

    @app.get("/api/cases/{case_id}", response_model=CaseDetail)
    def case_detail(case_id: str, store: ReviewStore = Depends(get_store)) -> CaseDetail:
        return store.detail(case_id)

    @app.post("/api/cases/{case_id}/transitions", response_model=TransitionResult)
    def transition(case_id: str, payload: TransitionInput, store: ReviewStore = Depends(get_store)) -> TransitionResult:
        return store.transition(case_id, payload)

    @app.get("/api/exports/cases.csv")
    def cases_export(
        store: ReviewStore = Depends(get_store),
        search: str | None = None,
        severity: str | None = None,
        issue_code: str | None = None,
        status: str | None = None,
        sort: str = "priority",
        direction: str = "asc",
    ) -> StreamingResponse:
        content = store.export_cases(search=search, severity=severity, issue_code=issue_code, status=status, sort=sort, direction=direction)
        return StreamingResponse(iter([content]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=directory-review-cases.csv"})

    @app.get("/api/exports/batch.csv")
    def batch_export(store: ReviewStore = Depends(get_store)) -> StreamingResponse:
        return StreamingResponse(iter([store.export_batch()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=directory-review-batch.csv"})

    return app


def run() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="Serve the local Directory Review Console API.")
    parser.add_argument("--sqlite", type=Path, default=database_path())
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(create_app(args.sqlite), host=args.host, port=args.port)


app = create_app()


if __name__ == "__main__":
    run()
