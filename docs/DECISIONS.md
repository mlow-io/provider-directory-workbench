# Architecture decisions

Updated 2026-10-23. These describe the local implementation, not production qualification or healthcare compliance.

## ADR 001: Retained evidence and transactional work

Accepted. `IntakeStore` separates artifacts, deliveries, interpretation attempts, native observations, relationships, work projections, later evidence, and events. An original case snapshot never changes after creation; later observations attach separately even when a discrepancy disappears. Approval, simulated submission, observed verification, and failed-verification reopen remain distinct decisions. QA resolution is not correction verification.

Acceptance commits all valid observations and linked work together under `BEGIN IMMEDIATE`. HTTP acceptance requires the attempt that was previewed; repeated acceptance of the same attempt is idempotent. Work events require the expected case version and update the projection and append history in one transaction. Database triggers prevent work-event update/delete through ordinary SQL. Actor/reason are asserted locally, without authentication.

Legacy QA/remediation IDs, tables, and events remain intact. Legacy QA detail still depends on the current generated batch; missing historical originals are not reconstructed. The new durable Work queue is the intake path. Preserving this compatibility boundary avoids falsely relabeling old snapshots as original artifacts.

## ADR 002: Explicit identity and coherent location evidence

Accepted. SHA-256 identifies bytes, not providers. A repeat artifact creates another receipt and can reuse a committed interpretation. A changed mapping creates a new attempt. Scoped native provider/location/listing identity reuses work across reordered or changed deliveries. Inadequate native identity remains unresolved.

An exact NPI supports a provider relationship, while a supplied source location key or human-reviewed crosswalk establishes operating-location scope. Multi-address public records retain their source grain; linking requires selecting one native practice address. Mailing evidence cannot establish an operating site. Address components stay together. There is no automatic merge, inferred termination, or cross-location field assembly.

Initial 2.0 operational comparison is a location phone requested-versus-listed discrepancy using explicit `reference_phone`. This is deliberately narrower than a generalized multi-source field reconciliation engine. The existing synthetic payer-precedence workflow remains available in compatibility views.

## ADR 003: One local API and bounded synchronous work

Accepted. `intake_api.create_workbench` composes existing review/remediation routes with intake/work/source endpoints on port 8000. Vite on 5173 proxies to it; a configurable API origin supports isolated browser tests. React has persistent navigation, URL-backed work filters, bounded evidence samples, and conflict recovery that retains draft inputs.

Parsing runs in a request worker thread with a persisted processing-attempt marker. Restart marks unfinished attempts interrupted and permits explicit replay. This replaces the proposal's separate persistent worker with a smaller equivalent recovery model. Measured 20,000-row CSV acceptance took about ten seconds locally; a separate queued worker is a revisit point if real workloads need progress/cancellation or longer asynchronous work. Multiple HTTP requests can parse concurrently; SQLite serializes acceptance writes. No throughput guarantee for concurrent writers is asserted.

## ADR 004: SQLite and artifact recovery

Accepted. `storage.py` configures foreign keys, WAL, and a ten-second busy timeout per connection. Numbered transactional migrations add the intake schema (v1) and native location crosswalk index (v2); future versions fail explicitly. SQLite backups precede legacy/v1 upgrades, and tests rehearse preservation, rollback, restart, integrity and foreign-key checks.

Artifact writes use generated digest keys, fsync and atomic rename. The ledger registers finalized bytes. Startup reports staged/unregistered/missing files to `artifact-recovery.json`, retaining them for inspection instead of deleting or accepting them. This favors evidence preservation over automatic garbage collection. Original files and working databases remain outside disposable test/demo roots.

## ADR 005: Explicit public adapters and offline replay

Accepted. Pure flat/NPPES/CMS adapters return original/native/normalized evidence and locators without database writes. The shared intake service handles HTTP uploads and public reads. Bounded owned-host HTTPS fetches cap records/bytes, enforce timeouts and bounded transient retries, retain request scope and CMS dataset metadata, and distinguish API failures from empty successful responses. Error bytes are retained when available, explicitly flagged if capped.

A lookup can reuse a retained response for fifteen minutes, producing another receipt with `retained_response` provenance. Explicit `refresh` bypasses reuse. Saved JSON uses the same parser/acceptance contract, but remains a replay, not live success. Publication, source update, retrieval, and human verification retain separate meanings. FHIR is deferred.

## ADR 006: Verification without destructive setup

Accepted. `PDTL_ROOT`/`PDTL_DB` configure owned paths across services and CLI. Service startup does not seed; validation gets a new directory each run. The demo launcher defaults to a fresh directory and resumes only when an explicit root is supplied. Browser setup uses new storage, no unknown-server reuse, sequential mutable scenarios, and separate synthetic source scopes. CI runs the same browser suite and retains failure traces. No checks require working runtime deletion.

## ADR: reviewed recurring mappings and a single accepted baseline

Keep recurring files in the existing receipt/attempt/observation service. Schema v3 adds immutable templates rather than rewriting previous mappings or creating another import subsystem. Every application of a template creates a retained attempt; source/profile/scope checks prevent accidental reuse across feeds. Header drift blocks acceptance, while unknown columns remain original evidence.

A preview selects one accepted attempt and records its ID. Acceptance rechecks that ID in `BEGIN IMMEDIATE`, which serializes the baseline check with observation/case writes. This avoids accepting a comparison that went stale after another delivery. Repeats do not create a new baseline; interpretation identity excludes the preview context but includes mapping revision. Prospective changes use valid unique rows, with invalid known identities explicitly blocked and unresolved rows unable to hide absence. Existing native public-reference comparison semantics remain separate.

## ADR: explicit source-bound participation identity

Use a small create-only organization/network/location catalog and append-only typed source bindings. Equal labels remain distinct opaque IDs. A reviewed binding references exactly one existing target through SQLite FKs; correcting it appends a revision with expected-current protection. Every network interpretation retains the binding snapshot and mapping revision in its fingerprint. The accepted row preserves the source codes/labels/dates and the local references separately.

A participation key includes source dataset, native record key, provider, local practice location and local network. This prevents one NPI or native key from collapsing multiple sites/networks. A fixed network is explicit configuration; a contradictory row is unresolved rather than evidence of presence in that default network. Unknown bindings stay quarantined. Baselines require equal declared network scope, and acceptance checks both baseline and binding freshness in the same transaction. No historic clinic evidence is silently converted into membership.
