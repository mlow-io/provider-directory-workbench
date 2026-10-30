from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import __version__
from .storage import database_path, connect
from .normalize import normalize_address, normalize_phone, normalize_text


RemediationStatus = Literal[
    "new",
    "triaged",
    "approved",
    "pending_verification",
    "verified",
    "reopened",
    "deferred",
]
RemediationAction = Literal["triage", "approve", "submit", "verify", "defer"]

STATUSES = {
    "new",
    "triaged",
    "approved",
    "pending_verification",
    "verified",
    "reopened",
    "deferred",
}
RISK_LEVELS = {"high", "medium", "low"}


class RemediationCaseItem(BaseModel):
    case_id: str
    listing_id: str
    reference_provider_key: str
    field_name: str
    status: RemediationStatus
    risk_level: str
    active_proposed_correction_value: str | None
    updated_at: str


class RemediationCasePage(BaseModel):
    items: list[RemediationCaseItem]
    total: int


class PhaseOneEvidence(BaseModel):
    values: dict[str, str | int | float | bool | None]


class RemediationEvent(BaseModel):
    event_id: int
    case_id: str
    event_type: str
    from_status: RemediationStatus | None
    to_status: RemediationStatus
    actor: str
    reason: str
    proposed_correction_value: str | None
    original_payer_value: str | None
    reference_value: str | None
    submission_reference: str | None
    submitted_at: str | None
    observed_payer_value: str | None
    verification_evidence_note: str | None
    occurred_at: str


class RemediationCaseDetail(BaseModel):
    case: RemediationCaseItem
    evidence: PhaseOneEvidence
    history: list[RemediationEvent]


class RemediationTransitionInput(BaseModel):
    action: RemediationAction
    actor: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=500)
    proposed_correction_value: str | None = Field(default=None, max_length=2_000)
    submission_reference: str | None = Field(default=None, max_length=500)
    observed_payer_value: str | None = Field(default=None, max_length=2_000)
    verification_evidence_note: str | None = Field(default=None, max_length=2_000)


class RemediationTransitionResult(BaseModel):
    case: RemediationCaseItem
    event: RemediationEvent


