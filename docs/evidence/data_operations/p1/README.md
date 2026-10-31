# Operational SQL qualification — 2026-10-30

`make validate` passed **130 Python tests**, plus isolated pipeline validation (12 records/11 findings/six discrepancies). Separate `python3 -m pytest -q`: **130 passed**, one upstream TestClient deprecation warning, no failures/skips. [Validation](validate.txt), [Python](pytest.txt). Frontend/application browser code is unchanged from the [passing core snapshot](../p0/README.md).

Six focused SQL tests cover null/empty values, missing lineage, evidence/event fan-out, tied event timestamps, actionable deferred versus closed resolved/verified cases, explicit accepted-delivery selection and incompatible/ambiguous selection rejection. The CLI executes in a subprocess against an open WAL fixture; durable database/WAL/artifact hashes remain unchanged. Transient SQLite shared-memory reader-lock bytes can change. Reads pin one snapshot and close their connection.

See [commands, row grain and expected synthetic results](../../../OPERATIONAL_SQL.md). No database-server portability or new application preview behavior is claimed by this query slice.


## Public-source qualification — 2026-10-31

The SQL files, runner, six regression tests, and query guide were copied without implementation changes onto public main `572f891`. Their Git blob hashes match the previously merged implementation. The durable intake store also matches that implementation exactly; no schema, API, frontend, dependency, or workflow changes were needed. README, state, progress, and proposal status now distinguish implemented CLI queries from planned recurring-import/application comparison features.

Fresh checks in an isolated public checkout:

- `make validate`: **130 Python tests passed** with one upstream TestClient deprecation warning; pipeline validation passed with 12 records, 11 findings, and six discrepancies. [Sanitized log](publication-2026-10-31-validate.txt).
- `python3 -m pytest -q tests/test_operations_sql.py`: **six passed** against newly created disposable SQLite fixtures.
- `npm test --prefix web`: **six frontend tests passed**; `npm run build --prefix web`: TypeScript and production build passed.
- `npm run test:e2e --prefix web`: **14 desktop/phone browser scenarios passed**, using invocation-owned temporary storage.
- All four CLI commands matched the guide's expected synthetic results. [JSON outputs and before/after database/artifact hashes](publication-2026-10-31-cli.json). The separate WAL regression also passed.

Reproduce the CLI results from the repository root after installing development dependencies:

```sh
python3 -m pytest -q tests/test_operations_sql.py::test_follow_up_lineage_latest_and_read_only --basetemp=.runtime/sql-practice
PYTHONPATH=src python3 -m provider_directory_truth_layer.operations_sql --db .runtime/sql-practice/test_follow_up_lineage_latest_0/intake.sqlite3 follow-up --as-of 2026-02-01
PYTHONPATH=src python3 -m provider_directory_truth_layer.operations_sql --db .runtime/sql-practice/test_follow_up_lineage_latest_0/intake.sqlite3 lineage --case-id c1
PYTHONPATH=src python3 -m provider_directory_truth_layer.operations_sql --db .runtime/sql-practice/test_follow_up_lineage_latest_0/intake.sqlite3 latest-event
PYTHONPATH=src python3 -m provider_directory_truth_layer.operations_sql --db .runtime/sql-practice/test_follow_up_lineage_latest_0/intake.sqlite3 compare --left-attempt a1 --right-attempt a2
```

The `--basetemp` directory is disposable and pytest replaces it on rerun; keep practice data there only. The fixture is deliberately synthetic and minimal; normal application databases retain schema v2.

Publication review: only the selected feature, synthetic test/output data, sanitized evidence, and necessary documentation are included. Added content was reviewed for private data, machine-local paths, credentials, and private preparation material. The branch descends solely from public main; no private commits, refs, or history were imported. Local qualification and GitHub CI are separate results; the PR check reports remote CI.
