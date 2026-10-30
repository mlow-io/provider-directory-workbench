# Intake Workbench delivery status

Updated 2026-10-30. **P0–P3 application scope is implemented and locally qualified. Feature pull-request/default-branch adoption is a separate pending gate.**

The [final receipt](evidence/data_operations/n4/README.md) records 168 Python tests, pipeline 12/11/6, 14 frontend tests, build and 22 desktop/phone-sized browser scenarios, inspected actual JSON/XLSX/screenshots, real v2→v4 migration/restart/repeat/header recovery and preservation of 7,449 prior files. No final local failures/skips; one upstream TestClient warning.

Delivered: read-only operational SQL, immutable recurring mappings, accepted-delivery/binding freshness, exact organization/network/location identity, scoped comparison QA, JSON/XLSX handoffs and guided synthetic multi-file recovery. Use `make workbench` and the [SOP](operations_governance/sop_provider_remediation.md#guided-multi-file-network-demonstration). [Project state](../PROJECT_STATE.md) and [limits](../README.md#supported-inputs-and-limits) describe the current contract.

This is a reviewed feature snapshot. Consult this exact branch/commit's GitHub Actions for remote qualification; do not infer default-branch adoption from branch publication. CI supports manual workflow_dispatch for explicit replay. Earlier [N1](evidence/data_operations/n1/README.md), [N2](evidence/data_operations/n2/README.md) and [N3](evidence/data_operations/n3/README.md) receipts remain dated evidence. No release, hosting, certified participation or payer update is claimed.
