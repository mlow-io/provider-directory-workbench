# Contributor guide

Read `PROJECT_STATE.md` and `README.md` first, then `docs/OPERATIONS_WORKFLOW.md` and `docs/DATA_DICTIONARY.md`. The proposal is desired behavior; current state and progress identify what is implemented.

Keep committed demo data synthetic. Preserve source and normalized records, original artifacts, receipts and append-only work history. Duplicate matches remain candidates for human review. Keep this local application scoped; authentication, hosting, multitenancy, bulk actions and automatic entity merging are outside the roadmap.

Use isolated `PDTL_ROOT` storage for development and validation. Run `make validate` for pipeline changes, `pytest -q` for Python changes, `npm test --prefix web` and `npm run build --prefix web` for frontend changes, and `npm run test:e2e --prefix web` for review behavior or responsive UI changes. Update domain documentation when public behavior or contracts change.
