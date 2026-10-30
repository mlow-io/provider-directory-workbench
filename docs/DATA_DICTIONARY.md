# Data Dictionary

Scope: current application contracts, updated 2026-10-26. The durable schema v4 is implemented below; the [2.0 proposal](INTAKE_2_0_PROPOSAL.md) preserves the original design intent.

Legacy generated QA/comparison tables are replaced by pipeline runs. Compatibility workflow tables persist separately, but general QA detail depends on the current batch. Legacy row IDs/provider keys are distinct from durable receipt and location identities.

## Input Fields

| Field | Meaning | Example |
| --- | --- | --- |
| `record_id` | Source record identifier used for review and traceability. | `REC-00001` |
| `npi` | National Provider Identifier. | `1234567890` |
| `provider_name` | Provider display name from the source. | `Sarah Patel MD` |
| `specialty` | Provider specialty or practice area. | `Cardiology` |
| `address` | Practice location street address. | `201 23rd Ave N Ste 400` |
| `city` | Practice location city. | `Nashville` |
| `state` | Practice location state. | `TN` |
| `zip` | Practice location ZIP code. | `37203` |
| `phone` | Public directory phone number. | `(615) 555-0101` |
| `accepting_new_patients` | Whether directory says provider accepts new patients. | `yes`, `no`, `unknown` |
| `source` | Source system or export name. | `payer directory` |
| `status` | Directory active/inactive status. | `active` |
| `last_verified_date` | Last known verification date. | `2026-03-15` |

## Synthetic Payer Listing Input

`data/raw/synthetic_payer_directory_listings.csv` is a deterministic, synthetic comparison input. It is used only when explicitly supplied and never replaces a source record.

| Field | Meaning | Example |
| --- | --- | --- |
| `listing_id` | Stable synthetic payer-listing identifier. | `PAYER-00001` |
| `reference_provider_key` | Explicit synthetic crosswalk key used to locate source-record evidence. | `npi:1234567890` |
| `npi` | NPI published by the payer listing; compared independently after crosswalk matching. | `1234567890` |
| `provider_name` through `status` | Directory fields compared field by field to the selected review reference. | `615-555-0181` |
| `last_verified_date` | Retained as payer-listing evidence but not compared until source-specific verification semantics are defined. | `2026-01-01` |

## Normalized Fields

| Field | Meaning |
| --- | --- |
| `phone_digits` | Phone number reduced to digits for validation and comparison. |
| `normalized_provider_name` | Uppercase, punctuation-light provider name used for simple matching. |
| `normalized_specialty` | Uppercase specialty value. |
| `normalized_address` | Uppercase address with common suffix normalization. |
| `normalized_city` | Uppercase city value. |

## Output Files

| File | Purpose |
| --- | --- |
| `normalized_provider_records.csv` | Cleaned and normalized provider records. |
| `provider_directory_exceptions.csv` | Row-level issues for operations review. |
| `duplicate_candidates.csv` | Potential provider/location duplicates for human review. |
| `quality_summary.csv` | Summary metrics by issue type and severity. |
| `operations_review_memo.md` | Plain-English review memo for stakeholders. |
| `provider_directory_review_pack.xlsx` | Excel workbook for nontechnical review with summary, exceptions, duplicates, normalized records, rules, and notes. |
| `provider_directory_truth_layer.sqlite3` | SQLite database containing the same review tables. |
| `synthetic_payer_directory_listings.csv` | Normalized copy of the explicit payer-listing input used in this run. |
| `payer_listing_identity_results.csv` | One matched or unmatched crosswalk outcome for every payer listing. |
| `field_source_precedence.csv` | Flattened configured ordering of preferred sources for every compared field. |
| `provider_field_reference_values.csv` | Selected nonblank field-level review reference, its source record, and precedence rank. |
| `payer_listing_field_comparisons.csv` | Complete listing-by-field evidence, including matches and unavailable references. |
| `payer_directory_discrepancies.csv` | Actionable subset of comparison rows with a mismatch or missing payer-listing value. |
| `directory_remediation_risk_summary.csv` | Counts of actionable discrepancies by configured risk level. |

## Directory Remediation and Verification Tables

