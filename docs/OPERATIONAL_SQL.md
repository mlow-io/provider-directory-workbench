# Operational SQL questions

This source-checkout tool reads an existing durable intake SQLite database. It does not initialize `IntakeStore`, run migrations, import files, or change workflow state. Use a fixture-owned database when practicing. The four queries live in [`sql/operations/`](../sql/operations/) and declare their row grain and parameters in their opening comments.

Run from the repository root with an editable install, or set `PYTHONPATH=src`:

```sh
PYTHONPATH=src python3 -m provider_directory_truth_layer.operations_sql --help
PYTHONPATH=src python3 -m provider_directory_truth_layer.operations_sql --db /path/to/intake.sqlite3 follow-up --as-of 2026-02-01
PYTHONPATH=src python3 -m provider_directory_truth_layer.operations_sql --db /path/to/intake.sqlite3 lineage --case-id CASE_ID
PYTHONPATH=src python3 -m provider_directory_truth_layer.operations_sql --db /path/to/intake.sqlite3 latest-event
PYTHONPATH=src python3 -m provider_directory_truth_layer.operations_sql --db /path/to/intake.sqlite3 compare --left-attempt ACCEPTED_A --right-attempt ACCEPTED_B
```

Results are JSON arrays. Exact IDs come from the selected database; no sample ID is inferred by the runner.

| Question | One result row means | Parameters | Synthetic fixture expectation |
| --- | --- | --- | --- |
| `follow-up` | One work case needing assignment or overdue follow-up, excluding resolved/verified cases by default. | `--as-of YYYY-MM-DD` (default today); `--include-closed` includes resolved/verified cases. | At `2026-02-01`, `c1`, overdue deferred `c4`, and unassigned due-today `c7` are returned. |
| `lineage` | One work-case/linked-observation pair, including original and normalized row payload, locator, attempt, receipt, and artifact hash. | `--case-id` exact case ID. | `c1` has three rows, `o1`–`o3`; `c2` has one row with null observation and receipt fields. |
| `latest-event` | One work case and its latest event, or null event fields if it has no events. | None. | Seven case rows; `c1` selects action `note` over `assign` at the same timestamp using higher event ID. |
| `compare` | One source-native identity present in either selected accepted delivery, with old/new normalized JSON and row locators. | Two explicit attempt IDs. | `a1` versus `a2`: `native-a` changed, `native-b` missing from right, `native-c` new. |

All queries use SQLite syntax and bound parameters. `latest-event` requires window-function support (SQLite 3.25+); `compare` requires JSON1. The runner opens `mode=ro` and enables `query_only`. `follow-up` treats null/blank owner as unassigned, null follow-up as not overdue, and a date equal to `as_of` as due today. `lineage` preserves cases without links through left joins. The latest-event query ranks events before joining them to cases, so a case with several evidence links cannot multiply its result.

Comparison selects two **accepted attempts**. A `duplicate_delivery` attempt is accepted but has no new observations: its recorded `preview.reuses_attempt` must point to a committed attempt of the same source, profile, and scope. Selecting two attempts that resolve to the same committed interpretation is rejected. Different source, profile, or declared `metadata.scope` values are rejected. The key is `native_id` plus normalized `location_id` within that source/scope; null and empty location IDs share the empty key. A missing/blank native ID or duplicate key makes that selected comparison ambiguous, so the runner rejects it. Rows with null *field values* remain comparable, and JSON null differs from an absent field or empty string. `missing_from_right` means absent from this bounded delivery, **not** terminated or removed. This tool compares accepted rows only and does not alter the application's current preview comparison semantics or claim a complete source history.

Fixture regression: `pytest -q tests/test_operations_sql.py`. The test hashes the SQLite file and an original artifact before/after the read-only questions; it also verifies the durable database and WAL bytes with a live WAL writer. SQLite may update transient `-shm` reader-lock bytes while answering a read query.
