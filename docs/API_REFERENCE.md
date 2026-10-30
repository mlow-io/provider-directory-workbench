# API reference: unified intake workbench and compatibility routes

Updated 2026-10-26. Start the unified application with `PYTHONPATH=src python3 -m provider_directory_truth_layer.intake_api`. It serves intake, durable work and compatibility review/remediation routes on port 8000. The standalone remediation module can still run on 8001 for compatibility.

The unified application reads durable intake/work and legacy generated SQLite evidence; standalone compatibility services retain their separate workflow tables. They do not authenticate operators, certify provider truth, contact payers, or alter normalized provider evidence. Pydantic validates declared types/constraints; models do not enable strict mode or forbid extra fields. Append-only history describes application behavior, not database tamper protection.


## Intake and durable work

All paths below use the same configured database/artifact root. There is no authentication; actor names are local assertions. JSON errors use `detail`; missing objects return 404, invalid inputs 422, and stale attempt/case versions 409. Multipart uploads are not used: send raw bytes with filename/source/designation/profile query parameters. Limit 10 MiB per artifact, 20,000 tabular rows; CSV/XLSX require explicitly mapped identity/address/phone fields. Validation/quarantine counts cover the full bounded artifact.

| Method | Path | Input / result |
| --- | --- | --- |
| GET | `/api/demo/samples` | Fixed synthetic sample catalog; empty items unless `PDTL_DEMO=1` (explicitly set by offline launcher). |
| POST | `/api/demo/samples/{sample_id}` | Allowed fixture only: `clinic-workbook`, `clinic-csv`, `clinic-changed`, `nppes`, `cms`. Normal retained intake receipt, always source `synthetic-demo`/designation `synthetic`. Disabled/unknown: 404. No file/URL parameter; no acceptance or verification. |
| GET | `/api/work-export.xlsx` | Read-only XLSX for all durable work, or exactly `?case_id=ID` (404 if absent). All-work ignores UI filters. Full linked evidence/events, related receipt attempts/repeats and payloads from one SQLite snapshot; no 50/200 UI cap. |
| POST | `/api/intakes/files` | Raw file body; query `filename`, `source=clinic`, `designation=synthetic|public|local`, `profile=flat|nppes|cms`. Retains receipt and preview, including visible parse failures. |
| GET | `/api/intakes` | `{items:[receipt summaries]}` newest first. |
| GET | `/api/intakes/{id}` | Receipt, metadata, attempts, preview, observations and linked cases. Interactive row/observation samples capped at 50; counts remain complete. |
| POST | `/api/intakes/{id}/mapping` | `{mapping:{canonical:original_header},sheet,header_row,encoding,delimiter}`; new attempt, including after an earlier commitment. |
| POST | `/api/intakes/{id}/commit` | `{expected_attempt,policy:"valid_rows"|"reject",actor,reason}`. Atomic acceptance; duplicate delivery reuses prior interpretation; stale attempt conflicts. |
| GET | `/api/intakes/{id}/artifact` | Exact retained original bytes. Reference-only links have none. |
| GET | `/api/intakes/{id}/quarantine` | Full CSV with locator, problems and original row JSON. |
| GET | `/api/intakes/{id}/packet` | Full JSON receipt/attempt/original/observation/case/history packet. |
| POST | `/api/intakes/lookups` | `{source:"nppes"|"cms",query:{number,city,state,limit,skip,offset},refresh:false}`. Connector-specific supported fields only; fifteen-minute retained-response reuse unless refresh requested. Failed responses remain receipts and HTTP 422 errors. |
| POST | `/api/intakes/links` | `{url,title,source,observed_at}`; asserted, unfetched reference receipt. |
| GET | `/api/sources` | Source health, bounded scope, metadata, last success/failure. |
| GET | `/api/work` | `{items:[work summaries]}` risk/overdue/age/ID order. UI filters over summaries and renders first 200 matches. |
| GET | `/api/work/{id}` | Immutable initial evidence, current projection/version, later observations, history. |
| POST | `/api/work/{id}/events` | Expected-version accountable event; returns updated detail. |
| POST | `/api/relationships` | `{observation_id,provider_id,location_id,actor,reason,location_index?}`; exact observed `NPI:...`; multi-address native records require a selected practice location index. |