These optional Phase 1 outputs are written to SQLite using the file names above as table names only when a payer-listing file is supplied. They are evidence tables; none is a provider-truth table or a remediation workflow table.

| Table / File | Required Fields | Contract |
| --- | --- | --- |
| `field_source_precedence` | `field_name`, `source`, `precedence_rank` | Lower rank wins when a nonblank source value is available. Precedence is configured separately for every comparison field. |
| `payer_listing_identity_results` | `listing_id`, `reference_provider_key`, `published_npi`, `identity_status`, `is_actionable`, `risk_level` | One crosswalk outcome per listing. An unmatched key is a high-risk listing-identity finding and has no field comparison rows. |
| `provider_field_reference_values` | `provider_key`, `field_name`, `reference_value`, `reference_source`, `reference_record_id`, `precedence_rank` | The selected review reference. `provider_key` is `npi:<NPI>` for valid NPIs and otherwise retains a record-specific key. |
| `payer_listing_field_comparisons` | `listing_id`, `provider_key`, `field_name`, `listing_value`, `reference_value`, `comparison_status`, `is_discrepancy`, `risk_level`, `risk_reason` | Complete evidence; values are compared in normalized form while raw display values remain inspectable. |
| `payer_directory_discrepancies` | All comparison fields above | Contains only `discrepancy` and `listing_missing` statuses. It is an input to later review, not an instruction to overwrite data. |
| `directory_remediation_risk_summary` | `risk_level`, `field_discrepancy_count`, `unmatched_listing_count`, `total_actionable_findings` | Stable high, medium, and low rollup for operational triage. |

`comparison_status` is one of `match`, `discrepancy`, `listing_missing`, or `reference_unavailable`. Only `discrepancy` and `listing_missing` have `is_discrepancy=true`. `identity_status` is `matched_reference_provider` or `unmatched_reference_provider`; only the latter is an actionable identity finding. Actionable rows receive a configured `high`, `medium`, or `low` risk; `match` is `none`, and `reference_unavailable` is `unverified`. Verification date is intentionally absent from the comparison contract until source-specific semantics are defined.

## Payer Remediation Workflow Tables

The local remediation API reads `payer_directory_discrepancies` as immutable Phase 1 evidence and adds the following separate workflow tables. It does not update provider, normalized, source, payer-listing, or Phase 1 evidence tables. These tables exist only after the remediation API initializes against SQLite output produced with an explicit payer-listing input.

| Table | Required Fields | Contract |
| --- | --- | --- |
| `remediation_case` | `case_id`, `listing_id`, `reference_provider_key`, `field_name`, `workflow_status`, `initial_risk_level`, `active_proposed_correction_value`, `evidence_snapshot`, timestamps | Current workflow projection. `case_id` is a deterministic hash of the stable listing ID, reference-provider key, and field name, excluding mutable values and risk. `evidence_snapshot` is the complete discrepancy row captured only when the case is first inserted; synchronization never replaces it. `active_proposed_correction_value` is updated only by approval or reapproval. There is at most one case for each identity. |
| `remediation_event` | `event_id`, `case_id`, `event_type`, `from_status`, `to_status`, `actor`, `reason`, `occurred_at` | Append-only history. Approval additionally records `proposed_correction_value`, `original_payer_value`, and `reference_value`; submission records `submission_reference` and `submitted_at`; verification/reopen records `observed_payer_value` and `verification_evidence_note`. |

`workflow_status` is one of `new`, `triaged`, `approved`, `pending_verification`, `verified`, `reopened`, or `deferred`. Valid state changes are `new → triaged → approved → pending_verification → verified`, `pending_verification → reopened → triaged`, and `new`, `triaged`, or `reopened → deferred → triaged`. Every event requires a nonblank `actor` and `reason`; actor is an explicit local attribution value, not evidence of authentication. Verification compares normalized observed payer value to `active_proposed_correction_value`, not automatically to the snapshot's `reference_value`. `payer_listing_identity_results` rows with `unmatched_reference_provider` do not create remediation cases.

## Directory Review Console Tables

The local review console reads the QA tables above and adds only these workflow tables to the same generated SQLite database. It never updates the provider or QA source tables.

