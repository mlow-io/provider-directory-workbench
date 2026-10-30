# Provider Directory Intake Workbench: 2.0 Proposal

Status: Accepted original 2.0 design specification, retained for traceability. Its implementation dispositions, measured limits and simplifications are recorded in DECISIONS.md, PROJECT_STATE.md and the evidence index. The [next-phase network roster plan](#proposed-next-phase-recurring-organization-and-network-rosters) below is proposed work, not an implemented capability or a reopening of the completed G0–G5 gates.

Reviewed: 2026-10-23. Baseline: `main` at `cad9765`.

Contributor guide: read the [execution guide](INTAKE_2_0_EXECUTION.md) and [progress checkpoint](INTAKE_2_0_PROGRESS.md) before coding. The [review](INTAKE_2_0_REVIEW.md) retains findings, reproduction, and screenshots in this repository; [product decisions](INTAKE_2_0_EXECUTION.md#product-decisions) summarize the scope.

## Product outcome

Extend the existing local provider-directory application into a dependable intake and reconciliation workbench. An operator can receive differently shaped files or supported public API results, preview their interpretation, retain their provenance, decide how identities relate, and work discrepancies through observed verification. Repeated deliveries preserve previous evidence and decisions.

The primary scenario is a clinic roster/change submission compared with directory observations at the correct provider and practice-location scope. Public-reference exploration is a separate, clearly labeled scenario; synthetic changes must never be presented as real discrepancies involving actual clinicians.

KPI-project integration is outside this proposal. Keep the existing Python, FastAPI, React/TypeScript, and SQLite application. Authentication, multitenancy, hosting, payer writeback, bulk case actions, full national replication, and automatic entity merging remain outside this release.

## Baseline assessment

Reusable capabilities:

- Configurable normalization and QA, conservative duplicate candidates, comparison exports, and an existing review console.
- Stable payer-remediation case keys, immutable initial evidence snapshots, active approved proposals, server-validated transitions, and append-only event history.
- Distinct proposal, submission-reference, observed-verification, and reopen paths.
- Existing Python, frontend, and browser scenario tests.

Source-backed gaps:

| Finding | Evidence | Consequence for 2.0 |
| --- | --- | --- |
| Main pipeline reads one already harmonized CSV | `src/provider_directory_truth_layer/pipeline.py:23` | Add explicit adapters, source contracts, and preview/accept workflow. |
| CSV inference loses identifier fidelity | `pipeline.py:23`, `normalize.py:66-73`, `qa.py:65-75` | A synthetic reproduction yielded blank NPI -> `"nan"`, ZIP `02108` -> `2108`, and zero QA exceptions. Fix before expanding input types. |
| Generated evidence tables replace their predecessors | `export.py:83-108` | Persist immutable intake observations; treat current exports as projections. |
| General QA case keys depend on batch and row index | `review_api.py:167-179`; old details query current exceptions at `:282-295` | Introduce stable work identity and retained case evidence. Keep legacy history identifiable. |
| NPI mapping uses positional IDs and labels source updates as verification | `npi_api.py:65-85` | Use source-native identity and separate retrieval, source update, and human verification timestamps. |
| References group at provider level | `remediation.py:161-166,311-324,337-341` | Require location scope before comparing operating address/phone. Multi-location mixing is a design risk identified from source, not a reproduced runtime failure. |
| Baseline architecture/governance/API docs overstated implementation | `docs/DECISIONS.md`, `docs/API_REFERENCE.md`, `docs/operations_governance/sop_provider_remediation.md` | Descriptions corrected in the documentation handoff. The underlying missing code controls remain open work; keep future claims aligned with implementation. |

Dated baseline checks on 2026-10-23: 31 Python tests passed; two frontend tests passed; frontend production build passed. An isolated synthetic run produced 12 normalized records, 10 QA exceptions, and six field discrepancies. Manual browser inspection covered the QA queue, QA case detail, and remediation evidence detail. Full browser E2E was not rerun; its default setup calls `make clean`, which removes runtime data. These are review results, not acceptance evidence for later code changes.

## Operator experience

Use one persistent navigation shell: **Intake**, **Work queue**, **Sources**. Keep QA dispositions and payer-correction transitions distinguishable within that shell; they express different business decisions.

### Intake inbox

- New intake offers file upload, supported public-source lookup, saved JSON, or evidence link.
- Each receipt shows source, filename/request label, received time, data designation, processing state, and counts.
- Distinguish parsing failure, needs mapping, preview ready, committed, and duplicate delivery. A valid file with review findings is not a failed import.
- Opening a receipt reveals its retained original artifact, processing attempts, mapping, accepted/quarantined rows, and created or linked work.

### Import preview

- CSV: explicit encoding/delimiter handling, original headers, sample rows, unknown columns, canonical mapping, and full bounded validation counts.
- XLSX: worksheet and header-row selection, mapped preview, original cell/row locators. Do not execute formulas; formula cells without usable cached values need explicit handling.
- Show required identity fields, source-native identifiers, missing-value handling, and how location scope is determined.
- Offer explicit acceptance of valid rows with a downloadable quarantine report, or rejection of the whole submission. Never silently discard bad rows.
- Record the mapping version and acceptance decision. Editing mapping after commitment creates another processing attempt rather than changing the old interpretation.
- For a later delivery in an established source scope, preview new, changed, and unchanged observations. Show missing observations as missing-from-this-delivery; infer removal only from an explicitly complete replacement scope.

### Work queue

- Columns: provider, location/listing, issue or requested change, source, risk and reason, owner, received age, next action, follow-up date.
- Initial filters: unassigned, selected local reviewer, needs information, overdue follow-up, and awaiting verification. Local reviewer names remain asserted identifiers, not authenticated users.
- Default ordering: risk, overdue follow-up, oldest receipt, stable case ID. Explain priority using business fields rather than an opaque score.
- Preserve query state in URLs and support keyboard row navigation, clear focus, loading, empty results, detail errors, and retry.
- Use a compact operational header so useful rows and case evidence appear sooner than in the current overview-heavy layout.

### Case workspace

- Present original source values, normalized observations, comparison reference, approved proposal, and observed verification separately.
- Link to the receipt and exact sheet/row or JSON locator for each piece of evidence.
- Keep original case evidence immutable; show newer observations in a dated comparison section.
- Distinguish potential identity match, confirmed relationship, and unresolved identity. No automatic provider merges.
- Preserve the existing correction flow: `new -> triaged -> approved -> pending_verification -> verified`, with documented defer and failed-verification reopen paths.
- Add ownership and needs-information/follow-up metadata without inventing an unreviewed second correction state machine.
- Return a readable conflict when a submitted action is based on an old case version; retain the operator's draft inputs.

### Sources

Show connector scope, supported fields, request parameters, adapter version, last successful and failed retrieval, source publication date when available, and truncation/completeness status. A successful retrieval must not imply verified accuracy or complete national coverage.

## Input scope

| Input | Shipping scope | Explicit boundary |
| --- | --- | --- |
| CSV | Header mapping, string-safe identifiers, selected encoding/delimiter, row quarantine | Not arbitrary automatic schema discovery. |
| XLSX | Selected worksheet/header, mapping, preserved row/cell references | No macro/formula execution or arbitrary workbook reconstruction. |
| Saved JSON | Explicit flat-record, NPPES response, and CMS dataset response profiles | Unsupported envelopes receive a useful rejection. |
| NPPES Registry API v2.1 | Exact NPI lookup and bounded search; default 25, application cap 200 records per intake | Preserve multiple locations/taxonomies and source status semantics; no credential certification. |
| CMS Doctors and Clinicians | Small bounded pages from National Downloadable File `mj5m-pzi6`, with fetched dataset metadata | Medicare clinician/enrollment/practice evidence, not every provider or payer network. |
| Links | Evidence URL with source, title, observed time, and asserted/fetched distinction; known public-source URLs can select their adapter | Attaching a webpage does not mean it has been fetched, parsed, or verified. Arbitrary HTML/PDF scraping is deferred. |
| CMS National Provider Directory FHIR | Experimental read-only adapter plus supported saved-Bundle fixtures after core acceptance gates pass | Discover advertised capabilities; preserve resources/references; do not imply production completeness, writes, or arbitrary FHIR support. |

For initial engineering acceptance, propose configurable limits of 10 MiB per uploaded artifact and 20,000 tabular rows, with a smaller preview. These are limits to implement and measure, not demonstrated performance. API imports use smaller connector-specific caps. Report `truncated` and query scope; never display a bounded sample as a complete directory.

## Data contract and persistence

The durable chain is:

```text
receipt -> retained artifact -> processing attempt -> source observations
                                                    -> findings / linked cases
                                                    -> workflow events
                                                    -> dated exports
```

Minimal additions and evolution:

| Record | Grain and important fields |
| --- | --- |
| `intake_receipt` | One delivery/request, including repeat deliveries: source, received time, original label or request, synthetic/public designation, artifact link, duplicate-of link. |
| `source_artifact` | One retained byte payload: SHA-256, media type, size, generated storage key, retrieved time, source update/publication metadata. |
| `ingestion_run` | One adapter/mapping attempt: versions, settings, state, counts, failure, start/end times. |
| `source_observation` | One source record at its native grain: run, source-native ID, row/resource locator, original and normalized payload, provider/location references, date semantics. |
| Provider/location links | Explicit crosswalks between observations and local provider/location identities; record reason and supporting evidence. Preserve unresolved candidates. |
| Finding/case links | Stable operational work linked to originating and later observations. Reuse and migrate the existing case/event structure where appropriate. |

Adapters return typed records and parse problems; they do not write database state. One ingestion service handles adapters, artifacts, preview, acceptance, and case linking for both CLI and HTTP routes. Keep mapping configurations explicit and small; avoid a plugin framework.

Required invariants:

1. A content hash identifies bytes, not a provider, case, or business submission.
2. A repeated delivery remains visible as a receipt but does not duplicate observations/work for the same source, artifact, and processing specification. Reprocessing under a changed mapping is a new versioned attempt.
3. Reordered rows do not change domain identity. Original row numbers remain provenance only. Records without sufficient native identity stay unresolved rather than receiving fabricated stable keys.
4. Provider, practice location, enrollment, payer listing, and operational work are distinct identities. Exact NPI can support a provider relationship; it does not identify a location.
5. Location-dependent fields are compared within an explicitly established location scope. Address components stay a coherent source observation rather than independently chosen components from unrelated sites.
6. A missing provider from a later bounded search is not evidence of termination. Removal interpretation requires an explicitly complete replacement scope.
7. `retrieved_at`, `source_updated_at`, effective dates, and `human_verified_at` retain separate meanings. NPI active status is not operational-location or payer-participation status.
8. New evidence does not silently close, overwrite, or reopen human work. Reuse the existing observed-verification decision boundary.
9. Commit accepted observations, findings, and case links in one database transaction. Interrupted attempts retain a readable status; retries cannot expose a half-accepted batch.
10. Updating a case projection and appending its event occur in one transaction with an expected-version check. Append-only history alone does not prevent concurrent update conflicts.

Use numbered SQLite migrations and per-connection foreign-key enforcement. Configure and verify WAL/busy-timeout behavior only as implemented requirements; remove existing unsupported claims first. Retain legacy workflow records with explicit legacy provenance; do not fabricate original artifacts that were never saved. Back up and rehearse migration against a copied database before applying it to the working dataset.

Store artifacts under generated local storage keys, with staged writes and atomic finalization. Preserve failed-attempt metadata and reconcile retained-but-uncommitted artifacts after interruption. Generated exports must not be the database of record.

## Architecture choices and trade-offs

| Choice | Benefit | Cost and revisit trigger |
| --- | --- | --- |
| Evolve the current application | Reuses tested review, remediation, UI, and export behavior | Requires deliberate migration of current-batch QA assumptions. Reconsider structure when shared services become difficult to test independently. |
| SQLite plus retained local artifacts | Simple reviewer setup and inspectable transactions | One workstation and bounded imports. Revisit PostgreSQL when measured concurrent-writer or deployment needs exceed this boundary. |
| Explicit source adapters and mappings | Each supported input has a testable contract | Additional sources require code/configuration work. Consider a broader mapping system only after several genuinely different sources reveal repeated needs. |
| One persisted local import worker | Responsive UI, visible failures, controlled retries | Throughput is bounded. Revisit worker count after measuring a representative queue and database contention. |
| Deterministic matching with human location links | Inspectable identity decisions and preserved evidence | More operator work for ambiguous submissions. Improve candidate suggestions using evaluated fixtures before changing merge policy. |

Measure import duration, peak memory, UI responsiveness, retry behavior, and committed-row throughput using representative mixed files before publishing performance claims. No benchmark results are asserted in this proposal.

## Service and API shape

Evolve the two local FastAPI applications into routers under one application, retaining route compatibility while moving shared storage/service logic out of endpoint handlers. Keep one local worker for bounded import jobs and a persisted processing-attempt table. On restart, identify interrupted attempts and offer safe retry; a distributed queue is unnecessary for this scope.

Proposed endpoints, not current capabilities:

- `POST /api/intakes/files`: retain an upload and schedule preview processing.
- `POST /api/intakes/lookups`: accept a typed source/query and schedule a bounded connector request.
- `POST /api/intakes/links`: attach an evidence reference or select a supported connector.
- `GET /api/intakes` and `GET /api/intakes/{id}`: inbox and receipt/attempt status.
- `GET /api/intakes/{id}/preview`: mapping, row problems, counts, and sample.
- `POST /api/intakes/{id}/mapping`: save a versioned interpretation for preview.
- `POST /api/intakes/{id}/commit`: explicit acceptance policy and idempotency token.
- Case endpoints retain separate QA/correction semantics and gain receipt links, location scope, version, ownership, follow-up, and later-evidence views.

Remote reads use connector-owned HTTPS hosts, bounded response sizes, explicit timeouts, and sequential page fetching. Retry transient failures only within a bounded policy, respecting `Retry-After` when present. Retain error envelopes; distinguish zero matches from an API/schema failure. Do not fetch arbitrary user-supplied internal URLs. Capture complete request scope, raw response, and paging/truncation state.

## Public-source contracts verified on 2026-10-23

### NPPES

- [Official API help](https://npiregistry.cms.hhs.gov/registry/help-api).
- Live smoke: `https://npiregistry.cms.hhs.gov/api/?version=2.1&city=Nashville&state=TN&limit=2` returned HTTP 200 and two records.
- Preserve `number`, entity type, `basic`, addresses, additional practice locations, taxonomies, identifiers, and source timestamps. Avoid the current positional-ID and update-as-verification mapping.
- Official documentation describes daily refresh, 200-result requests, and a finite `skip` search window; do not use it to promise a national bulk harvest.
- [NPPES bulk files](https://download.cms.gov/nppes/NPI_Files.html) are a future source. The page was under maintenance during research and the archive is unnecessary for a bounded demo.

### CMS Doctors and Clinicians

- [Dataset `mj5m-pzi6`](https://data.cms.gov/provider-data/dataset/mj5m-pzi6), [official data dictionary](https://data.cms.gov/provider-data/sites/default/files/data_dictionaries/physician/DOC_Data_Dictionary.pdf), and [PDC API guidance](https://data.cms.gov/provider-data/about).
- Live unfiltered two-row datastore query returned HTTP 200; fetched metadata reported modification on 2026-10-02. A filtered state query timed out; filtered browsing is not yet demonstrated.
- Native grain includes clinician/enrollment/group/address. Retain NPI, enrollment, organization PAC, and address identifiers, including missing values. Multiple rows per NPI are expected.
- Use stable dataset ID plus distribution index; retain metadata because refreshes can change distributions/schema. Use modest pages and contract tests rather than depending on inconsistent documented maximums.

### CMS National Provider Directory FHIR

- [Developer documentation](https://directory.cms.gov/developers), [CapabilityStatement](https://directory.cms.gov/fhir/metadata), [OpenAPI](https://directory.cms.gov/fhir/api-docs), and [program homepage](https://directory.cms.gov/).
- Metadata returned HTTP 200, FHIR 4.0.1, `active`, dated 2026-10-14; bounded Practitioner and Location searches each returned one resource in HTTP-200 searchset Bundles.
- Preserve `(resourceType, id)`, identifier systems, references, and opaque next links. A Bundle need not have `total`; NPI must come from an appropriate identifier system rather than any identifier.
- The official program homepage describes API testing. Treat this as experimental even with active metadata. No completeness or production-readiness claim follows from these smoke checks.

These checks establish present feasibility, not implemented connectors or source accuracy. Offline tests use synthetic fixtures shaped like those envelopes; optional live checks remain separate from CI.

## Build sequence and acceptance gates

| Slice | Deliverable | Gate before proceeding |
| --- | --- | --- |
| 0. Honest, reliable baseline | Fix identifier/null handling, separate NPI timestamp semantics, correct misleading docs, isolate demo/test storage | Blank-NPI/leading-zero ZIP regressions pass; tests and demo never clean working intake data. |
| 1. Complete file-intake journey | Durable artifacts/receipts/runs, CSV and XLSX adapters, mapping/preview, explicit acceptance/quarantine, inbox | Import a messy fixture from browser to persisted result; duplicate delivery and interrupted commit are controlled. |
| 2. National-reference evidence | NPPES adapter, saved JSON, response capture, query limits, retry/cache status, source detail | Live opt-in lookup and offline replay use the same contract; multiple locations and timestamps remain distinct. |
| 3. Durable reconciliation | Provider/location crosswalk review, stable QA work, current/later evidence, ownership/follow-up, versioned transitions | Second delivery preserves work; reordered rows and two locations under one NPI remain correct; stale updates fail cleanly. |
| 4. Second independent public source | CMS Doctors and Clinicians adapter with native grain and dataset metadata | Medicare evidence coexists with registry evidence without collapsing enrollment/address rows or interpreting absence as termination. |
| 5. Release-quality demonstration | One launcher, browser CI, synthetic story, current screenshots, export evidence, concise case study | A fresh checkout can run the deterministic demonstration without accounts or network. Live sources are optional. |
| Stretch after gates | Experimental CMS FHIR lookup/import | Resource references and paging pass fixture tests; testing/coverage limits remain visible. |

Testing should prove invariants rather than duplicate implementation:

- File fidelity: blank/null versus literal values, leading-zero IDs/ZIPs, ZIP+4, phone extensions, unknown headers, workbook sheets, formula-cell handling.
- Adapter contracts: missing native IDs, malformed/error envelopes, multiple locations/taxonomies, schema additions/removals, timeout, transient retry, paging boundaries, truncated results.
- Persistence: duplicate delivery, changed mapping version, interrupted commit/restart, original artifact integrity, stable work across row order and later receipts, migration rollback rehearsal.
- Domain: provider versus location identity, coherent address fields, no automatic merge, no termination inference from partial source coverage, verification distinct from source update.
- Workflow: invalid transitions, required evidence, approved-proposal verification, reopen, expected-version conflict, event/projection transaction consistency.
- Browser: upload -> mapping -> row quarantine -> commit -> case -> verification; repeat-delivery history; offline connector replay; readable empty/failure/retry paths; desktop and narrow layout.

Add isolated browser checks to CI with synthetic data; retain failure traces. Keep optional network smoke commands independent. Do not run the current destructive E2E setup against working intake storage.

## Five-minute demonstration

1. Open the intake inbox and import a synthetic clinic XLSX with unfamiliar headers, one malformed row, and one provider at two locations.
2. Confirm worksheet/mapping, inspect the row problem, accept valid rows, and download the quarantine explanation.
3. Import a differently shaped CSV; show the common observation model and retained original row evidence.
4. Review a location-specific phone discrepancy, explain the match evidence, approve a proposal, record a simulated submission, and verify the observed result. Show a second case reopening after a mismatch.
5. Reimport the first workbook; show the repeat receipt with no duplicate work and retained ownership/history. Import a changed delivery and inspect the later evidence without overwriting the original.
6. Open the separate public-reference example: retrieve or replay NPPES and CMS clinician observations; explain their different identity grains and timestamp meanings. Demonstrate experimental FHIR only if its gate has passed.
7. Export a receipt/case evidence packet containing traceable source locators and workflow history.

## Definition of done

The release is ready when heterogeneous input follows one tested intake contract; every accepted record and finding has original evidence; repeated deliveries and interruptions preserve work; operating-location scope is explicit; public-source claims match documented capabilities; the full synthetic browser journey passes in CI; and a reviewer can reproduce and understand the demonstration.

The shipped case study should describe implemented behavior and measured limits. It must distinguish synthetic operations, public reference observations, manually asserted verification, and actual external system changes.


## Proposed next phase: recurring organization and network rosters

Current disposition (2026-10-30): P1 operational SQL and N1 recurring clinic imports are implemented. [N1 qualification](evidence/data_operations/n1/README.md) records the passing local candidate and real operator evidence. N2–N4 remain in delivery; the requirements below remain the acceptance contract.

Status: **N1 locally qualified; N2–N4 planned.** Requested after application checkpoint `2a68c885033240bdf2681342bca0fc6013fe60c7`. This section owns the next scoped plan; the original proposal and completed qualification above remain historical. Prioritize the publishable core and read-only SQL examples below, then reusable source mappings and a readable change preview, followed by explicit organization/network participation storage through the existing intake service.

### Near-term delivery priority: publishable core and transferable data work

The first shareable checkpoint should demonstrate the existing Python/FastAPI, SQL/SQLite and JavaScript/TypeScript workflow without depending on completion of the organization/network expansion. Keep the healthcare scenario concrete; its import validation, relational identities, joins, repeat deliveries, recovery and review behaviors are inspectable engineering examples across data-intensive domains. The demonstration remains a healthcare-data workflow.

The product outcome is an inspectable data-operations and record-management application. Healthcare supplies the concrete records and business rules; the technical evidence should make ingestion, relational storage, provenance, controlled changes, reconciliation, repeatable automation and recovery easy to assess. The goal is useful operations that visibly require Python and SQL, with a working web interface.

| Capability to make inspectable | Implemented foundation | Next evidence/delivery |
| --- | --- | --- |
| Data ingestion and quality | Original CSV/XLSX/JSON retention, explicit parsing/mapping, normalization, row validation and quarantine. | Recurring files using reviewed saved mappings, structural-change detection and reconciled accepted/quarantined counts. |
| SQL and relational design | SQLite tables, joins, primary/foreign keys, indexes, transactions, numbered migrations and append-only event guards. | Tested operational SQL for follow-up work, source lineage, latest events and selected-delivery comparisons; show row grain, null handling and query plans where performance matters. |
| Record lifecycle and provenance | Stable source/provider/location work, immutable initial evidence, later observations, owner/follow-up and expected-version review events. | A readable old/new change view and explicit network participation history, preserving original records and earlier decisions. |
| Repeatable automation | Python CLI pipeline, bounded parsing/adapters, deterministic validation and exports, repeat-delivery handling and restart recovery. | A documented repeatable intake-to-handoff run with explicit inputs/settings, reconciled counts and retained run evidence; automate mechanical processing while acceptance and consequential review remain explicit. |
| Application integration | FastAPI service and React/TypeScript UI for intake, review/conflict recovery and evidence downloads. | A short walkthrough tracing one upload through Python, SQL, operator action and exported evidence, including a failure/retry case. |

SQLite is the current embedded SQL engine. The [SQL language reference](https://www.sqlite.org/lang.html) covers its SQL support, including joins, CTEs, window functions, indexes and transactions; [its deployment guidance](https://www.sqlite.org/whentouse.html) distinguishes embedded/local storage from client/server operation. Present the engine choice and its limits accurately. A database-engine replacement is not part of P0–P2; add a separate PostgreSQL or other dialect validation only when a concrete portability or operating requirement justifies it. Do not claim server administration, production concurrency or untested database compatibility from the local implementation.

| Order | Planned deliverable | Evidence required before claiming it |
| --- | --- | --- |
| P0 — Publication candidate | Review the current tested core as a specific revision: clear README/demo route, synthetic fixtures, current screenshots, installation commands, limitations and inspectable local check receipts. Review the selected source for synthetic fixtures, documentation accuracy and reproducible setup. | Reproduce the chosen revision in an isolated checkout and data root. Retain exact commands/results and distinguish local tests from remote CI. Record the exact source revision and fresh qualification results. |
| P1 — Operational SQL | A small tested read-only operational query pack over the current durable tables: unassigned/overdue work, evidence/receipt joins, latest event per case and a selected-delivery comparison. Declare one row's meaning and parameter/dialect assumptions for every query. | Synthetic fixtures prove expected output, missing/null handling and join cardinality. A case with several observations/events must not inflate case totals. The latest-event example has a deterministic tie-break. Run read-only against fixture-owned SQLite; expose source locators without changing work. No reporting dashboard or new database service is required. |
| P2 — One recurring-import slice | Implement N1 below: saved mappings, required-header change detection, explicit prior accepted delivery and valid-versus-quarantined field comparisons. | One end-to-end browser journey plus meaningful Python/SQL/UI regressions, repeat/restart preservation and inspected downloads. Preserve the simple documented demo. Saved-mapping and baseline behavior remains proposed until these gates pass. |
| P3 — Network expansion | Proceed to N2–N4 once the first shareable core/SQL checkpoint and N1 are usable. | The existing organization/network identity, migration, source-evidence and operator-journey gates below apply. Network breadth is not a prerequisite for publishing a bounded, honestly described core. |

P0 and P1 establish an inspectable core and operational SQL examples. The SQLite queries are specific to this application; portability to another engine requires separate validation.

These queries must answer actual record-management questions, such as which cases need follow-up, which receipts support a case, and what changed between selected deliveries. Their fixture checks and example outputs should make their operational use visible; a list of SQL keywords alone is insufficient. The SQL examples must use the actual current schema, not proposed network tables. Start with `work_case`, `work_event`, `work_evidence`, `observation`, `attempt` and `receipt`. Explain the fan-out when joining case → observations and case → events; use grouping, a deliberate existence test, or a ranked subquery according to the requested result grain. A latest observation per key is not a substitute for choosing one accepted delivery as a comparison baseline. Parameterize external values and identify the SQLite dialect; portability to an employer's SQL engine remains a separate verification step.

For implementation, use the project's supported Python version and primary references: [Python 3.13 CSV handling](https://docs.python.org/3.13/library/csv.html), [SQLite window functions](https://www.sqlite.org/windowfunctions.html), and [MDN Fetch behavior](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch). These references inform implementation; application tests establish the behavior claimed here.

### Delivery checkpoints and documentation updates

Use the existing Python/FastAPI, SQLite and React/TypeScript application throughout these checkpoints. Assume ordinary internal-application needs: file processing, relational queries, small API/UI changes, repeatable operations and debugging. The existing stack defines the implementation contract. Deliver one useful slice at a time; each pull request describes the operator problem, resulting behavior, checks and remaining limits.

| Checkpoint | Bounded additions | Documentation updated with the delivery | Completion evidence |
| --- | --- | --- | --- |
| P0: share the existing core | Publish a reviewed snapshot containing the implemented intake workbench, guided synthetic demo and read-only handoff, plus this roadmap. Record a reviewed source snapshot and its verification. | README entry/demo image and commands; current project state; this ordered plan; a dated qualification/publication receipt. Preserve earlier evidence as historical. | A clean source snapshot runs the documented deterministic checks with isolated storage. Record repository, source revision, public revision, PR URL where applicable and local versus remote CI results. Keep local checks and remote CI results distinct. |
| P1: answer operational questions with SQL | Proposed `sql/operations/` queries, a small read-only Python runner and fixture regressions. Cover unassigned/overdue work, receipt lineage, deterministic latest events and a comparison of two explicitly selected accepted deliveries. | Proposed `docs/OPERATIONAL_SQL.md`: questions, commands, parameters, result grain, expected synthetic outputs, dialect and limits. Link it from README; update the data dictionary only if a public contract changes. | Fixtures include absent evidence, nulls, multiple observations/events, equal event timestamps and two accepted deliveries. Query results match expected rows without join inflation; database/artifact hashes stay unchanged. The selected-delivery query does not claim to fix the application's existing comparison behavior. |
| P2 = N1: repeat a real import workflow | Reviewed saved mapping revisions, header-drift handling, explicit accepted baseline and readable valid/quarantined field differences through existing intake/API/UI paths. | API reference, data dictionary, architecture decision for persisted revisions/baselines, operations workflow and demo SOP; refresh screenshots/case study once observed. | N1 gates below, migration preservation where needed, Python/pipeline/frontend/browser checks, inspected handoff and real repeat/restart evidence. |
| P3 = N2–N4: manage scoped network assertions | Add organization/network identity and participation storage, then scoped review/filter/export behavior, in separate coherent PRs. | Data dictionary and migration/identity decisions before integration; API/workflow contracts with behavior; final multi-file SOP, case study and fresh screenshots. | N2–N4 gates below. Three distinct provider/location/network rows survive repeat deliveries and migration; no inferred membership or automatic termination. |

Keep `PROJECT_STATE.md` limited to actual capability, material limitations and the next priority. Keep `INTAKE_2_0_PROGRESS.md` as the compact continuation checkpoint, with the next exact action and links to evidence. Put routine implementation history in commits and pull requests. New documentation files listed above are planned outputs, not existing commands or shipped features.

For each implementation slice: settle its small data/API contract, implement through the existing service, run the relevant required checks against owned fixtures, inspect the operator result, and update affected documentation in the same PR. Keep SQL examples on the real schema and JavaScript work on actual request/data/error behavior. Avoid adding a database server, new framework, dashboard or connector platform merely to broaden the technology list.

Implement P0 through P3 as coherent slices with code, integration, tests, observed operator journeys and matching documentation. A roadmap, SQL file without a usable runner, backend-only migration or unverified UI does not complete a slice. Record completed and incomplete gates accurately at each checkpoint.

Keep synthetic fixtures, documented limits and exact check results with each feature slice. Record remote CI separately from local qualification.

### Operator and useful outcome

A provider-data coordinator receives recurring clinic and payer-network rosters in different CSV/XLSX layouts. The coordinator needs to answer: which provider is reported at which practice location in which network, what changed in this delivery, what remains uncertain, and who must follow up? The output is a reviewable queue and evidence-backed handoff, with the original files retained.

For this phase, a **network** means a payer/provider participation network. Clinics, medical groups and health systems are **organizations**; organization affiliation and network participation are different relationships. A payer organization can have several networks, and one provider/location can appear in several networks. A network label does not identify an insurance product or establish a patient's benefits. Health-system affiliation modeling beyond a source-supplied organization link is deferred.

This scope follows the [HealthCare.gov network definition](https://www.healthcare.gov/glossary/network/). CMS's [NPI fact sheet](https://www.cms.gov/files/document/npi-fact-sheet.pdf) distinguishes NPI assignment from licensure/credentialing and Medicare enrollment. Our design consequently treats NPPES/CMS reference observations as identity/context evidence, never proof of participation in a supplied payer network.

### Baseline to reuse and actual gaps

Current code already retains CSV/XLSX/JSON originals, interpretations, quarantine, explicit acceptance, source-scoped provider/location links, later evidence, accountable work and read-only exports. Do not rebuild those paths. Current `IntakeStore.receive` reuses a committed mapping only for identical source/profile/artifact bytes; it does not provide a reusable mapping for genuinely changed clinic files. `compare_delivery` supplies counts and row classifications, while the UI largely exposes the comparison as JSON. There is no organization/network catalog, network-aware participation observation model or network-specific identity in the durable work contract. CMS enrollment/group/address identifiers already retained by its adapter are not payer-network identities. The current comparator takes the latest observation per native key across source history and classifies parsed rows including quarantine; it is not a single accepted-delivery or prospective accepted-row diff. N1 must replace that comparison contract before presenting the stronger change preview.

### First synthetic demonstration

Use a clearly synthetic payer organization, two named networks (CEDAR and PINE), and one clinic organization with NORTH and SOUTH locations. The same clinician appears at NORTH in both networks and at SOUTH in CEDAR. Those three participation rows must stay distinct.

1. Import an unfamiliar clinic workbook; review mapping once and save a source mapping revision. Inspect a malformed row and explicitly accept the valid rows.
2. Import a separate network roster. Confirm its network code bindings and provider/location links; unresolved links remain visible for review. Show source-listed participation, dates, original receipt and exact row.
3. Import the next delivery with reordered columns/rows, one phone change, one new participation row and one prior row absent. Reuse the saved mapping, show old/new field values and the selected baseline delivery, then accept explicitly. Missing remains missing-from-this-delivery; it is not a termination.
4. Demonstrate a renamed required header pausing interpretation for mapping review. An added unknown column is visible and retained without destroying a still-valid mapping.
5. Filter work by network and clinic/location, assign follow-up, inspect all evidence and download a scoped XLSX handoff. Repeat a delivery and restart: relationships, ownership, history, mapping revisions and originals remain intact.

The network roster's supplied phone/status is an assertion by that source. A changed participation row creates review work; it does not automatically become an approved correction. Existing explicit phone proposal/submission/observed-verification behavior remains separate. Cross-source clinic-versus-network comparisons require reviewed network and location links before being added; joining by NPI alone is insufficient.

### Proposed logical storage

These are logical records to settle before choosing exact table names/DDL. Keep the current SQLite/artifact architecture; do not introduce a separate database service.

| Record | Grain and proposed retained fields |
| --- | --- |
| Organization | One explicitly created/confirmed local organization: opaque ID, label, kind such as clinic/group/health system/payer, source-native identifiers with their issuing namespace, and asserted provenance. An organization is not identified by its display name. |
| Network | One explicitly identified local network: opaque ID, label, owning payer organization when known, source code bindings and provenance. Missing owner stays unknown. Multiple sources require an explicit reviewed binding to the same local network; equal names never merge networks. |
| Saved source mapping revision | One immutable revision for a stable source/import configuration: adapter kind, worksheet/header/encoding/delimiter, column mapping, required-header expectations, network/organization bindings, allowed source scope, actor/reason/time. Keep this distinct from the existing flat/NPPES/CMS adapter profile. |
| Participation observation | One source assertion about a provider at a location in a network: linked accepted observation/attempt, source-native participation/listing key or declared composite key, provider/location/network references, organization reference when supplied, source-listed status, reported effective/end dates, raw values and interpretation. It retains receipt, row/cell locator and retrieval/source dates through existing provenance links. |
| Reviewed identity binding | Audited source-namespace/key to local organization/network/provider/location relationship. Preserve unresolved candidates and earlier binding decisions; corrections do not rewrite retained originals or immutable initial case snapshots. |
| Participation review work | A current review projection plus append-only events, linked to initial and later participation evidence. Reuse existing work ownership, follow-up and expected-version patterns; network scope becomes part of new participation work identity. |

A proposed relationship is `organization → network → participation observation → provider + practice location`. The clinic organization may also be referenced by the participation row. This is a set of explicit references, not an inference that a clinic owns the payer network or that its entire staff participates.

For a valid longitudinal comparison, require a reviewed stable identity comprising source scope, network, provider, location and the declared native participation key (or an explicitly configured stable composite when no single native key exists). Preserve every identifier as text. Row position, file hash, provider name and an address string alone cannot establish participation identity. Duplicate/contradictory rows for the same declared key must be shown for review, not resolved by choosing the last row. An unresolved identity cannot silently become an established membership.

Store source-listed status separately from review disposition and any later human verification. Retain unknown versus supplied values; parse reported effective/end dates without relabeling retrieval time as effective time. Invalid or contradictory dates generate an explained row problem. Keep originals and as-imported organization/network labels even if a catalog display label changes later.

### Import, comparison and API behavior to implement

- Source setup explicitly chooses a clinic-roster or network-roster configuration. A file with several networks requires mapped network codes and reviewed code bindings. A fixed single-network default is allowed only when the operator explicitly declares that scope; row/default conflicts require review.
- Save and select a mapping revision for later files. Reordered known columns still work; missing/renamed required columns pause acceptance until a new revision is reviewed. New unmapped columns remain in the original and preview. Applying a saved mapping never accepts rows.
- Retain the selected mapping and identity-binding revisions in the processing specification/fingerprint. Identical bytes interpreted against different network bindings must not reuse the wrong accepted result. Repeating the same interpretation remains idempotent.
- Beginning in N1 for clinic files, choose and display one prior accepted delivery as the baseline; never synthesize a baseline by taking different keys from different historical deliveries. N3 extends this to the same declared source/dataset/network scope. Delivery/as-of dates are metadata, not a changing identity key. Never compare a clinic file with an unrelated payer feed or combine different networks' native IDs.
- Compute prospective accepted new/changed/unchanged results from valid rows only. Show quarantined rows separately. If an invalid row has an unambiguous known source key, label the baseline record as present-but-invalid/blocked rather than an accepted change or unexplained absence. Rows without enough identity remain unresolved and cannot conceal a missing baseline record. Distinguish input-row counts from unique-identity counts; duplicate/conflicting keys need an explicit problem.
- Display new/changed/unchanged/unresolved/missing and blocked-invalid counts with a filterable row/field comparison: previous value, incoming value, receipt/row locator and mapping revisions. Distinguish a reinterpreted mapping from a source-value change. Recheck the baseline at acceptance; a newer accepted delivery requires refreshing a stale comparison.
- Expose network/organization filters and case scope through additive API/UI fields. Existing receipt, file upload, mapping, acceptance and export paths remain the integration points. Add only small catalog/mapping operations where necessary; define exact endpoints after the identity contract is agreed.
- Carry organization/network IDs and source-listed participation through full evidence packets and workbook sheets. Clearly label all-work, selected-case and any future explicit network export scope; never silently apply UI filters to the existing all-work download. Reads remain transactionally consistent and non-mutating.

Absence from a file, even a declared full snapshot, produces a reviewable missing observation only. Automatic termination/removal is outside this phase. Source designation, declared completeness and effective dates must be retained so reviewers can assess what a delivery actually supports.

### Ordered implementation slices and acceptance gates

| Slice | Deliverable | Gate |
| --- | --- | --- |
| N1 — Repeatable file intake | Saved source mappings, immutable revisions, header-change review, one explicit accepted clinic-delivery baseline and readable field-level preview. | Different bytes/reordered columns reuse a reviewed mapping; renamed required headers pause acceptance; unknown columns remain inspectable; quarantined rows cannot masquerade as accepted changes or hide absence; stale-baseline acceptance conflicts; restart retains revisions; repeats do not duplicate work. |
| N2 — Network participation storage | Small organization/network catalog, reviewed source bindings, additive participation observations and explicit scope. | Three synthetic provider/location/network combinations persist independently; ambiguous names/missing IDs/conflicting keys stay reviewable; same native key in different networks cannot collide. Migration preserves every existing receipt/case/event and artifact link. |
| N3 — Recurring network review | Extend N1 baseline/validity rules to network scope; add network-aware QA work, filters and XLSX/JSON handoff. | Changed, new, missing and contradictory rows have correct evidence and distinct workflow states; later evidence never verifies work; stale comparisons conflict; selected exports contain only their stated relationship scope. |
| N4 — Operator demonstration | Fresh offline multi-file journey, restart/repeat/error recovery, inspected screenshots/workbooks and a concise updated SOP/case study. | A first-time reviewer completes the journey without local path guessing; deterministic checks pass; original runtime data remains unchanged; demonstrated and proposed behavior stay separate. |

Before N1 persistence, settle mapping-revision and comparison-baseline storage and preservation. Before N2, review exact foreign keys, uniqueness rules, binding-history representation and new case identities. Use a numbered additive migration with SQLite backup/rollback/integrity/FK tests; current schema v2 and old case identifiers remain untouched during this planning task. Do not guess new network bindings for historic source rows or rebuild old cases. Rehearse migration only against fixture-owned copies before adopting any working database.

Run `make validate`, `pytest -q`, frontend tests/build and desktop/phone browser checks as applicable, using invocation-owned database/artifact roots and preserving existing compatibility coverage. Add fixtures for leading-zero IDs, literal `NA`/nulls, invalid dates, duplicate keys, source/network collisions, multi-location providers, structural drift, repeated/reordered deliveries, interrupted acceptance and full evidence beyond UI sample bounds. Inspect browser-downloaded workbooks, prove exports do not mutate state, and rehearse real stop/resume. Performance claims require new measurements on representative fixtures.

### Scope boundary and learning goals

Ship local file-based organization/network roster intake first, using synthetic fixtures. Existing bounded NPPES/CMS adapters provide separate reference evidence. New live payer integrations, arbitrary website scraping, plan/product catalogs, contracts/rates, benefits or eligibility determination, credentialing, automatic identity merging, national ingestion, bulk mutation, FHIR, authentication/hosting and KPI integration remain deferred.

The engineering learning goals are concrete: relational modeling and many-to-many relationships; source namespaces and stable identity; reusable versioned configuration; schema-change detection; SQL field comparisons; transactional acceptance/idempotency; migrations and preservation; and an understandable review UI. Completion is demonstrated by the recurring multi-file operator journey, not an assumed scale or hours-saved claim.
