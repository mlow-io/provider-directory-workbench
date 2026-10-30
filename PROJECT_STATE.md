# Project state

Updated 2026-10-30. P0–P3 application work is implemented locally through the guided multi-file demonstration. Final clean-candidate qualification/publication state is tracked in the [progress checkpoint](docs/INTAKE_2_0_PROGRESS.md); no release or deployment is claimed.

## Implemented

- Durable CSV/XLSX/explicit JSON intake, hashed originals, receipts/attempts, string-safe normalization, full bounded validation, quarantine, explicit acceptance/rejection and complete evidence packets.
- Immutable reviewed mapping revisions reusable across changed bytes; required-header drift review, unknown-column retention, one accepted source/dataset/network baseline, valid-only field comparisons, duplicate-key quarantine and stale-baseline acceptance checks.
- Distinct organization, payer network, provider, practice location and source-asserted participation identities. Opaque catalog IDs, typed immutable binding revisions and interpretation snapshots prevent name/NPI inference or cross-network collisions. Source status/effective/end/as-of dates and declared completeness retain their own meanings.
- Durable network QA for accepted assertions, missing baseline keys and known quarantined identities. Unknown bindings remain receipt quarantine. Human ownership/follow-up/status/version/history and immutable initial evidence survive later deliveries, reinterpretation and restart; no automatic merge, termination or verification occurs.
- Parameterized read-only SQLite questions for follow-up, original/row lineage (including comparison work), deterministic latest events and two explicitly selected accepted deliveries with full network identity/scope checks.
- Network/organization/location filters, responsive case review and read-only all/case/network XLSX/JSON from one pinned SQLite snapshot. Scoped operational catalog/binding/participation rows remain separate from complete shared receipt context; literal-text/chunked payload safety preserves identifiers, nulls, dates and long originals.
- Demo-only explicit synthetic catalog preparation and guided clinic/network sample paths. Saving/loading/applying never silently accepts or verifies. Header-error recovery saves a new revision; repeat/restart retains work. Ordinary startup does not seed data; original compatibility QA/correction views remain available.
- Additive transactional schema migrations 1–4, versioned SQLite backups, future-schema rejection, integrity/FK checks, artifact recovery reporting and invocation-owned validation/browser/demo storage. A real populated v2→v4 migration/restart rehearsal preserved prior rows/events/input/artifact hashes.
- Native NPPES/CMS bounded reference adapters, retained raw responses/errors, source metadata/replay and explicit location relationships. Historical live checks remain dated reference observations, not certified truth.

## Qualification

The [final qualification](docs/evidence/data_operations/n4/README.md) passed **168 Python tests**, isolated pipeline 12 records/11 findings/six discrepancies, **14 frontend tests**, production build and **22 desktop/phone-sized Chromium scenarios**. Actual guided network acceptance/review/download/header-recovery behavior and screenshots were inspected. A separate real v2→v4 launcher migration/restart/repeat/export rehearsal preserved prior rows, source bytes, initial evidence and human history; all 7,449 pre-existing files were preserved in place or prior-output copies. One upstream TestClient deprecation warning remains.

Earlier [core](docs/evidence/data_operations/p0/README.md), [SQL](docs/evidence/data_operations/p1/README.md), [N1](docs/evidence/data_operations/n1/README.md), [N2](docs/evidence/data_operations/n2/README.md) and [N3](docs/evidence/data_operations/n3/README.md) receipts retain incremental dated evidence. Remote CI and default-branch adoption are separate gates in the progress checkpoint.

## Material limits

This is a single-user local application with bounded worker-thread requests and persisted recovery, not a persistent job queue. Reviewer/verification identities are local assertions. Network review is QA; operational phone proposal/simulated submission/observed verification remains a separate clinic-location correction workflow. Clinic-versus-network reconciliation is not inferred by NPI or equal labels.

Artifact limit is 10 MiB and tabular limit 20,000 rows. Interactive evidence/comparison samples stop at 50 and queue rendering at 200 matching cases; full exports read complete selected durable scope. Earlier 20,000-row CSV timing remains historical and does not establish equivalent XLSX, concurrent-writer, memory or production performance. Native public JSON reference comparisons retain their earlier semantics.

Authentication, hosting, multitenancy, bulk mutation, payer writeback, full entity resolution, automatic termination, national ingestion, FHIR, products/benefits/rates, clinical/credential certification and KPI integration remain outside scope. A source assertion never establishes a patient's benefits or verified participation.

## Contributor entry

Start with [README](README.md), [AGENTS](AGENTS.md), [workflow](docs/OPERATIONS_WORKFLOW.md), [data dictionary](docs/DATA_DICTIONARY.md), [API](docs/API_REFERENCE.md), [decisions](docs/DECISIONS.md), the [SQL guide](docs/OPERATIONAL_SQL.md) and [operator SOP](docs/operations_governance/sop_provider_remediation.md). The [roadmap](docs/INTAKE_2_0_PROPOSAL.md) retains scope and acceptance criteria; delivery gates are recorded separately from implementation.
