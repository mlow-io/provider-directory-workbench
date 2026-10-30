# Public reference source contracts

Updated 2026-10-23. Implemented in `intake_adapters.py` and exposed through the Intake public lookup and saved-response profile controls. Public observations are not certified provider truth. Offline fixtures are unmistakably synthetic.

## NPPES Registry v2.1

[Official API help](https://npiregistry.cms.hhs.gov/registry/help-api). Supports exact NPI and bounded city/state searches, default 25, maximum 200, with explicit skip. One request produces one bounded intake; there is no automatic national harvest. Preserve `number`, entity type, full `basic`, addresses, additional practice locations, taxonomies and other original fields. Unknown status stays unknown. All locations remain together at native entity grain; no mailing address is silently treated as a confirmed practice.

`basic.last_updated` is `source_updated_at`, never human verification. The legacy CSV sample helper is still available, selects one address/taxonomy for its projection, uses native NPI IDs, and now leaves human verification blank.

## CMS Doctors and Clinicians

[Dataset mj5m-pzi6](https://data.cms.gov/provider-data/dataset/mj5m-pzi6), [dictionary](https://data.cms.gov/provider-data/sites/default/files/data_dictionaries/physician/DOC_Data_Dictionary.pdf), [API information](https://data.cms.gov/provider-data/about). Fetch dataset metadata before a small datastore distribution-0 page; retain the metadata with the original response receipt. API supports a bounded limit/offset. It does not expose arbitrary query expressions or promise filtered national coverage.

Native grain is clinician/enrollment/group/address. Retain all rows, including incomplete composite keys as unresolved; never deduplicate on NPI. Published labels and observed lowercase/underscore machine columns have contract tests. CMS coverage concerns Medicare, not all clinicians or commercial payer networks. Dataset publication/modification dates do not establish per-provider verification.

## Retrieval behavior

Only connector-owned HTTPS hosts are fetched. Redirects outside the source host are rejected. Responses cap at 10 MiB and pages at 200 rows. Transient HTTP/network failures have at most three attempts, with bounded `Retry-After` handling. Error envelopes, malformed success responses and connection failures remain visible failures, not healthy empty directories. Response bytes are retained when available; a capped failure prefix is labeled truncated. Connection failures have no invented response artifact.

A fifteen-minute retained-response cache creates a new receipt with `cache_status=retained_response`; `refresh=true` requests a fresh read. Saved `flat`, `nppes`, and `cms` JSON profiles use the same ingestion service and produce normal previews/quarantine/acceptance. Unsupported envelopes are rejected visibly. Zero results are a successful bounded retrieval with zero accepted rows.

## Verified live scope

Integrated lookups on 2026-10-23 at 21:27 UTC returned HTTP 200 for NPPES Nashville/TN limit 1 and CMS unfiltered limit 1. Raw responses, request metadata and SHA-256 artifacts are retained locally in `.runtime/live-smoke-20261023/`; public bytes are not committed as synthetic fixtures. Both responses were marked `truncated=true`. CMS metadata reported modified 2026-10-02 and released 2026-10-15. These establish only the specific bounded reads. See the [durable evidence index](evidence/intake_2_0/README.md).

## Evidence links and exclusions

Evidence URLs are asserted references, not fetched or verified. Arbitrary HTML/PDF scraping, private URLs, bulk replication, credentials/licensure checks, payer writes, and CMS FHIR are not implemented. NPI issuance/status does not establish licensure, payer participation, or operating-site status.
