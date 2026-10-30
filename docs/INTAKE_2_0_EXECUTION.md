# Intake Workbench implementation guide

The [proposal](INTAKE_2_0_PROPOSAL.md) describes desired behavior. [Project state](../PROJECT_STATE.md) and [progress](INTAKE_2_0_PROGRESS.md) distinguish implemented capabilities from planned work. The [review](INTAKE_2_0_REVIEW.md) records baseline findings; [decisions](DECISIONS.md) records implemented design choices.

## Product decisions

The workbench focuses on evidence-backed provider directory intake and review. Earlier KPI reporting ideas are outside this product scope. Preserve source and normalized records, distinct receipts and processing attempts, original artifacts, and accountable work history. A repeated delivery can add a receipt without duplicating work. A provider NPI alone does not identify a practice location or payer-network participation. Incomplete identity remains unresolved; a bounded source response missing a record is not proof of termination. Human verification is an explicit workflow action, never inferred from later source data.

## Contributor workflow

Read [README](../README.md), [operations workflow](OPERATIONS_WORKFLOW.md), [data dictionary](DATA_DICTIONARY.md), [API reference](API_REFERENCE.md), and [public-source notes](PUBLIC_DATA_SOURCES.md) before changing contracts. Keep the SQLite/artifact/FastAPI/React architecture small and make additive migrations preserve existing receipts, work, events and artifacts. Use synthetic fixtures and isolated `PDTL_ROOT` storage; validation and browser suites create their own roots. No check should clean a working database. Keep proposal language separate from shipped behavior.

For pipeline changes run `make validate`; for Python changes run `pytest -q`; for frontend changes run `npm test --prefix web` and `npm run build --prefix web`; for review-console behavior or responsive changes also run `npm run test:e2e --prefix web`. Inspect downloads and rendered operator journeys when they are part of a claim. Record exact results and limits in dated evidence. The [delivery checkpoints](INTAKE_2_0_PROPOSAL.md#delivery-checkpoints-and-documentation-updates) define the next slices.
