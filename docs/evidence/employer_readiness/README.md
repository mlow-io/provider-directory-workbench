# Employer-readiness follow-up evidence

Qualified locally on 2026-10-26 (America/Chicago; browser/runtime timestamps cross into 2026-10-27 UTC). This is dated local evidence for the guided-demo implementation. The [2026-10-23 G0–G5 evidence](../intake_2_0/README.md) remains the separate historical baseline.

## Delivered scope

- Explicit offline sample picker, shared deterministic XLSX/CSV/saved-response fixtures, normal retained intake/parsing, editable suggested columns and explicit acceptance. Sample loading is disabled on ordinary startup; `scripts/demo.py` enables `PDTL_DEMO=1`. All picker receipts are visibly synthetic and use `synthetic-demo`.
- Read-only XLSX handoff for every durable case or exactly the selected case. Full initial/later evidence, scoped native relationships, related/repeat receipts and attempts, current ownership/follow-up, and append-only decisions use one read-only SQLite snapshot. Full JSON payloads are chunked, identifiers/formula-like inputs stay literal text, and source/verification dates and listed/requested/approved/observed values stay distinct.
- No schema migration, source overwrite, automatic acceptance/verification or entity merging; no external writes or public network reads required for these checks.

## Reproducible checks

| Command | Fresh observed result | Retained log |
| --- | --- | --- |
| `python3 -m pytest -q` | 114 passed in 7.67 s; zero failures/skips | [Python](pytest.txt) |
| `make validate` | 114 passed in 7.83 s, then isolated pipeline: 12 records, 11 findings, six discrepancies | [Pipeline](validate.txt) |
| `npm test --prefix web` | Six tests / three files passed | [Frontend](frontend.txt) |
| `npm run build --prefix web` | TypeScript and Vite 6.4.5 production build passed | [Build](build.txt) |
| `npm run test:e2e --prefix web` | 14 passed in 34.8 s, wide 1440×960 and iPhone 13 390×844; zero failures/skips | [Browser](browser.txt) |
| Real offline start/stop/resume | Exact case/event/receipt/observation row equality plus input/artifact hashes: two cases, 10 decisions, four receipts, six observations | [Restart receipt](restart-summary.json) |
| Prior runtime/original comparison | All 137 previously recorded files unchanged | [Preservation receipt](preservation-summary.json) |

Python 3.13.2, FastAPI 0.116.1, openpyxl 3.1.5; existing local dependencies were used. No shared installation, push, remote CI run, merge, deployment or publication occurred. No new live public-source smoke, large-scale performance benchmark, screen-reader or contrast certification was run.

`tests/test_employer_readiness.py` adds 11 tests: explicit sample mode; every fixed sample through normal intake; manual mapping/acceptance; repeat/restart; XLSX null/empty/literal-NA/leading-zero/formula fidelity; exact long Unicode/control payload reconstruction; 205 cases, 56 observations on one case and 55 decisions without UI truncation; native practice-address scope; no export mutation; and a real writer committing after the export's first SELECT without contaminating its snapshot. Existing compatibility tests remain intact.

`web/e2e/employer-readiness.spec.ts` exercises mapping suggestions without saving/accepting, malformed row visibility, explicit acceptance, accidental repeats, ownership/follow-up, filtered queue versus all-work scope and both browser downloads. It opens the actual downloaded XLSX with openpyxl and checks contents and unchanged case state. The other 12 scenarios cover the preserved intake/public-fixture/compatibility workflows, verification/reopen, failure/retry, keyboard and stale-conflict behavior.

The initial new browser scenario failed on an overly strict test label locator (the mapping itself was filled); correcting the locator resolved it. Local port binding first required sandbox approval. A subsequent passing suite tightened fixture generation into an invocation-owned temporary input root and passed all 14 again. Final review also added a passing regression for control-character escaping expanding a scalar beyond Excel’s cell size; the exporter checks the escaped display length before choosing a complete payload reference. Raw first-attempt logs are retained locally; these are not unresolved application failures.

## Real offline rehearsal and visual inspection

Fresh launch: `PYTHONPATH=src python3 scripts/demo.py --root .runtime/employer-readiness-20261026/demo`. From the actual browser, loaded and reviewed the messy workbook, inspected original/normalized ZIP `02108` and quarantined `Clinic roster!5`, explicitly accepted two valid sites, assigned an owner/follow-up, triaged/approved/simulated submission and asserted verification. NORTH matched `6175550199` and verified; SOUTH observed `6175550170` against approved `6175550198` and reopened. Each case retained five decisions. CSV and changed deliveries attached later evidence; an accidental repeat reused interpretation without duplicate work.

Downloaded `rehearsal-case.xlsx` through the UI and inspected all eight sheet names, SOUTH scope, owner/follow-up, five decisions and distinct phone values with openpyxl. Ctrl-C stopped both service groups (exit 0); the same command resumed the retained root without reseeding or rewriting inputs. Exact row/hash comparison passed, then the phone UI showed NORTH still verified at version 5 and SOUTH still reopened. Services were stopped after inspection.

Screenshots below were captured from that real synthetic rehearsal and their rendered contents were directly inspected. Desktop/phone first views show the healthcare problem, synthetic label and visible load action. Row detail shows retained bad-row evidence and leading-zero ZIP. Case detail shows scoped phone values, action form, owner/follow-up and history; the resumed phone view shows preserved status and the case download. No horizontal overflow, overlap or unreadable primary controls was observed in these inspected states. Long evidence panels intentionally scroll. This is bounded usability evidence, not a full accessibility audit.

- [Desktop first screen](screenshots/demo-entry-desktop.png)
- [Phone first screen](screenshots/demo-entry-phone.png)
- [Messy workbook original/normalized/quarantined rows](screenshots/demo-rows-desktop.png)
- [SOUTH reopened correction and five decisions](screenshots/demo-work-desktop.png)
- [Phone after resume, NORTH verified](screenshots/demo-resumed-phone.png)

The exploratory pass also checked changing sample shapes, repeat loading, later evidence without workflow overwrite, narrow navigation and an empty queue filter while exporting all work. Development console observations were a missing favicon and expected Vite reconnect failures while the launcher was deliberately stopped; no functional browser error remained during the passing journeys.

## Local retained artifacts and boundaries

Ignored `.runtime/employer-readiness-20261026/` contains complete checks/first-attempt logs, preservation manifest, exact before/after restart snapshots, downloaded workbook, original screenshots and the retained demo root. Browser-suite downloads/screenshots remain in `web/test-results/`; its database and input files use separate invocation-owned temporary roots printed in browser logs. Original legacy runtime and earlier qualification evidence remain preserved.

This is a local portfolio project with synthetic operational examples, bounded public-reference adapters and locally asserted verification. It is not production employment, a payer deployment, certified provider truth, HIPAA certification or automatic identity resolution. Excel capacity and local in-memory export limits remain documented in the [data contract](../../DATA_DICTIONARY.md#durable-work-handoff-workbook).


## Subsequent regression hardening

The [continuation after `2cfb5e1`](hardening/README.md) fixes later multi-address evidence/relationship scope and offline-launcher failure handling, with 124 Python tests, the unchanged six frontend/14 browser checks, and real failure/restart preservation evidence. Original qualification above remains historical.
