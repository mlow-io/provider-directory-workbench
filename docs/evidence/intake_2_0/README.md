# Intake 2.0 evidence index

Implementation branch: `feat/provider-directory-intake-2`, based on complete documentation checkpoint `1b0733c234ff17d75aa6aaab24dd8b439ec6c03b`.

## Baseline preservation and G0

2026-10-23: clean checkout confirmed at the documentation commit. Python 3.13.2, FastAPI 0.116.1, pandas 2.3.2, openpyxl 3.1.5; Node 22.17.0/npm 10.9.2. No project service listeners. Legacy database was 36,864 bytes with generated QA and review tables. SQLite backup, copied exports, and original SHA-256 manifest are retained locally at `.runtime/preserved-20261023/`; originals were not migrated or reseeded.

`make validate`: 66 Python tests passed, isolated synthetic pipeline validation passed (12 records, 11 QA findings, six correction discrepancies). The additional finding is the correctly detected missing NPI. Disposable validation root `.runtime/validation-ukmqt0bb` is retained locally; reruns create new roots.

The fidelity regression tests preserve leading-zero identifiers, actual nulls, literal `NA`, and separate registry-update versus human-verification dates. Historical reproduction evidence remains unchanged.

## Historical G0 checkpoint

At that initial checkpoint, G1–G5 implementation and integrated acceptance evidence were still pending. The 66-test result included adapter unit tests; it did not establish live integration or UI acceptance. The completed qualification and its limits are recorded in the final gate receipt below.

## Integrated implementation qualification

- `tests/test_intake_store.py`: artifact/hash/quarantine/native identity, mapping changes, repeats/reordering, later evidence, source scopes, explicit practice-address links, interruption/restart, migration backup/rollback/future rejection, FK/integrity, atomic acceptance/event rollback, version conflict, verification/reopen, bounds/formulas/formatted numeric ZIP, orphan recovery.
- `tests/test_intake_api.py`: HTTP receipt/original/quarantine/packet/commit/repeat/conflict, saved failure bytes, links, retained-response cache.
- `tests/test_storage.py`: connection pragmas and validation isolation even when an inherited `PDTL_DB` points at working data.
- `web/e2e/intake.spec.ts`: CSV/XLSX mapping/quarantine/acceptance, original/normalized evidence, repeat CSV/workbook, changed delivery, durable verification/reopen and packet download; NPPES/CMS saved JSON, native location relationship; loading/empty/failed/retry/keyboard/source layout and stale-version draft recovery. Existing compatibility scenarios are preserved.
- CI now installs Chromium, runs isolated browser scenarios and uploads failure traces. Configuration is locally qualified; no remote CI execution is claimed because this branch has not been pushed.

### Measured bounded import

Apple M4 (`Mac16,12`), Python 3.13, one local process. `PYTHONPATH=src python3 scripts/benchmark_intake.py 1000` and `... 20000` produced the retained [1,000-row](benchmark-1000.json) and [20,000-row](benchmark-20000.json) synthetic measurements. The latter previewed in 1.14 s and accepted in 9.862 s, peak process RSS 311.5 MiB. Integrity was `ok`, with zero FK violations. Timing is machine/workload-specific; no equivalent XLSX/concurrent-user claim follows. Uploads above 10 MiB or 20,000 rows fail explicitly.

### Integrated live reads

[live-smoke-summary.json](live-smoke-summary.json) retains request scopes/times/status/count/hash/truncation and CMS publication metadata without committing public clinician rows. At 21:27 UTC, HTTP-200 NPPES Nashville/TN limit 1 and CMS unfiltered limit 1 each produced one valid preview. Both were truncated. Exact originals and database are local at `.runtime/live-smoke-20261023/`; those files are ignored. These observations do not establish complete-directory coverage, payer errors, credentials, or current operational accuracy.

## Final gate receipt — all G0–G5 passed locally

Qualified application lineage: `00bef56` (core), `c705740` (contracts/demo docs), `8f65336`/`1f81331` (lookup form regression), `5fa02d2` (tooling), `23c2b10` (launcher lifecycle). Later evidence-only commits do not change the application. No push, merge, deployment or remote CI run occurred.

