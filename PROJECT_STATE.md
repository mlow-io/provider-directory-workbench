# Project state

Updated 2026-10-30. Local Intake Workbench 2.0; original G0–G5 baseline and the focused employer-readiness follow-up passed locally. Publication status and fresh snapshot qualification are recorded separately from these historical local results.

## Implemented behavior

- String-safe legacy QA pipeline and preserved current-batch review/remediation compatibility views; source updates are separate from human verification.
- Unified FastAPI application with durable CSV/XLSX/explicit JSON intake, original hashed artifacts, receipt and attempt history, parsing controls, mapping, full bounded validation, explicit acceptance/rejection and quarantine exports.
- Native NPPES and CMS Doctors and Clinicians adapters, bounded public reads, raw response/error retention, dataset metadata, fifteen-minute retained-response replay and asserted unfetched links. Multiple locations/taxonomies and clinician/enrollment/group/address grain remain inspectable.
- Stable source/provider/location/native-key work with initial snapshots and later observations; explicit audited practice-location crosswalks; ownership, needs information, follow-up and explained risk; stale-preview/case conflict checks and atomic event/projection updates.
- Distinct QA disposition and correction approval/simulated submission/observed verification/reopen. Current operational correction scope is explicit location phone requests, with legacy configured payer-field comparison separately available.
- Schema v2 numbered transactional migration, backups and future-schema rejection; SQLite foreign keys/WAL/busy timeout; retained artifact recovery report; invocation-owned validation/browser/demo storage.
- Intake/Work queue/Sources navigation, desktop/phone layouts, keyboard controls, loading/empty/failure/retry states, retained conflict drafts, full evidence packets, and one offline demo launcher.
- Explicit offline synthetic sample picker through normal intake, editable suggested workbook columns and operator acceptance; ordinary service startup keeps sample loading disabled. Repeated fixture bytes stay stable across restarts.
- Read-only all-durable-work/selected-case XLSX handoff with current ownership/follow-up, scoped evidence/receipt/row locators, complete history and chunked original payloads from a consistent SQLite snapshot. All-work export explicitly ignores queue filters.

## Qualification and current checkpoint

The 2026-10-23 baseline passed 103 Python tests, isolated pipeline validation, three frontend tests, TypeScript/Vite 6.4.5 build and 12 browser scenarios across desktop/phone viewports in a clean local checkout. npm audit reported zero known vulnerabilities. Exact commands and fresh-checkout evidence are recorded in [the execution checkpoint](docs/INTAKE_2_0_PROGRESS.md) and [evidence index](docs/evidence/intake_2_0/README.md). Original legacy runtime data was backed up and preserved before implementation.

The 2026-10-26 follow-up passed **114 Python tests**, isolated pipeline validation (12 records/11 findings/six discrepancies), **six frontend tests**, production build and **14 desktop/phone browser scenarios**. Real fresh offline start/stop/resume retained exact cases/events/receipts/observations and input/artifact hashes; all 137 prior runtime files remained unchanged. Selected UI/screenshots and downloaded XLSX contents were inspected. See the [follow-up evidence](docs/evidence/employer_readiness/README.md).

Subsequent regression hardening passed **124 Python tests**, pipeline validation, six frontend tests, production build and 14 browser scenarios. Later native evidence/relationship exports now retain the selected case scope; launcher port/service failures return nonzero and clean up sibling/descendant services. Real failure/restart checks preserved exact work and originals; all 272 pre-existing runtime files remained unchanged. See the [hardening evidence](docs/evidence/employer_readiness/hardening/README.md).

Integrated bounded live NPPES and CMS reads succeeded on 2026-10-23, one record each, both explicitly truncated. Public data is not certified truth. Synthetic offline fixtures are separate from retained live observations.

## Limits and trade-offs

The service uses bounded worker-thread requests and persisted attempts, not a separate persistent job queue. Initial operational comparison is location phone listed-versus-requested; there is no generalized reconciliation engine. Legacy QA remains a generated current-batch compatibility view; old originals are never fabricated. New intake work is durable.

Current delivery comparison takes the latest observation per native key across source history and classifies parsed rows including quarantine. It does not establish a single accepted-delivery or prospective accepted-row diff. The planned N1 slice explicitly addresses baseline selection and present-but-invalid rows before expanding comparisons to networks.

Artifact cap is 10 MiB and tabular cap 20,000 rows. Interactive samples cap at 50 observations; queue renders 200 matches over loaded summaries. A measured 20,000-row synthetic CSV took 1.14 s preview and 9.86 s acceptance with roughly 312 MiB process RSS; XLSX/concurrent-writer equivalence is not established. Public reads are bounded pages and may fail or quarantine incomplete records.

Names/verification inputs are locally asserted, no authentication or external payer writeback exists. No automatic identity merge/removal, national replication, KPI integration, multitenancy, deployment, bulk case operations, clinical/credential certification or FHIR is implemented.

## Next scoped priority — planned

The [next-phase proposal](docs/INTAKE_2_0_PROPOSAL.md#near-term-delivery-priority-publishable-core-and-transferable-data-work) prioritizes a reviewed publication candidate for the existing core and a tested operational SQL pack over real record-management questions, then N1 saved mappings/readable accepted-delivery comparisons. Organization/network participation storage and N2–N4 remain planned after that usable checkpoint. This is proposed work: no SQL example pack, catalog, participation model, schema migration or new API is implemented by this roadmap. Existing scope exclusions remain in place.

The [delivery checkpoints](docs/INTAKE_2_0_PROPOSAL.md#delivery-checkpoints-and-documentation-updates) define P0–P3. The implemented core is documented above; P1 operational SQL and N1–N4 recurring import/network features remain planned. The [2026-10-30 snapshot qualification](docs/evidence/data_operations/p0/README.md) passed 124 Python tests, pipeline validation, six frontend tests, build and 14 browser scenarios. Remote CI is recorded independently after publication.


## Contributor navigation

Read [README](README.md), [AGENTS](AGENTS.md), [execution checkpoint](docs/INTAKE_2_0_PROGRESS.md), [architecture decisions](docs/DECISIONS.md), and [demo procedure](docs/operations_governance/sop_provider_remediation.md). Historical handoff/review findings remain dated evidence; the current dispositions and checks are linked rather than rewriting reproductions.
