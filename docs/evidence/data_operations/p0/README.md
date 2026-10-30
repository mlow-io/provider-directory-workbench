# Core snapshot qualification — 2026-10-30

The selected source snapshot was installed in a fresh Python virtual environment and with `npm ci`; checks used invocation-owned storage. No application behavior changed during snapshot preparation. Historical evidence elsewhere remains dated.

| Command | Result | Log |
| --- | --- | --- |
| `make validate` | 124 tests; pipeline 12 records, 11 findings, six discrepancies | [Validation](validate.txt) |
| `python3 -m pytest -q` | 124 passed; no failures/skips | [Python](pytest.txt) |
| `npm test --prefix web` | Six tests passed | [Frontend](frontend.txt) |
| `npm run build --prefix web` | Passed | [Build](build.txt) |
| `npm run test:e2e --prefix web` | 14 desktop/phone scenarios passed | [Browser](browser.txt) |

Environment: Python 3.13.2, Node 22.17.0, npm 10.9.2; fresh Python dependencies include FastAPI 0.162.0, Starlette 1.10.0, pandas 2.3.3 and openpyxl 3.1.5. One Starlette TestClient/httpx deprecation warning was observed; tests pass. npm installation reported zero known vulnerabilities.

The browser exercised synthetic sample → reviewed mapping → valid-row acceptance → case assignment → selected/all-work XLSX downloads. Download assertions inspect ownership, NORTH/SOUTH scope, original row locators, leading-zero ZIP, history and formula count, and confirm reads leave work unchanged. The fresh rendered quarantine preview was visually inspected. Earlier unchanged launcher/recovery regressions and preservation rehearsals remain linked from [hardening evidence](../../employer_readiness/hardening/README.md).

Logs here are visibly labeled publication copies with local paths normalized; exact logs remain locally retained. These local results do not establish remote CI, production concurrency, accessibility certification or public-source accuracy. The offline fixtures are synthetic and no payer changes are sent.