| Table | Purpose |
| --- | --- |
| `review_case` | Current review-state projection for an exception in a QA batch: case identifier, status, assignee, latest note, and timestamps. |
| `review_event` | Append-only assignment, review, resolution, defer, and note events. Each event records a reason, optional note, state transition, assignee, and timestamp. |

`review_case` is a read-optimized projection. `review_event` is the audit record used to reconstruct how a case reached its current review state.

General QA case IDs include a batch fingerprint and row index. Old detail queries current generated exceptions; a preserved event does not preserve its original source evidence. Remediation instead retains initial evidence snapshots. These compatibility endpoints do not use the new work-version protocol. Shared storage now explicitly enables per-connection foreign keys, WAL and busy timeout; the durable intake/work contract is below.

## Durable intake schema (version 2)

| Table | Grain / retained meaning |
| --- | --- |
| `artifact` | Exact-byte SHA-256, size, generated storage key. |
| `receipt` | Delivery, source namespace, designation, label, received time, artifact, profile, duplicate receipt, metadata. |
| `attempt` | Versioned mapping/parser specification, fingerprint, state, full preview/quarantine, creation/commit time, acceptance actor/reason/policy. |
| `observation` | Native record ID or unresolved null, original locator/payload, normalized interpretation, provider/location projection, retrieval/source-update/human-verification dates. |
| `relationship` | Audited exact-provider/operating-location crosswalk; optional native location index for multi-address evidence. |
| `work_case` | Stable scoped work identity, immutable initial evidence JSON, status/owner/follow-up/version, active proposal/observed value, explained priority. |
| `work_evidence` | Initial and later source-observation links, independent of current issue detection. |
| `work_event` | Append-only accountable actions and from/to state with exact payload. |
| `schema_migration` | Applied numbered migrations; `PRAGMA user_version` rejects future schemas. |

Artifact identity is not business identity. Identical source/artifact/specification reuses an interpretation while retaining another receipt. Changed mapping creates an attempt; changed/reordered source-native rows link to scoped work and retain original snapshots. Missing native identity remains unresolved. A bounded response's absence is only `missing_from_this_delivery`; no termination is inferred.

NPI supports provider identity, not operating location, enrollment or payer listing. Supplied location IDs are source-scoped; native multi-address records retain all locations and require explicit practice-address selection for crosswalks. CMS native composites retain enrollment/group/address grain. Phone discrepancies in the new workbench compare explicit listed and requested values at that location. Legacy provider-precedence comparisons remain a separate compatibility path.

`retrieved_at`, `source_updated_at`, source publication/modification metadata, and `human_verified_at` have distinct meanings. A source update never becomes human verification. Human correction verification is recorded in the work event and observed-value projection; it is not a write into provider evidence. CSV actual nulls stay blank; literal `NA` stays text; leading-zero identifiers remain strings. Simple XLSX all-zero numeric display formats are retained along with raw cell metadata; formula cells are quarantined.

## Exception Review Fields

| Field | Meaning |
| --- | --- |
| `review_status` | Workflow status for the issue. Defaults to `new`. |
| `assigned_to` | Reviewer owner. Defaults to `unassigned`. |
| `recommended_action` | Suggested next action derived from the issue type. |
| `priority_rank` | Numeric sort key derived from severity and issue type. Lower means higher priority. |

## Workbook Tabs

| Tab | Purpose |
| --- | --- |
| `Summary` | High-level record and issue metrics. |
| `Exceptions` | Review queue for data quality issues. |
| `Duplicates` | Possible provider/location duplicate candidates. |
| `Normalized Records` | Cleaned provider records after normalization. |
| `Rules` | Current QA configuration values. |
| `Review Notes` | Plain-English reviewer guidance. |
| `Payer Listings` | Normalized synthetic payer-directory listings used for deterministic comparison. |
| `Listing Identity` | One crosswalk match outcome per payer listing. |
| `Field Precedence` | Configured source rank for every comparison field. |
| `Reference Values` | Field-level selected reference evidence. |
| `Field Comparisons` | Complete payer-listing comparison evidence. |
| `Discrepancies` | Actionable payer-directory discrepancies only. |
| `Remediation Risk` | High, medium, and low discrepancy summary. |

## Issue Codes

