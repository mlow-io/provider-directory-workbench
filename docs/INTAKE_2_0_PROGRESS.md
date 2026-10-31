# Intake Workbench delivery status

Updated 2026-10-31. The G0–G5 intake workbench, guided synthetic demo, read-only XLSX handoff, and P1 [operational SQL slice](OPERATIONAL_SQL.md) are implemented. N1–N4 recurring-import/network capabilities in the [roadmap](INTAKE_2_0_PROPOSAL.md#delivery-checkpoints-and-documentation-updates) remain planned.

## Verified historical checkpoints

- [G0–G5 evidence](evidence/intake_2_0/README.md): 103 Python tests, isolated pipeline validation, three frontend tests, production build, and 12 desktop/phone browser scenarios. Retained originals, quarantine, explicit acceptance, repeat/restart, and source-scoped work were exercised.
- [Guided demo evidence](evidence/employer_readiness/README.md): 114 Python tests, six frontend tests, 14 browser scenarios, inspected XLSX downloads and rendered desktop/phone screenshots. A fresh offline start/stop/resume retained two cases, 10 decisions, four receipts, six observations, and exact input/artifact hashes.
- [Regression hardening evidence](evidence/employer_readiness/hardening/README.md): 124 Python tests, isolated pipeline validation, six frontend tests, production build, and 14 browser scenarios. Export scope and launcher failure/restart behavior were checked; 272 prior runtime files remained unchanged.

Fresh [2026-10-30 core snapshot qualification](evidence/data_operations/p0/README.md) passed 124 Python tests, pipeline validation, six frontend tests, production build and 14 browser scenarios. The [2026-10-30 P1 SQL qualification](evidence/data_operations/p1/README.md) recorded 130 Python tests and isolated pipeline validation in the original SQL checkout, including six SQL regressions; its [synthetic fixture tests](../tests/test_operations_sql.py) exercise all four queries and a read-only CLI invocation. The entries above remain historical. Live NPPES/CMS smoke results and the 20,000-row CSV measurement are bounded historical observations in the G0–G5 evidence. Remote CI, full accessibility, production concurrency, and public-data accuracy are not established by them.

## Next delivery

Build N1 saved mappings and application-workflow accepted-delivery comparisons, followed by N2–N4 scoped organization/network records and multi-file demonstration. The P1 read-only SQL pack and runner already exist. Update the API, data, workflow, and operator documents alongside each implemented slice. The supported offline entry is `make workbench`; follow the [demo procedure](operations_governance/sop_provider_remediation.md).
