# Five-minute offline employer demonstration

Updated 2026-10-26. This is a synthetic portfolio demonstration, not employer policy, licensure verification, payer writeback or a compliance certification.

## Launch and preserve

After dependency setup in the [README](../../README.md), run `make workbench`. It creates a fresh root, prints the input directory, and starts one API on 8000 plus Vite on 5173. Open `http://127.0.0.1:5173/?view=intake`. Ctrl-C retains the root. Resume with `PYTHONPATH=src python3 scripts/demo.py --root <printed-root>`. No startup cleanup or implicit reseed occurs on resume.

## Demonstrate the operator journey

1. In Intake, choose **Synthetic clinic workbook → Load synthetic sample**. The UI explains the patient-contact problem and labels the evidence synthetic. The launcher explicitly enables sample mode; ordinary service startup does not. Header row **2** and worksheet `Clinic roster` are selected. Click **Use suggested columns**, review/edit the mappings below, then **Save mapping and reprocess**. Loading and filling suggestions make no acceptance decision. Samples use the fixed `synthetic-demo` namespace.

   Ordinary uploads remain available: select `<root>/inputs/synthetic-clinic.xlsx` under any explicit namespace, choose header row 2, reprocess and map the columns manually.

| Canonical field | Workbook header |
| --- | --- |
| npi | Registry number |
| provider name | Clinician |
| address | Street |
| city | Town |
| state | Region |
| zip | Postal |
| phone | Listed phone |
| record id | Roster key |
| location id | Site key |
| reference phone | Requested phone |

2. Save mapping: inspect **2 valid, 1 quarantined**. Expand an original/normalized row and show ZIP `02108`. Download the quarantine CSV; the malformed row remains traceable and is not silently accepted. Enter reviewer/reason and **Accept valid rows**. Download original bytes or the full evidence packet.
3. Select **Synthetic clinic CSV → Load synthetic sample**. It has canonical headers and maps automatically. Accept it and explain that its scoped native keys attach later evidence to the same two site cases. The XLSX and CSV artifacts remain separate originals.
4. Open Work queue and search `synthetic-demo`. There is one provider at **NORTH** and **SOUTH**, not one provider-wide phone. For NORTH select `triage`, then `approve` proposal `6175550199`, then `submit` reference `SIMULATED-TICKET-NORTH`, then `verify` observed `6175550199` with an explicitly synthetic observation note. Supply actor/reason for each action. Show `verified` and history.
5. For SOUTH use proposal `6175550198`, submit a simulated ticket, then observe `6175550170`. The case becomes **reopened**, retaining the proposal and failed observation. Assign an owner and follow-up if desired; explain locally asserted attribution.
6. Load **Synthetic clinic workbook** again. Its committed parsing settings are reused, and it is visibly a repeat receipt. Accept it without duplicating work/history. Load **Synthetic changed delivery**: preview new/changed/unchanged/missing-from-this-delivery counts. Accept and inspect later evidence; the original snapshot/status/ownership remain intact. Absence is not termination.
7. For an optional separate reference example, choose **Synthetic NPPES response** and **Synthetic CMS clinician response** from the picker. Ordinary saved-response upload can instead use a separate namespace such as `offline-reference` and the corresponding explicit profile. These are **synthetic saved-response fixtures**, not live success. Inspect native addresses/taxonomies versus enrollment/group/address grain. Accept valid observations. An explicit location relationship requires selecting the particular native practice location, with reviewer and evidence reason; mailing evidence is rejected.
8. Open Sources to explain bounded retrieval metadata and reference limits. An optional live lookup requires network and remains separate from the offline core. Save an asserted source link to show that a URL alone is not fetched or verified.
9. In a selected work case, choose **Download case XLSX**. Inspect Cases (listed/requested/approved/observed values and ownership), Evidence (source/receipt/row locators), and Decisions (every action and assertion). **Download all work XLSX** includes every durable case, regardless of queue filters; shared receipt attempts may contain other source rows. Payloads preserve complete originals and long history details. These exports read one consistent snapshot and change no workflow state. The receipt evidence packet JSON remains available.
10. Ctrl-C the launcher, then restart using the same printed root. Show the same receipt, owner/follow-up, case version and events. Inputs, originals and work are retained; sample reload remains a repeat rather than duplicate work.

## Recovery and rollback

Before creating or opening demo storage, the launcher checks whether ports 8000 and 5173 are available. An occupied port returns a nonzero exit with an actionable message; it never reuses that service. If the API or UI exits unexpectedly (including exit 0), the launcher stops its own service groups and returns failure while retaining storage. Ordinary Ctrl-C is a successful stop. `--prepare-only` needs no free service ports and starts no services.

A failed parse stays visible: correct header, encoding, delimiter or mapping and save a new attempt. Rejecting a failed/needs-mapping submission records an explicit decision. A stale case version returns a conflict; refresh the evidence and retry with the retained draft. No action automatically closes work from later source observations.

If interrupted while processing, restart and reprocess the receipt. Atomic acceptance leaves either the entire accepted batch or none. Startup reports staged/orphan/missing artifacts without deleting them. Keep the database and matching artifact root together. Before manual restoration, stop services and restore a SQLite backup plus its corresponding artifact root into a **new** directory; inspect integrity/FK checks before selecting it. Do not overwrite originals to rehearse restoration.

Legacy QA and Corrections views remain available for the original deterministic payer-precedence demonstration. They use current generated QA evidence and original remediation snapshots rather than the new intake identity/version contract. See the [API compatibility reference](../API_REFERENCE.md).