| Issue Code | Meaning |
| --- | --- |
| `missing_required_field` | A required field such as NPI, specialty, address, city, state, or phone is blank. |
| `invalid_or_missing_phone` | Phone is missing or has too few digits. |
| `inactive_or_unknown_status` | Provider record is not marked active. |
| `missing_verification_date` | No last verification date exists. |
| `stale_verification` | Last verification date is older than the configured threshold. |
| `invalid_accepting_new_patients` | Accepting-new-patients value is not `yes`, `no`, or `unknown`. |
| `possible_duplicate_provider_location` | Multiple records share the same normalized provider/location key. |


## Durable work handoff workbook

`GET /api/work-export.xlsx` exports **all durable work**, irrespective of UI filters or the 200 rendered matches. Optional `case_id` exports exactly one case (404 if absent), all its linked initial/later observations, relationships and decision events. Legacy QA/remediation cases are excluded. Related receipt deliveries include matching source/profile/artifact repeats; their complete attempt previews can include rows outside the selected case. This is evidence context, not additional selected work.

The exporter opens SQLite in read-only/query-only mode, begins a transaction, and pins its snapshot with the first read. Every subsequent receipt/evidence/event read uses that connection and snapshot. Reads finish before XLSX rendering begins. `snapshot_at_utc` describes the pinned read, not a business event or source date. It writes no source, case, version, event or artifact. No schema migration is needed.

| Sheet | Content / grain |
| --- | --- |
| Read me | Format version 2, snapshot time, exact scope/count, value/date/null/safety conventions and limits. |
| Cases | One current work projection; explicit provider/NPI/location/native/listing identifiers, field, issue/risk, status, owner/follow-up/version, immutable initial listed/requested values, active approved proposal and latest observed value. |
| Evidence | One case/observation link, marked initial or later; source/designation/artifact, receipt/attempt/native IDs, row locator and location fields. Initial columns use the case's immutable selected practice-address snapshot. Later columns use the latest explicit relationship for that observation and the same provider/location scope, including its selected native address and locator. Separate native-observation identifiers/locator and payload retain the original multi-address grain. |
| Receipts | Related original/repeat delivery identifiers, labels, source/designation/profile, dates, digest and duplicate relationship. |
| Attempts | All attempts for included receipts, with mapping/preview/quarantine/acceptance retained in the payload. |
| Decisions | Every append-only work event, accountable actor/reason, from/to status/time, owner/follow-up inputs, proposal, simulated submission reference, observed result and verification note. |
| Relationships | Audited explicit native provider/location choices matching the exported case’s provider and location, including native location index and reviewer/reason. Other locations on a shared observation are not attributed to this case. |
| Payloads | Complete JSON for referenced case snapshots, native observations, receipts, attempts and events. Concatenate `json_chunk` by `payload_id`, ordering `part` numerically, then parse JSON. Long scalar displays reference `payload:ID`. |

Full export reads are not limited by the UI's 50 observation sample, eight visible preview rows or 200 rendered cases. Excel has a 1,048,576-row sheet limit; exceeding it returns a clear error suggesting selected-case export. Export is an in-memory local operation, not a large-scale reporting service.

All populated cells, including identifiers, dates and formula-like `=`, `+`, `-`, `@` strings, are literal text with no executable formulas or hyperlinks. Null displays as a blank cell; empty text displays as two quotes. JSON payloads preserve the exact distinction, types and originals. Prohibited XML controls in scalar displays are escaped. ASCII JSON is split into numbered chunks of at most 30,000 characters rather than silently hitting Excel's cell limit. The JSON payload is authoritative for exact values.

`listed_value` and `requested_value` are initial source assertions; `approved_value` is the current human proposal; `observed_value` may represent a failed verification. A populated observation does not imply verified status. Source update/retrieval/receipt dates do not establish human verification. Human verification actions, times and notes remain Decisions records; the original observation's `human_verified_at` is not rewritten by workflow review.

## Recurring interpretation revisions

`mapping_revision` stores one immutable reviewed source/profile/scope-specific template: opaque ID/name, effective column/parsing settings, required header names, actor/reason and creation time. Update/delete guards preserve every revision. Attempts retain their own immutable `spec` and fingerprint; accepting an attempt updates its state/decision, never its interpretation. Saving/applying a template is separate from acceptance.

