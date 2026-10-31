# Operational SQL qualification — 2026-10-30

In the original 2026-10-30 SQL checkout, `make validate` passed **130 Python tests**, plus isolated pipeline validation (12 records/11 findings/six discrepancies). Separate `python3 -m pytest -q`: **130 passed**, one upstream TestClient deprecation warning, no failures/skips. [Validation](validate.txt), [Python](pytest.txt). This SQL slice does not modify the frontend or browser tests; the public branch's current CI is evaluated separately from the [core snapshot](../p0/README.md).

Six focused SQL tests cover null/empty values, missing lineage, evidence/event fan-out, tied event timestamps, actionable deferred versus closed resolved/verified cases, explicit accepted-delivery selection and incompatible/ambiguous selection rejection. The CLI executes in a subprocess against an open WAL fixture; durable database/WAL/artifact hashes remain unchanged. Transient SQLite shared-memory reader-lock bytes can change. Reads pin one snapshot and close their connection.

See [commands, row grain and expected synthetic results](../../../OPERATIONAL_SQL.md). No database-server portability or new application preview behavior is claimed by this query slice.
