# Export scope and launcher hardening

This is dated local regression evidence. This is a separate regression pass after the [original employer-readiness qualification](../README.md); earlier counts/screenshots remain dated evidence.

## Reproduced defects and fixes

1. A later NPPES observation linked to SOUTH exported NORTH’s primary address, ZIP and phone because the exporter used the native default projection. Later Evidence now applies the latest explicit relationship matching the observation and the case’s provider/location, including its selected native address and row locator. The initial case snapshot and full native payload remain unchanged.
2. A SOUTH-only workbook included NORTH relationships and labeled them with the SOUTH case ID. Relationship export now includes only matching provider/location assertions for each case; shared native originals remain complete in Payloads. Both selected and all-work workbooks are checked.
3. The offline launcher returned success after a child service failed. It now returns failure for unexpected API/UI exits (including an unexpected zero exit), stops its invocation-owned service groups including remaining descendants, and preserves storage. Port conflicts fail before preparing a root; prepare-only needs no free ports. Ordinary Ctrl-C remains successful.

A bounded Sol/medium reviewer independently reproduced the two scope defects and authored only `tests/test_work_export_scope.py`. The primary implemented exporter/launcher fixes, launcher regressions, integration, docs and verification. No schema/API expansion, native observation rewrite or additional feature scope was needed.

## Fresh checks

| Command | Result | Evidence |
| --- | --- | --- |
| `python3 -m pytest -q` | 124 passed; zero failures/skips | [Python](pytest.txt) |
| `make validate` | 124 passed; isolated pipeline 12 records, 11 findings, six discrepancies | [Pipeline](validate.txt) |
| `npm test --prefix web` | Six tests / three files passed | [Frontend](frontend.txt) |
| `npm run build --prefix web` | TypeScript/Vite 6.4.5 build passed | [Build](build.txt) |
| `npm run test:e2e --prefix web` | 14 desktop/phone scenarios passed; zero failures/skips; actual XLSX downloads inspected by openpyxl assertions | [Browser](browser.txt) |
| Real occupied-port / child failure / restart / Ctrl-C rehearsal | Passed with isolated local processes and fresh owned storage | [Launcher summary](launcher-summary.json), [port-conflict output](port-conflict.log) |
| Prior runtime preservation | All 272 pre-existing files unchanged | [Preservation](preservation-summary.json) |

The new native-scope regression exports through the actual HTTP route, checking both deliveries’ SOUTH phone/address/ZIP/locator, selected/all-work relationship attribution, unchanged native payloads and no database/artifact mutation. Nine launcher regressions cover occupied-port preflight, both children unexpectedly exiting with zero/nonzero status, Ctrl-C, descendants of an exited launcher, unavailable executables and prepare-only preservation.

## Real launcher rehearsal

`python3 .runtime/employer-readiness-hardening/check_launcher.py` ran against a fresh owned root. It temporarily occupied port 8000 and confirmed exit 1 with no requested root created. After releasing that listener it launched the ordinary demo, loaded/accepted the synthetic CSV and assigned an owner. It identified only its own API child by parent PID and module command, then sent that child SIGTERM. The parent returned 1, stopped its UI sibling and released both ports, retaining identical database and input/artifact bytes. Resuming the same root retained the owner and exact snapshot; Ctrl-C returned 0 and released both ports. Counts: one receipt, two observations, two cases, one event.

Full controller, before/after snapshots, failure/resume logs, preservation manifest and retained demo root are under ignored `.runtime/employer-readiness-hardening/`. Earlier `web/test-results/` were copied into that root before the browser rerun. The existing synthetic UI screenshots still describe the unchanged controls/layout; this continuation adds export-content and service-lifecycle evidence, not a new visual-design qualification.

No services remain running. No public-source network check, remote CI, push, merge, deployment, shared installation, publication, production-data validation or accessibility certification was performed. The local/synthetic/asserted-verification and scope boundaries remain unchanged.