The workbook sample selects header row 2 and provides `metadata.suggested_mapping`; loading suggested columns only edits the form. Save mapping and explicitly accept after review. Repeated samples retain byte identity across restart and reuse a previously committed interpretation through normal intake rules. Ordinary uploads remain available with demo mode disabled.

The XLSX [data contract](DATA_DICTIONARY.md#durable-work-handoff-workbook) defines sheet grains, shared-receipt context, snapshot consistency, literal-text safety, nulls and complete chunked payloads. Download filename is `durable-work-handoff.xlsx`; no case mutation occurs.

Mapping supports `npi`, `provider_name`, `address`, `city`, `state`, `zip`, `phone` (required) and optional `record_id`, `location_id`, `listing_id`, `reference_phone`, `specialty`, `status`, `source_updated_at`. An unmapped source-native ID remains unresolved. String-safe CSV and simple zero-formatted XLSX identifiers retain leading zeroes; formulas quarantine the row.

Work actions: `assign` requires owner; `needs_information` records a reason and optional follow-up; `triage` starts/resumes review; correction-only `approve` requires ten-digit phone proposal, `submit` requires simulated submission reference, `verify` requires observed phone and verification note. A match verifies; mismatch reopens. `defer` records deferral; QA-only `resolve` records disposition. All actions require nonblank actor/reason and exact `expected_version`; follow-up is YYYY-MM-DD. Blank optional inputs should be omitted to preserve the current projection.

Example correction event (substitute an actual case and version):

```json
{"action":"approve","expected_version":1,"actor":"demo-reviewer","reason":"Reviewed the synthetic clinic request at NORTH","proposal":"6175550199"}
```

Original source evidence is not updated by these routes. Relationship events append a crosswalk; they do not merge entities. No external correction occurs.

## Compatibility boundary

The sections below describe earlier generated-batch QA and payer-precedence APIs. They retain their original request/response contracts and IDs. New intake evidence and expected-version work use `/api/work`; compatibility QA remains current-batch and standalone compatibility transitions do not gain the new version protocol.

## Review service

Default origin: `http://127.0.0.1:8000`. Source: `src/provider_directory_truth_layer/review_api.py`.

| Method | Path | Result |
| --- | --- | --- |
| GET | `/api/health` | `{"status":"ok"}`; liveness only, not database readiness. |
| GET | `/api/batches/current` | `BatchSummary`. |
| GET | `/api/cases` | `CasePage`; all matching current-batch cases, no pagination. |
| GET | `/api/cases/{case_id}` | `CaseDetail`. |
| POST | `/api/cases/{case_id}/transitions` | `TransitionInput` -> `{case,event}`. |
| GET | `/api/exports/cases.csv` | Current filtered/sorted case-state CSV. |
| GET | `/api/exports/batch.csv` | One-row batch-summary CSV. |

List and case-export query parameters:

- `search`: case-insensitive substring in provider name, record ID, or issue code.
- `severity`, `issue_code`, `status`: exact filters. Unmatched strings yield no matching rows; these are not enum-validated query fields.
- `sort`: `priority` (default), `provider`, `issue_code`, `severity`, `status`, `owner`, `updated`.
- `direction`: `asc` (default), `desc`. Unsupported sort/direction returns 422.

There is no review `source`, `limit`, or `offset` filter. Current issue codes use lower snake case, for example `missing_required_field` and `possible_duplicate_provider_location`; see the [dictionary](DATA_DICTIONARY.md).

### Response shapes

`CasePage`: `items: CaseListItem[]`, `total: integer`.

`CaseListItem`: `case_id`, `record_id`, `provider_name`, `issue_code`, `severity`, `field_name`, `source`, `review_status`, nullable `assigned_to`, `updated_at`.

`BatchSummary`: `batch_id`, `source_label`, `record_count`, `exception_count`, `records_with_issues`, `issue_counts`, `severity_mix`, `source_summary`, `data_notice`, `limitations`. Batch IDs are `qa-` plus an evidence fingerprint; the current label is a static synthetic-sample label. Source-summary counts describe exception rows, not all provider records.

`CaseDetail` fields:

- `case`: `CaseListItem`.
- `exception`: `{values: {...}}`.
- `normalized_records`: array of `{values: {...}}`.
- `recommendation`, `explanation`, nullable `notes`.
- `history`: chronological `HistoryEvent[]`.
- `duplicate`: nullable `{candidate, records, warning}`, where candidate/records use the same values wrappers.

QA detail relies on source exceptions in the current generated batch. Preserved review events do not guarantee access to old source evidence after a changed pipeline output.

### Record a review action

Example body, sent to a case ID returned by the list endpoint:

```json
{
  "action": "assign",
  "assignee": "demo-reviewer",
  "reason": "Route to source confirmation",
  "note": "Confirm the clinic phone."
}
```

Declared inputs: required `action`, required `reason` length 3–500, optional `assignee` maximum 120, optional singular `note` maximum 2,000. There is no recorded actor or controlled reason code. QA checks truthiness for required assignee/note and does not consistently trim/reject whitespace.

| Action | Allowed current states | Next state |
| --- | --- | --- |
| `assign` | `new`, `assigned`, `in_review`, `deferred` | `assigned`; requires assignee. |
| `start_review` | `new`, `assigned`, `deferred`, `resolved` | `in_review`. |
| `resolve` | `in_review` | `resolved`. |
| `defer` | `new`, `assigned`, `in_review` | `deferred`. |
| `add_note` | All defined QA states | Same state; requires note. |

Response: `{case: CaseListItem, event: HistoryEvent}`. A history event has `event_id`, `event_type`, nullable `from_status`, nullable `to_status`, nullable `assigned_to`, `reason`, nullable `note`, and `occurred_at`.

Case CSV columns: `case_id,record_id,provider_name,issue_code,severity,status,assignee,updated_at`.

Batch CSV columns: `batch_id,source_label,record_count,exception_count,records_with_issues,data_notice,limitations`.

Neither CSV exports event history. `/api/export` is not an implemented endpoint.

## Remediation service

Default origin: `http://127.0.0.1:8001`. Source: `src/provider_directory_truth_layer/remediation_api.py`.

| Method | Path | Result |
| --- | --- | --- |
| GET | `/api/remediation/health` | Liveness response; does not validate evidence storage. |
| GET | `/api/remediation/cases` | `{items: RemediationCaseItem[], total: integer}`. |
| GET | `/api/remediation/cases/{case_id}` | `{case,evidence,history}`. |
| GET | `/api/remediation/cases/{case_id}/history` | Chronological `RemediationEvent[]`. |
| POST | `/api/remediation/cases/{case_id}/transitions` | `{case,event}`. |

List filters: optional `status`, `risk_level`, `listing_id`, `field_name`. `limit` defaults to 100, range 1–100; `offset` defaults to 0, minimum 0. Results order by case ID; total counts matching cases before pagination. Unsupported nonblank status/risk returns 422. Listing/field filters are exact strings.

`RemediationCaseItem`: `case_id`, `listing_id`, `reference_provider_key`, `field_name`, `status`, `risk_level`, nullable `active_proposed_correction_value`, `updated_at`.

Detail contains `case: RemediationCaseItem`, `evidence: {values: {...}}`, and `history`. Evidence includes the initial discrepancy, selected source/record, comparison values, risk, and precedence. Legacy snapshots can identify unavailable original evidence with `snapshot_status=legacy_evidence_unavailable_when_snapshot_migrated`.

### Record a remediation action

Example approval body after triage:

```json
{
  "action": "approve",
  "actor": "demo-reviewer",
  "reason": "Synthetic clinic evidence supports this phone correction",
  "proposed_correction_value": "615-555-0101"
}
```

Required common fields: `action`, `actor` (1–120), `reason` (1–500). Actor/reason must remain nonblank after trimming. Optional action-specific fields are `proposed_correction_value` (maximum 2,000), `submission_reference` (500), `observed_payer_value` (2,000), and `verification_evidence_note` (2,000).

| Action | Allowed current states | Required extra fields / next state |
| --- | --- | --- |
| `triage` | `new`, `reopened`, `deferred` | `triaged`. |
| `approve` | `triaged` | Proposal -> `approved`. |
| `submit` | `approved` | Submission reference -> `pending_verification`. Records evidence; sends nothing externally. |
| `verify` | `pending_verification` | Observed value and verification note -> `verified` on normalized proposal match, otherwise `reopened`. |
| `defer` | `new`, `triaged`, `reopened` | `deferred`. |

`reopen` is the event produced by failed verification, not an accepted action. Verification compares with the active approved proposal, not automatically the original reference. Each case keeps its initial evidence even after later comparison outputs change.

`RemediationEvent`: `event_id`, `case_id`, `event_type`, `from_status`, `to_status`, `actor`, `reason`, `proposed_correction_value`, `original_payer_value`, `reference_value`, `submission_reference`, `submitted_at`, `observed_payer_value`, `verification_evidence_note`, `occurred_at`. Action-specific evidence fields can be null.

## Errors and verification limits

Explicit application errors use FastAPI's `{"detail":"..."}`; request-validation errors use a `detail` array. RFC 7807 conformance is not implemented.

- 422: invalid request values, required action evidence, or unsupported validated filters/sort.
- 409: disallowed state transition, invalid stored remediation snapshot, or missing active proposal for verification.
- 404: absent case or a QA case whose source exception is not in current output.
- 503: missing/incomplete prerequisite evidence where handled by the service.

Not every storage failure has a custom response. Health endpoints establish liveness only. Compatibility case transitions do not include expected-version concurrency control; durable `/api/work` does. See [2.0 execution gates](INTAKE_2_0_EXECUTION.md) for the original implementation contract and [review](INTAKE_2_0_REVIEW.md) for baseline evidence.

## Recurring file intake (schema v3)

`GET /api/intakes/{receipt_id}/saved-mappings` lists immutable reviewed revisions for that receipt's source/profile/declared scope. `POST` to the same path requires `name`, `actor`, `reason`, and `expected_attempt`; it saves the current ready mapped tabular preview, including parsing settings and selected required headers. It does not accept any rows. Each returned revision has an opaque `id`, source/profile/scope, settings, required headers and accountable creation fields. Revisions cannot be edited or deleted.

Apply with `POST /api/intakes/{receipt_id}/mapping` and `{"mapping_revision_id":"ID"}`. Settings cannot override a saved revision; review manual columns and save another revision instead. Reordered columns and extra unmapped headers are permitted. Missing selected headers yields `needs_mapping` with an explained error and blocks acceptance. The original always retains unknown columns. Source/profile/scope mismatches return 422.

Tabular previews now pin a single latest committed delivery for the same source/profile/declared scope. `preview.comparison.baseline` gives its attempt/receipt/label/acceptance time/mapping revision, or null. Comparison includes raw-row and unique-identity counts and new/changed/unchanged/unresolved/blocked-invalid/missing counts, plus entries with old/new fields and both row locators. Duplicate record/location keys quarantine every copy. Known-key invalid rows block a baseline key; unresolved rows cannot conceal absence. New/changed/unchanged describes valid unique rows only. Mapping reinterpretation is labeled separately.

The commit endpoint still requires `expected_attempt`, actor/reason and explicit valid-row/reject policy. Under the acceptance transaction it rechecks the pinned baseline; an intervening committed delivery returns 409 (`Accepted baseline changed...`). Refresh mapping/comparison and review before retrying. A duplicate delivery reuses the earlier accepted interpretation and does not advance the baseline. Later source evidence never changes human review status. Interactive rows/comparison entries are bounded to 50 with `entry_count`; downloaded evidence packets retain all entries/attempts. Native public JSON comparisons retain their earlier reference-evidence semantics.

## Organization/network intake (schema v4)

`GET /api/catalog` returns organizations, networks, locations and all reviewed source bindings, including which revision is current. `POST /api/catalog/organizations` requires label, kind (`payer`, `clinic`, `group`, `health_system`, `other`), actor/reason; optional identifiers are a list of issuing namespace/text value objects. Network creation (`POST /api/catalog/networks`) accepts label, optional payer organization ID, identifiers and actor/reason. Practice-location creation (`POST /api/catalog/locations`) accepts label, optional organization ID and actor/reason. IDs are opaque; equal labels create distinct records. Missing owners remain null; a network owner must be an explicitly selected payer. These operations neither import nor accept data.

`POST /api/catalog/bindings` requires source, kind (`network`, `organization`, `location`), exact source_key, existing target_id, actor/reason and expected_binding_id (null for a first binding). Replacing a binding appends a revision; stale expected IDs return 409. Earlier revisions and target references remain immutable. No provider/location/network identity is inferred from a display label.

Existing file upload optionally accepts `dataset_scope`, `completeness` (`unknown`, `bounded`, `full`) and `as_of` (YYYY-MM-DD). These remain receipt metadata; declared completeness and as-of dates never prove termination or effective dates.

For mapped network files, existing mapping POST additionally accepts roster_kind=`network`, typed `bindings` maps (`network`, `location`, `organization`, each exact source code → reviewed binding ID), and optional fixed_network_binding_id for an explicitly declared single-network scope. Mapping fields add network_code, organization_code, network_label, organization_label, participation_status, effective_date and end_date. The service stores a binding snapshot in the attempt specification/fingerprint. Saving a mapping revision retains this configuration; applying it remains revision-ID-only.

Every row needs a source-native participation key, provider NPI, explicit practice-location binding and network binding. A supplied organization code also requires a binding; absent organization stays unknown. Unbound identities, conflicting row/default networks, invalid dates and end-before-effective dates quarantine the row. Source-listed status is an assertion, separate from human review status. Contradictory fixed-network codes cannot hide a missing baseline record. Acceptance rechecks baseline and current binding revisions atomically; older bindings require renewed mapping review.

Comparison scope includes source/profile/declared dataset, roster kind and the explicitly configured local network set. Clinic and network deliveries, or different network sets, never share a baseline. Network identity includes native key, provider, practice location and network. Same bytes interpreted with changed reviewed bindings cannot silently reuse a different interpretation.

## Scoped network review and handoff

`GET /api/work` accepts exact optional network_id, organization_id and location_id filters. Items add network/organization/practice-location IDs and catalog labels; existing clinic items retain null network scope. `GET /api/work/{case_id}` adds the explicit scope and append-only participation_review evidence. These source comparisons are distinct from the human event history.

Accepted network deliveries retain missing/known-invalid comparison work as QA cases (`participation_missing` and `participation_validation`). Quarantined rows never become accepted participation observations. Unbound identities remain receipt quarantine without invented membership. Later evidence does not modify initial snapshots, owner, human status, version or events. Repeated interpretations do not duplicate this work. An explicitly full empty network snapshot with a prior accepted baseline can be accepted as absence evidence; an all-invalid nonempty file remains blocked. Absence never terminates participation.

`GET /api/work-export.xlsx` and `GET /api/work-export.json` export all durable work when unfiltered. Optional case_id or network_id selects one explicit scope; supplying both returns 422, unknown IDs return 404. The all-work download continues to ignore UI filters. JSON includes format_version=2 and an explicit scope/context notice. XLSX format 2 adds network columns and, when network work is included, Participations, Review evidence, Catalog and Bindings sheets. Operational rows and bindings/catalog references belong only to selected cases/network. Complete related receipt/attempt payloads are visibly labeled shared context and may contain other rows or interpretations; different declared datasets are not treated as repeats.

Both formats read one pinned read-only SQLite transaction without initializing/migrating a store or mutating artifacts/work. XLSX IDs, dates and formula-like values remain literal text; complete payloads use numbered JSON chunks. Effective/end/as-of dates, declared completeness, source status and human decisions retain their separate meanings. Full snapshots are independent of UI sample/render limits.