class RemediationStore:
    """Append-only human workflow over immutable Phase 1 discrepancy evidence."""

    def __init__(self, sqlite_path: Path) -> None:
        self.sqlite_path = sqlite_path

    def connect(self) -> sqlite3.Connection:
        if not self.sqlite_path.exists():
            raise HTTPException(
                status_code=503,
                detail=(
                    "Payer discrepancy evidence is unavailable. Run `make demo` or run the "
                    "pipeline with an explicit --payer-listings file before starting the remediation API."
                ),
            )
        conn = connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def rows(
        conn: sqlite3.Connection, query: str, params: tuple[object, ...] = ()
    ) -> list[dict[str, object]]:
        return [dict(row) for row in conn.execute(query, params).fetchall()]

    @staticmethod
    def case_id(listing_id: str, reference_provider_key: str, field_name: str) -> str:
        """Stable identity deliberately excludes payer and reference values and risk."""
        seed = "|".join(("payer-remediation-v1", listing_id, reference_provider_key, field_name))
        return f"remediation_{hashlib.sha256(seed.encode()).hexdigest()[:16]}"

    def initialize(self) -> None:
        with self.connect() as conn:
            available = {
                str(row[0])
                for row in conn.execute("select name from sqlite_master where type = 'table'")
            }
            has_phase_one_evidence = "payer_directory_discrepancies" in available
            if not has_phase_one_evidence and "remediation_case" not in available:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Payer discrepancy evidence is unavailable. Supply --payer-listings when "
                        "running the pipeline; arbitrary or public-NPI runs do not create remediation cases."
                    ),
                )
            conn.executescript(
                """
                create table if not exists remediation_case (
                    case_id text primary key,
                    listing_id text not null,
                    reference_provider_key text not null,
                    field_name text not null,
                    workflow_status text not null,
                    initial_risk_level text not null,
                    active_proposed_correction_value text,
                    evidence_snapshot text not null,
                    created_at text not null,
                    updated_at text not null,
                    unique (listing_id, reference_provider_key, field_name)
                );
                create table if not exists remediation_event (
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
                    occurred_at text not null,
                    foreign key(case_id) references remediation_case(case_id)
                );
                """
            )
            self.add_case_projection_columns(conn)
            if has_phase_one_evidence:
                self.synchronize(conn)
                self.backfill_missing_snapshots(conn)
            else:
                self.backfill_unavailable_legacy_snapshots(conn)
            self.backfill_active_proposals(conn)
            case_count = int(conn.execute("select count(*) from remediation_case").fetchone()[0])
            if not has_phase_one_evidence and case_count == 0:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Payer discrepancy evidence is unavailable. Supply --payer-listings when "
                        "running the pipeline; arbitrary or public-NPI runs do not create remediation cases."
                    ),
                )
            conn.commit()

    @staticmethod
    def add_case_projection_columns(conn: sqlite3.Connection) -> None:
        columns = {
            str(row["name"])
            for row in conn.execute("pragma table_info(remediation_case)").fetchall()
        }
        if "active_proposed_correction_value" not in columns:
            conn.execute(
                "alter table remediation_case add column active_proposed_correction_value text"
            )
        if "evidence_snapshot" not in columns:
            conn.execute("alter table remediation_case add column evidence_snapshot text")

    def synchronize(self, conn: sqlite3.Connection) -> None:
        """Insert a case once for each current field discrepancy; never delete workflow state."""
        discrepancies = self.rows(
            conn,
            """
            select *
            from payer_directory_discrepancies
            order by listing_id, provider_key, field_name
            """,
        )
        for discrepancy in discrepancies:
            listing_id = text_value(discrepancy["listing_id"])
            provider_key = text_value(discrepancy["provider_key"])
            field_name = text_value(discrepancy["field_name"])
            case_id = self.case_id(listing_id, provider_key, field_name)
            now = utc_now()
            conn.execute(
                """
                insert or ignore into remediation_case
                (case_id, listing_id, reference_provider_key, field_name, workflow_status,
                 initial_risk_level, active_proposed_correction_value, evidence_snapshot,
                 created_at, updated_at)
                values (?, ?, ?, ?, 'new', ?, null, ?, ?, ?)
                """,
                (
                    case_id,
                    listing_id,
                    provider_key,
                    field_name,
                    text_value(discrepancy["risk_level"]),
                    evidence_snapshot(discrepancy),
                    now,
                    now,
                ),
            )

    def backfill_missing_snapshots(self, conn: sqlite3.Connection) -> None:
        cases = self.rows(
            conn,
            """
            select * from remediation_case where evidence_snapshot is null
            """,
        )
        for case in cases:
            evidence = conn.execute(
                """
                select * from payer_directory_discrepancies
                where listing_id = ? and provider_key = ? and field_name = ?
                """,
                (case["listing_id"], case["reference_provider_key"], case["field_name"]),
            ).fetchone()
            if evidence is not None:
                conn.execute(
                    """
                    update remediation_case set evidence_snapshot = ?
                    where case_id = ? and evidence_snapshot is null
                    """,
                    (evidence_snapshot(dict(evidence)), case["case_id"]),
                )

    def backfill_unavailable_legacy_snapshots(self, conn: sqlite3.Connection) -> None:
        for case in self.rows(
            conn, "select * from remediation_case where evidence_snapshot is null"
        ):
            conn.execute(
                """
                update remediation_case set evidence_snapshot = ?
                where case_id = ? and evidence_snapshot is null
                """,
                (evidence_snapshot(legacy_evidence_snapshot(case)), case["case_id"]),
            )

    def backfill_active_proposals(self, conn: sqlite3.Connection) -> None:
        cases = self.rows(
            conn,
            """
            select * from remediation_case
            where active_proposed_correction_value is null
            """,
        )
        for case in cases:
            event = conn.execute(
                """
                select proposed_correction_value from remediation_event
                where case_id = ? and event_type = 'approve'
                order by event_id desc limit 1
                """,
                (case["case_id"],),
            ).fetchone()
            if event is not None and event["proposed_correction_value"] is not None:
                conn.execute(
                    """
                    update remediation_case set active_proposed_correction_value = ?
                    where case_id = ? and active_proposed_correction_value is null
                    """,
                    (event["proposed_correction_value"], case["case_id"]),
                )

    @staticmethod
    def evidence(case: dict[str, object]) -> dict[str, object]:
        snapshot = case.get("evidence_snapshot")
        if not snapshot:
            return legacy_evidence_snapshot(case)
        try:
            values = json.loads(str(snapshot))
        except json.JSONDecodeError as error:
            raise HTTPException(status_code=409, detail="Stored remediation evidence snapshot is invalid.") from error
        if not isinstance(values, dict):
            raise HTTPException(status_code=409, detail="Stored remediation evidence snapshot is invalid.")
        return values

    @staticmethod
    def case_item(case: dict[str, object]) -> RemediationCaseItem:
        return RemediationCaseItem(
            case_id=text_value(case["case_id"]),
            listing_id=text_value(case["listing_id"]),
            reference_provider_key=text_value(case["reference_provider_key"]),
            field_name=text_value(case["field_name"]),
            status=text_value(case["workflow_status"]),
            risk_level=text_value(case["initial_risk_level"]),
            active_proposed_correction_value=(
                text_value(case.get("active_proposed_correction_value"))
                if case.get("active_proposed_correction_value") is not None
                else None
            ),
            updated_at=text_value(case["updated_at"]),
        )

    def list_cases(
        self,
        status: str | None,
        risk_level: str | None,
        listing_id: str | None,
        field_name: str | None,
        limit: int,
        offset: int,
    ) -> RemediationCasePage:
        self.initialize()
        if status and status not in STATUSES:
            raise HTTPException(status_code=422, detail="Unsupported remediation status.")
        if risk_level and risk_level not in RISK_LEVELS:
            raise HTTPException(status_code=422, detail="Unsupported remediation risk level.")
        filters: list[str] = []
        params: list[object] = []
        for column, value in (
            ("workflow_status", status),
            ("initial_risk_level", risk_level),
            ("listing_id", listing_id),
            ("field_name", field_name),
        ):
            if value:
                filters.append(f"{column} = ?")
                params.append(value)
        where = f"where {' and '.join(filters)}" if filters else ""
        with self.connect() as conn:
            count = int(conn.execute(f"select count(*) from remediation_case {where}", tuple(params)).fetchone()[0])
            cases = self.rows(
                conn,
                f"""
                select * from remediation_case {where}
                order by case_id
                limit ? offset ?
                """,
                tuple(params + [limit, offset]),
            )
        return RemediationCasePage(items=[self.case_item(case) for case in cases], total=count)

    def find_case(self, case_id: str) -> tuple[dict[str, object], sqlite3.Connection]:
        self.initialize()
        conn = self.connect()
        case = conn.execute("select * from remediation_case where case_id = ?", (case_id,)).fetchone()
        if case is None:
            conn.close()
            raise HTTPException(status_code=404, detail="Remediation case not found.")
        return dict(case), conn

    def history(self, conn: sqlite3.Connection, case_id: str) -> list[RemediationEvent]:
        return [
            RemediationEvent(**clean_values(row))
            for row in self.rows(
                conn,
                "select * from remediation_event where case_id = ? order by event_id",
                (case_id,),
            )
        ]

    def detail(self, case_id: str) -> RemediationCaseDetail:
        case, conn = self.find_case(case_id)
        try:
            return RemediationCaseDetail(
                case=self.case_item(case),
                evidence=PhaseOneEvidence(values=clean_values(self.evidence(case))),
                history=self.history(conn, case_id),
            )
        finally:
            conn.close()

    def event_history(self, case_id: str) -> list[RemediationEvent]:
        case, conn = self.find_case(case_id)
        try:
            return self.history(conn, text_value(case["case_id"]))
        finally:
            conn.close()

    def transition(
        self, case_id: str, payload: RemediationTransitionInput
    ) -> RemediationTransitionResult:
        case, conn = self.find_case(case_id)
        try:
            actor = required(payload.actor, "actor")
            reason = required(payload.reason, "reason")
            current = text_value(case["workflow_status"])
            action_rules: dict[str, tuple[set[str], str]] = {
                "triage": ({"new", "reopened", "deferred"}, "triaged"),
                "approve": ({"triaged"}, "approved"),
                "submit": ({"approved"}, "pending_verification"),
                "verify": ({"pending_verification"}, "verified"),
                "defer": ({"new", "triaged", "reopened"}, "deferred"),
            }
            allowed, target = action_rules[payload.action]
            if current not in allowed:
                raise HTTPException(
                    status_code=409,
                    detail=f"Cannot {payload.action} a {current} remediation case.",
                )

            evidence = self.evidence(case)
            proposed_value: str | None = None
            original_payer_value: str | None = None
            reference_value: str | None = None
            submission_reference: str | None = None
            submitted_at: str | None = None
            observed_payer_value: str | None = None
            verification_note: str | None = None
            event_type = payload.action

            if payload.action == "approve":
                proposed_value = required(payload.proposed_correction_value, "proposed_correction_value")
                original_payer_value = text_value(evidence.get("listing_value"))
                reference_value = text_value(evidence.get("reference_value"))
            elif payload.action == "submit":
                submission_reference = required(payload.submission_reference, "submission_reference")
                submitted_at = utc_now()
            elif payload.action == "verify":
                observed_payer_value = required(payload.observed_payer_value, "observed_payer_value")
                verification_note = required(
                    payload.verification_evidence_note, "verification_evidence_note"
                )
                approved_value = text_value(case.get("active_proposed_correction_value"))
                if not approved_value:
                    raise HTTPException(
                        status_code=409,
                        detail="A pending-verification case requires an approved proposed correction value.",
                    )
                if comparison_value(text_value(case["field_name"]), observed_payer_value) != comparison_value(
                    text_value(case["field_name"]), approved_value
                ):
                    event_type = "reopen"
                    target = "reopened"

            now = utc_now()
            conn.execute(
                """
                update remediation_case
                set workflow_status = ?,
                    active_proposed_correction_value = coalesce(?, active_proposed_correction_value),
                    updated_at = ?
                where case_id = ?
                """,
                (target, proposed_value, now, case_id),
            )
            cursor = conn.execute(
                """
                insert into remediation_event
                (case_id, event_type, from_status, to_status, actor, reason,
                 proposed_correction_value, original_payer_value, reference_value,
                 submission_reference, submitted_at, observed_payer_value,
                 verification_evidence_note, occurred_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    case_id,
                    event_type,
                    current,
                    target,
                    actor,
                    reason,
                    proposed_value,
                    original_payer_value,
                    reference_value,
                    submission_reference,
                    submitted_at,
                    observed_payer_value,
                    verification_note,
                    now,
                ),
            )
            conn.commit()
            updated = dict(
                conn.execute("select * from remediation_case where case_id = ?", (case_id,)).fetchone()
            )
            event = clean_values(
                dict(conn.execute("select * from remediation_event where event_id = ?", (cursor.lastrowid,)).fetchone())
            )
            return RemediationTransitionResult(
                case=self.case_item(updated), event=RemediationEvent(**event)
            )
        finally:
            conn.close()


def required(value: str | None, field_name: str) -> str:
    if value is None or not value.strip():
        raise HTTPException(status_code=422, detail=f"{field_name} is required.")
    return value.strip()


def comparison_value(field_name: str, value: str) -> str:
    if field_name == "phone":
        return normalize_phone(value)
    if field_name == "address":
        return normalize_address(value)
    if field_name in {"provider_name", "specialty", "city"}:
        return normalize_text(value)
    if field_name == "state":
        return value.strip().upper()
    if field_name in {"accepting_new_patients", "status"}:
        return value.strip().lower()
    if field_name in {"npi", "zip"}:
        return value.strip().removesuffix(".0")[: 5 if field_name == "zip" else None]
    return value.strip()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def text_value(value: object) -> str:
    return "" if value is None else str(value).strip()


def clean_values(row: dict[str, object]) -> dict[str, str | int | float | bool | None]:
    cleaned: dict[str, str | int | float | bool | None] = {}
    for key, value in row.items():
        cleaned[key] = (
            None
            if value is None
            else value
            if isinstance(value, (str, int, float, bool))
            else str(value)
        )
    return cleaned


def evidence_snapshot(evidence: dict[str, object]) -> str:
    """Persist every available Phase 1 discrepancy column as immutable case evidence."""
    return json.dumps(clean_values(evidence), sort_keys=True, separators=(",", ":"))


def legacy_evidence_snapshot(case: dict[str, object]) -> dict[str, str | int | float | bool | None]:
    """Keep pre-snapshot cases inspectable without consulting mutable Phase 1 tables."""
    return {
        "listing_id": text_value(case.get("listing_id")),
        "provider_key": text_value(case.get("reference_provider_key")),
        "field_name": text_value(case.get("field_name")),
        "risk_level": text_value(case.get("initial_risk_level")),
        "snapshot_status": "legacy_evidence_unavailable_when_snapshot_migrated",
    }


def create_remediation_app(
    sqlite_path: Path | None = None,
) -> FastAPI:
    app = FastAPI(title="Directory Remediation API", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    store = RemediationStore(sqlite_path or database_path())

    def get_store() -> RemediationStore:
        return store

    @app.get("/api/remediation/health")
    def health(_: RemediationStore = Depends(get_store)) -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/remediation/cases", response_model=RemediationCasePage)
    def cases(
        store: RemediationStore = Depends(get_store),
        status: str | None = None,
        risk_level: str | None = None,
        listing_id: str | None = None,
        field_name: str | None = None,
        limit: int = Query(default=100, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> RemediationCasePage:
        return store.list_cases(status, risk_level, listing_id, field_name, limit, offset)

    @app.get("/api/remediation/cases/{case_id}", response_model=RemediationCaseDetail)
    def case_detail(
        case_id: str, store: RemediationStore = Depends(get_store)
    ) -> RemediationCaseDetail:
        return store.detail(case_id)

    @app.get("/api/remediation/cases/{case_id}/history", response_model=list[RemediationEvent])
    def case_history(case_id: str, store: RemediationStore = Depends(get_store)) -> list[RemediationEvent]:
        return store.event_history(case_id)

    @app.post(
        "/api/remediation/cases/{case_id}/transitions",
        response_model=RemediationTransitionResult,
    )
    def transition(
        case_id: str,
        payload: RemediationTransitionInput,
        store: RemediationStore = Depends(get_store),
    ) -> RemediationTransitionResult:
        return store.transition(case_id, payload)

    return app


def run() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="Serve the local Directory Remediation API.")
    parser.add_argument(
        "--sqlite", type=Path, default=database_path()
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    uvicorn.run(create_remediation_app(args.sqlite), host=args.host, port=args.port)


app = create_remediation_app()


if __name__ == "__main__":
    run()
