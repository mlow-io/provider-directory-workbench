# Final data-operations demonstration qualification — 2026-10-30

The final sanitized source candidate passed **168 Python tests**, isolated pipeline validation (12 records/11 findings/six discrepancies), **14 frontend tests**, production build and **22 desktop/phone-sized Chromium scenarios**. No final failures/skips. One upstream Starlette TestClient/httpx deprecation warning remains. Dependencies were installed in the candidate's isolated virtual environment; npm lock/dependencies are unchanged from the fresh core install.

| Command | Result | Log |
| --- | --- | --- |
| `make validate` | 168 tests; isolated pipeline 12/11/6 | [Validation](validate.txt) |
| `python3 -m pytest -q` | 168 passed | [Python](pytest.txt) |
| `npm test --prefix web` | 14 passed | [Frontend](frontend.txt) |
| `npm run build --prefix web` | TypeScript/Vite production build passed | [Build](build.txt) |
| `npm run test:e2e --prefix web` | 22 passed | [Browser](browser.txt) |

## Observed operator journey

The browser explicitly prepares the synthetic codebook, loads the network baseline, fills/reviews scope, saves/applies a mapping and accepts three assertions. Changed delivery shows raw5/unique3, valid2/quarantined3, new1/changed1/blocked2/unresolved1/missing1. It accepts valid rows only, reviews scoped QA, assigns an owner, inspects selected JSON/XLSX, then blocks renamed phone headers and recovers through a newly reviewed mapping revision. The old revision and initial human/source evidence remain intact.

The full guided scenario uses both desktop and 390px widths, retaining the phone viewport through changed acceptance, work assignment and downloads. A separate mobile-project case checks the compact entry without repeating mutation of the fixed demo namespace. Earlier clinic/recurring/network journeys still run independently at desktop and phone sizes. Screenshots were visually inspected: [entry desktop](network-entry-desktop.png), [entry phone](network-entry-phone.png), [comparison desktop](network-comparison-desktop.png), [comparison phone](network-comparison-phone.png), [work desktop](network-work-desktop.png), [work phone](network-work-phone.png). Overflow assertions pass; this is not a real-device or accessibility certification.

## Real launcher, migration and preservation

A separate owned v2 database with original synthetic receipts/observations/cases/events and five input files was launched through the normal current demo. Additive v2→v4 migration retained every original row and six original input/artifact hashes, with versioned SQLite backups. The real multi-file workflow accepted the unfamiliar clinic workbook (2 valid/1 quarantined), network baseline and changed file, assigned ownership and inspected scoped XLSX/JSON.

Stop/resume retained an exact relational/input/artifact snapshot. Repeat delivery reused its interpretation without duplicate work. Renamed-header recovery saved a new mapping revision and retained initial case evidence, owner and human history. Scoped PINE handoff contained three cases, two accepted participation evidence rows, four comparison evidence rows, referenced catalog/bindings and zero formulas. Reads left stored state unchanged. Final integrity/FK checks passed. [Rehearsal summary](final-rehearsal-summary.json).

All **7,449** pre-existing files were preserved: **7,411 unchanged in place**, with **38 prior generated browser output files retained in a checked copy** before reruns. Original working runtime/legacy outputs were preserved; no working database was cleaned/reseeded. [Preservation summary](preservation-summary.json). Full before/after manifests, original logs, controllers, owned migration roots, exact downloaded workbooks/JSON and backups remain retained locally.

## Integration findings and limits

The final pass corrected network-source assumptions in the original sample regression and an ambiguous mapping-summary browser locator. Remote SQL-slice CI also exposed a repeat-sample test race; the browser now waits for the new receipt ID before filling reviewer inputs. All 22 browser scenarios were rerun successfully locally. A late no-mutation check exposed retained writable SQLite connections: native connection contexts transact without closing, so GC could checkpoint an earlier writer during a later read. Shared connection contexts and backup targets now close deterministically, with commit/rollback/close/WAL and GC regressions; read-only snapshots still use explicitly closed mode=ro connections. Final scope review also verified that later accepted organization assertions retain all referenced catalog/binding records while initial case scope/history stays unchanged.

Public-source reads were not rerun. Source status, reported dates, completeness and human verification remain separate assertions; absence never terminates membership. This is a bounded local workbench, without authentication, hosting, payer writeback, automatic entity merge or production-concurrency claims. Local qualification is separate from GitHub branch checks, pull requests and default-branch adoption.