| Check | Observed result |
| --- | --- |
| `python3 -m pytest -q` | **103 passed** in the working checkout. |
| `make validate` in clean checkout | **103 passed**, then isolated pipeline validation: 12 records, 11 QA findings, six configured discrepancies. |
| `npm test --prefix web` after tooling update | **3 files / 3 tests passed**, including source-specific CMS lookup query. |
| `npm run build --prefix web` | TypeScript and Vite **6.4.5** production build passed. |
| `npm run test:e2e --prefix web` in clean checkout | **12 passed**, desktop/phone; final full run 39.7 seconds, no server reuse. |
| `npm ci --prefix web --offline` after dependency setup | Passed in clean checkout with the final lockfile; initial cache lacked one baseline package and required normal dependency installation first. |
| `npm audit --prefix web` | **0 known vulnerabilities** after Vitest 5.0.5/Vite 6.4.5 refresh; not a security certification. |
| Fresh local editable install | Version 2.0.0 installed into a separate venv with preinstalled dependency access; no production environment claim. |
| `scripts/demo.py --prepare-only --root ...` | Fresh inputs/database created offline; repeat prepare retained the selected root. |
| Real launcher start/stop/resume | HTTP API and UI 200; accepted two synthetic observations; restart retained receipt `74695b6cf2874d249cb0cca70b521a72`, exact artifact digest and both observations. Ctrl-C stopped both service groups, exit 0. |
| Original runtime SHA-256 comparison | All **eight** original database/output files unchanged from the initial preservation manifest. |
| Git/link/whitespace/process reconciliation | Local links and `git diff --check` passed; no project listeners left on 8000/8100/5173/5180. |

### Fresh-checkout reproduction

A local clone (no hardlinks) at `.runtime/fresh-checkout` contains no original runtime data. It was cloned from this implementation branch, installed with `npm ci`, then fast-forwarded to the final application commit. Python setup used a separate venv with existing dependencies; the demo/fixtures/browser flows require no account or network after installation.

```bash
git clone --no-local <repository-url> .runtime/fresh-checkout
cd .runtime/fresh-checkout
python3 -m venv --system-site-packages .runtime/qualification-venv
.runtime/qualification-venv/bin/python -m pip install --no-build-isolation --no-deps -e .
npm ci --prefix web
PYTHONPATH=src .runtime/qualification-venv/bin/python scripts/demo.py --prepare-only --root .runtime/fresh-demo
make validate
npm test --prefix web
npm run build --prefix web
npm run test:e2e --prefix web
```

For a reviewer without preinstalled Python dependencies, use the README's ordinary `python3 -m pip install -e '.[dev]'` setup instead. Chromium installation is a dependency setup step. Deterministic tests use synthetic fixtures; live network smoke is separate.

### Selected synthetic UI evidence

Captured by the passing clean-checkout Playwright scenarios. Desktop accepted intake and phone conflict/work layout were directly visually inspected; screenshots supplement the behavioral assertions and do not constitute a screen-reader/contrast audit.

- [XLSX accepted: original/normalized evidence and quarantine](screenshots/xlsx-desktop.png)
- [Changed delivery and retained later evidence](screenshots/later-evidence-desktop.png)
- [Reopened correction with observed result](screenshots/work-reopened-desktop.png)
- [Failed import and reprocess controls](screenshots/failed-import-desktop.png)
- [Loading](screenshots/loading-desktop.png) and [empty inbox](screenshots/empty-desktop.png)
- [Phone layout with preserved stale-version draft after refresh](screenshots/conflict-draft-phone.png)
- [Phone source registry](screenshots/sources-phone.png)

Full browser run artifacts remain under ignored `.runtime/fresh-checkout/web/test-results/`; CI retains failure traces when applicable. The synthetic workbook/CSV/JSON inputs are reproducibly generated by `scripts/demo_fixtures.py` rather than retaining a mutable demo database in Git.

### Genuine limits

Core correction comparison is explicit location-phone listed/requested evidence; legacy configured payer-field comparison is preserved separately. Bounded requests use worker threads/persisted attempts rather than asynchronous job progress. Queue summaries are loaded locally with bounded rendering, not server pagination. Compatibility QA is current-batch; old originals are not reconstructed. Verification and identity relationship attribution are manually asserted. Live-source availability/accuracy/completeness, remote CI, full accessibility, concurrent-user performance, hosting/authentication/payer writeback and FHIR are not qualified or implemented by these results.


## Subsequent focused follow-up

The [2026-10-26 employer-readiness evidence](../employer_readiness/README.md) separately qualifies guided synthetic samples and durable XLSX handoff. Historical test counts, screenshots, live observations and measured limits above remain dated baseline evidence.
