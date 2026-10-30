# Operations Workflow

This document explains the bounded healthcare data-cleanup workflow.

The durable 2.0 operator journey is documented in the [five-minute procedure](operations_governance/sop_provider_remediation.md): receive CSV/XLSX/JSON or a bounded public response, map and quarantine, explicitly accept, review scoped identities, then approve/submit/verify corrections with retained evidence. The sections below document the preserved legacy CSV/current-batch pipeline and its payer-precedence comparison boundary. See the [API](API_REFERENCE.md) and [data dictionary](DATA_DICTIONARY.md) for the distinct durable intake contract.

## Scenario

A small healthcare operations firm receives provider directory exports from several sources:

- an NPPES-like public export,
- a payer directory,
- a clinic directory,
- a health-system roster.

The client wants to know which records are trustworthy enough for downstream reporting and which records need human review.

## Input

The input is a CSV with fields such as:

- record ID,
- NPI,
- provider name,
- specialty,
- address,
- city,
- state,
- ZIP,
- phone,
- accepting-new-patients status,
- source,
- active/inactive status,
- last verified date.

## Normalize

The pipeline standardizes:

- column names,
- phone digits,
- provider names,
- addresses,
- city names,
- state values,
- ZIP codes,
- dates.

Normalization does not mean the record is correct. It only means the fields are shaped consistently enough to compare and validate.

## Validate

The rules in `config/qa_rules.yml` check:

- missing required fields,
- invalid or missing phone number,
- inactive or unknown status,
- missing verification date,
- stale verification date,
- invalid accepting-new-patients value.

Each failed rule becomes an exception row.

## Detect Duplicate Candidates

Duplicate candidates are grouped by normalized provider name, normalized address, normalized city, and state. This is intentionally conservative. It is good enough to identify suspicious duplicates, but final merge decisions should be made by a reviewer.

## Verify Synthetic Payer Listings (Phase 1)

The loop runs only when a payer-listing CSV is explicitly supplied. `make demo` supplies the committed, clearly labeled synthetic payer-directory listing file; custom and public-NPI runs remain QA-only unless the caller supplies a payer file. It does not alter the source export or normalized provider records.

For each payer listing field, the pipeline:

1. uses the payer listing's explicit `reference_provider_key` crosswalk to locate source evidence, independently of the payer-published NPI;
2. records one high-risk listing-identity finding if that key is unmatched, without emitting field comparisons for that listing;
3. selects the first nonblank field value using configured, field-specific source precedence for matched listings;
4. compares normalized payer and reference values so harmless phone or address formatting differences do not become discrepancies; and
5. labels a mismatch or missing payer value as high, medium, or low risk while preserving individual `reference_unavailable` fields as evidence only.

The precedence has deliberately different semantics by field. NPPES-like data is preferred for NPI and provider legal identity. Clinic and health-system sources are preferred for operating location, phone, availability, status, and specialty because they are closer to active operations; payer data is a lower-priority fallback. Verification date remains a QA freshness control and is not compared in this Phase 1 loop because source-specific verification semantics have not yet been defined.

The result is a deterministic verification queue. It does not correct a field, publish a listing, or change a source, normalized, or payer record.

## Remediate Matched Field Discrepancies (Phase 2)

The local remediation API creates one workflow case for each row in `payer_directory_discrepancies`; unmatched listing identities remain a separate identity finding and do not become correction cases. The deterministic case identifier is derived only from the stable listing ID, reference-provider key, and field name. Synchronization inserts newly detected cases but never removes workflow state, appends duplicate cases, or changes event history.

`remediation_case` is the current-state projection and `remediation_event` is the append-only audit record. Each transition requires a nonblank human reason and an explicit actor value. The actor value documents who asserted the action in this local demo; it is not an authentication claim. The only transitions are:

1. `new → triaged → approved → pending_verification → verified`;
2. `pending_verification → reopened → triaged` when verification still observes a mismatch; and
3. `new`, `triaged`, or `reopened → deferred → triaged`.

When first inserted, each case snapshots the complete discrepancy evidence required for review; details and approvals use that immutable snapshot rather than a later mutable Phase 1 output row. Approval records a proposed correction plus the payer and selected-reference values from the snapshot, and stores the proposal as the case's active value. Submission requires a payer submission reference and receives a server timestamp. Verification requires the observed payer value and an evidence note, then compares normalized values to the active approved proposal—not automatically to the original reference. A normalized observed proposal match verifies the case; a mismatch appends a `reopen` event and preserves the observed mismatch. Reapproval updates only the current projection while every earlier proposal remains append-only event history. Existing cases therefore remain inspectable through changed, removed, or QA-only pipeline outputs. Phase 3 presents this same bounded workflow in the local console, separating stored evidence, human judgment, and observed payer verification. It remains human-controlled: there is no automatic correction, payer writeback, bulk action, FHIR exchange, or authentication.

## Export

The pipeline writes:

- normalized provider records,
- provider directory exceptions,
- duplicate candidates,
- quality summary,
- Excel review workbook,
- operations review memo,
- SQLite review database,
- payer listings, source-precedence, reference-value, comparison, discrepancy, and risk-summary artifacts.

## Review

An operations reviewer would use the exception report to:

1. Fix high-severity missing fields.
2. Review duplicate candidates.
3. Re-verify stale records.
4. Identify source systems producing recurring issues.
5. Track cleanup status over time.

The exception report includes workflow fields:

- `review_status` starts as `new`.
- `assigned_to` starts as `unassigned`.
- `recommended_action` tells the reviewer what kind of follow-up is likely needed.
- `priority_rank` lets the reviewer sort the queue.

## Operational Rationale

Many healthcare data jobs do not begin with advanced modeling. They begin with:

- messy exports,
- missing fields,
- inconsistent source systems,
- stakeholder questions,
- manual cleanup,
- exception reports,
- repeatable weekly/monthly workflows.

The pipeline implements that operational layer directly.

## Current operational boundaries

The legacy pipeline receives several synthetic sources in one harmonized CSV. Its generated evidence is replaced on rerun; compatibility QA detail relies on the current batch. The durable Intake Workbench separately provides receipts, original artifacts, mapping/acceptance and later observations. Its synthetic sample picker uses that same intake service. Payer remediation and durable work preserve their own initial evidence and human history.

The October missing-NPI/leading-zero ZIP and source-update-as-verification defects now have fixes and regression tests. Normalization still does not establish the accuracy of source evidence. The [dated review](INTAKE_2_0_REVIEW.md) preserves the original reproduction, with current dispositions and qualification linked separately.

Validation and browser runs own separate fixture roots; API startup never reseeds evidence. Preserve a working database and its matching artifact root together. Durable work exports use a read-only SQLite snapshot and include all or one selected case; the all-work workbook ignores UI filters. Exports do not accept, resolve, verify or change work. See the [workbook contract](DATA_DICTIONARY.md#durable-work-handoff-workbook).

## Recurring clinic deliveries

After reviewing a ready file preview, save its mapping revision with a name/reviewer/reason. On a new file in the same source scope, select that revision and apply it; acceptance remains a separate decision. Reordered columns are safe, extra source columns stay retained, and missing selected headers require renewed review.

Expand the accepted-delivery comparison to see the exact baseline, raw/unique counts and filterable old/new fields with locators. Inspect blocked/quarantined and unresolved rows separately. Missing means absent only. If acceptance reports a changed baseline, refresh comparison, review the new previous values and retry with an explanation. Original observations, ownership and human verification history remain intact through repeats/restarts. The [SQL selected-delivery tool](OPERATIONAL_SQL.md) still asks the operator to choose its two accepted attempts explicitly.