For clinic files, longitudinal identity is source scope plus source-native `record_id` and supplied `location_id`; neither row number, bytes nor provider label is an identity. Every duplicate/conflicting key is quarantined. Preview counts distinguish raw rows and unique identities. A known invalid key is `blocked_invalid`; an unresolved row cannot suppress a baseline record's `missing` entry. The baseline is exactly one accepted attempt, never a union of latest keys from history. Its ID is pinned in `attempt.spec.baseline_attempt_id`, excluded from the interpretation fingerprint, and rechecked at acceptance. The mapping revision remains part of the fingerprint.

Schema migration 3 adds the mapping table/index/guards and immutable attempt-spec guard, preserving existing tables/IDs/history/artifact links. Existing v1/v2 databases receive a `.pre-intake-v3.bak` SQLite backup before this additive transaction; fresh databases apply migrations 1–3. Migration and rollback rehearsals use owned copies. Back up the database and matching artifacts together.

## Explicit organization/network records

| Table | Grain and contract |
| --- | --- |
| organization | One opaque local organization ID with label/kind, issuing-namespace identifiers and accountable creation. Labels are not identity. |
| network | One opaque payer-network ID, optionally referencing a known payer organization. Unknown owner remains null. |
| practice_location | One explicit local practice location, optionally linked to an organization. NPI alone never chooses a location. |
| identity_binding | One immutable reviewed source/kind/exact-key revision. Typed organization/network/location FKs and a kind CHECK require one valid target; previous revision and expected-current checks retain corrections without rewriting earlier evidence. |
| participation_observation | One accepted source assertion linked by observation_id. Native key, provider, local location, network, optional supplied organization, mapping revision, source-listed status, reported dates, binding snapshot and original labels remain separate. |
| case_scope | One new network-review case's explicit network/location/native-key scope, with supplied organization when known. Existing clinic case IDs are unchanged. |
| participation_review_evidence | One append-only comparison-evidence link to a case and processing attempt. Source comparison evidence is separate from human work events. |

Network longitudinal identity is source/dataset scope + native participation key + provider + explicitly bound practice location + network. Rows in different networks or at different locations cannot collide. Original source codes and as-imported labels stay in original/normalized payloads; binding corrections create new interpretations. The source-listed status/effective/end dates never establish human verification, licensing, credentialing or patient benefits. Invalid or contradictory dates quarantine the row.

Schema migration 4 adds these tables, typed FKs, scope index and immutable-record guards. It never backfills network membership for old rows or rebuilds existing cases. Existing databases are backed up with SQLite's backup API to `.pre-intake-v4.bak` before the transaction; migration rollback/integrity/FK and populated v3 preservation are rehearsed on owned copies. Keep each database with its matching artifact root.

## Network comparison evidence and scoped handoff

`participation_review_evidence` retains accepted-row source assertions and missing/known-invalid comparisons linked to processing attempt/receipt. A missing/validation case can have no accepted observation: its immutable initial snapshot explains the current receipt, baseline references and quarantined source row. It must not be presented as an accepted participation. Its source evidence appends separately from work_event, and later source data never changes human workflow automatically.

Network work items add explicit catalog scope and label fields. Case detail includes that scope and source-comparison history; review actions still use expected_version and append human events atomically. Missing and validation case identities use the same full participation scope plus finding kind. Unknown network/location/provider bindings remain quarantine, with no invented case membership.

Format 2 exports add network/organization/location labels to Cases. Network exports additionally contain Participations (case/accepted-observation link, source status/reported dates/receipt metadata), Review evidence (case/attempt/comparison row), Catalog (referenced organizations/networks/locations only) and Bindings (row bindings for the selected operational scope). All/case/network reads are consistent and non-mutating. Complete shared receipt/attempt payloads remain source context, not additional scoped operational rows. Related repeated-byte receipt discovery also checks declared dataset scope.

Shared writable connection contexts commit or roll back and then close deterministically; backup targets close explicitly too. Python's native SQLite context manager alone does not close a connection. Closing each completed request prevents retained connections/late WAL checkpoints; read-only exports and SQL queries still use their own explicitly closed snapshot connections.

Case scope and its organization filter describe the immutable initial work scope. Later source organization assertions remain separate evidence; selected handoffs include all catalog/binding references actually used by those accepted observations, without rewriting initial work scope.
