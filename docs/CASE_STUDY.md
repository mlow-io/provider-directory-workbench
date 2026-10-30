# Provider Directory Intake Workbench

A local data-operations application for receiving heterogeneous provider-directory files, keeping original evidence, reviewing changes and handing off accountable work. Python/FastAPI handles parsing, validation and transactions; SQLite retains relational provenance and workflow; React/TypeScript presents explicit operator decisions. The offline scenario is synthetic.

## Operator problem and resulting workflow

Clinic and payer-network files arrive with different headers, repeated bytes, invalid rows and ambiguous identifiers. An NPI identifies a provider, not a practice location or payer-network membership. The workbench retains each original artifact and receipt, creates immutable interpretation attempts, quarantines invalid rows and requires explicit acceptance. Reviewed mapping revisions work across changed bytes/reordered columns; required-header drift pauses acceptance.

Recurring comparisons select one accepted delivery in the same source/dataset/network scope. Valid new/changed rows, known invalid identities, unresolved rows and missing baseline records remain distinct. Duplicate keys never resolve by choosing the last row. Acceptance checks the preview baseline and binding versions under the same transaction as observation/case writes; stale comparisons require renewed review.

The organization/network catalog uses opaque IDs and reviewed source-code bindings. The demonstration keeps CEDAR/NORTH, CEDAR/SOUTH and PINE/NORTH distinct under one synthetic clinician. Source status and reported dates remain assertions. Missing/quarantined comparison evidence creates QA follow-up without fabricating accepted participation or changing human review state. Earlier originals, ownership, immutable initial evidence and append-only human actions survive repeats, mapping/binding changes, restart and additive migration.

## Inspectable engineering evidence

- A parameterized read-only [SQL runner](OPERATIONAL_SQL.md) answers follow-up, original-row lineage, deterministic latest-event and explicitly selected accepted-delivery questions. Queries state result grain and prevent evidence/event joins from inflating case counts.
- File/adapter fidelity preserves identifier text, leading-zero ZIP, unknown fields, nullable values and original CSV/XLSX/JSON locators. NPPES/CMS have separate bounded native-grain adapters; historical live observations are dated, not certification.
- Numbered SQLite migrations preserve existing rows/history/artifact links, with owned-copy rollback and real populated v2→v4 rehearsal. Validation/demo/browser commands use isolated storage; ordinary startup never reseeds working evidence.
- All/case/network XLSX and JSON use a single read-only snapshot. Scoped operational rows are explicit; full receipt/attempt payloads remain labeled shared context. IDs/dates/formula-like values are literal text and complete long payloads are chunked rather than truncated by Excel.
- The [guided multi-file SOP](operations_governance/sop_provider_remediation.md#guided-multi-file-network-demonstration) exercises manual mapping/acceptance, changed and contradictory rows, missing evidence, scope filtering, ownership, inspected downloads, header-error recovery, repeat and restart. [Dated qualification receipts](evidence/data_operations/n4/README.md) distinguish final local checks from remote publication gates.

## Scope and limits

This is a single-user local workbench, with bounded worker-thread requests and persisted recovery rather than a distributed job queue. Reviewer identities and verification inputs are locally asserted. Artifact limit is 10 MiB and tabular limit 20,000 rows; interactive samples render up to 50 observations/comparison entries and 200 matching cases. Full exports read durable scope beyond these UI limits. Earlier CSV performance measurements remain dated and do not establish XLSX, concurrent-writer or production scale.

There is no authentication, hosting, multitenancy, automatic entity merge/termination, payer writeback, clinical/credential certification, patient-benefit decision, national ingestion, product/rate catalog, FHIR or KPI integration. Clinic and network evidence coexist, but cross-source reconciliation is not inferred from NPI alone.
