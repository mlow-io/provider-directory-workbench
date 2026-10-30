"""One HTTP application for intake and existing review routes."""
from __future__ import annotations

import csv
import io
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from .intake_store import IntakeStore, Conflict, MAX_BYTES
from .storage import database_path, storage_root
from .review_api import create_app
from .remediation_api import create_remediation_app


def create_workbench(path: Path | None = None, root: Path | None = None, *, demo: bool | None = None) -> FastAPI:
    path = path or database_path()
    store = IntakeStore(path, root or storage_root())
    app = create_app(path)
    demo_enabled = os.environ.get('PDTL_DEMO') == '1' if demo is None else demo
    # Keep existing route compatibility in the same process and database.
    for route in create_remediation_app(path).routes:
        if getattr(route, 'path', '').startswith('/api/remediation'):
            app.router.routes.append(route)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=409 if isinstance(exc, Conflict) else 422)

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=404)

    @app.get('/api/intakes')
    def inbox():
        return store.inbox()

    @app.post('/api/intakes/files')
    async def upload(request: Request, filename: str, source: str = 'clinic', designation: str = 'synthetic', profile: str = 'flat'):
        payload = bytearray()
        async for chunk in request.stream():
            payload.extend(chunk)
            if len(payload) > MAX_BYTES:
                raise ValueError('Artifact limit is 10 MiB')
        # Bounded parsing runs off the event loop, so receipt/status reads remain responsive.
        return bounded(await run_in_threadpool(store.receive, bytes(payload), filename, source, designation, profile))

    def bounded(result):
        # Full evidence is downloadable; interactive responses have bounded samples.
        if result.get('preview'):
            result['preview']['rows'] = result['preview']['rows'][:50]
        for attempt in result.get('attempts', []):
            attempt['preview']['rows'] = attempt['preview'].get('rows', [])[:50]
        for field in ['observations', 'linked_cases']:
            result[field + '_count'] = len(result.get(field, []))
            result[field] = result.get(field, [])[:50]
        return result

    @app.get('/api/demo/samples')
    def samples():
        from .demo_samples import SAMPLES
        return {'items': SAMPLES if demo_enabled else []}

    @app.post('/api/demo/samples/{sample_id}')
    def load_sample(sample_id: str):
        from .demo_samples import SAMPLES, WORKBOOK_MAPPING, sample_payloads
        if not demo_enabled:
            raise HTTPException(404, 'Synthetic sample loading is disabled; use the offline demo launcher')
        sample = next((s for s in SAMPLES if s['id'] == sample_id), None)
        if sample is None:
            raise KeyError('Unknown synthetic sample')
        metadata = {'demo_sample': sample_id, 'notice': 'SYNTHETIC offline example; no real clinicians or payer updates'}
        if sample_id == 'clinic-workbook':
            metadata['suggested_mapping'] = WORKBOOK_MAPPING
        result = store.receive(sample_payloads()[sample_id], sample['filename'], 'synthetic-demo', 'synthetic', sample['profile'], metadata)
        if sample_id == 'clinic-workbook' and result['state'] == 'failed':
            result = store.mapping(result['id'], {'header_row': 2, 'sheet': 'Clinic roster'})
        return bounded(result)

    @app.get('/api/intakes/{receipt_id}')
    def detail(receipt_id: str):
        return bounded(store.detail(receipt_id))

    @app.post('/api/intakes/{receipt_id}/mapping')
    def mapping(receipt_id: str, payload: dict):
        return bounded(store.mapping(receipt_id, payload))

    @app.post('/api/intakes/{receipt_id}/commit')
    def commit(receipt_id: str, payload: dict):
        if not payload.get('expected_attempt'):
            raise ValueError('expected_attempt is required; accept the interpretation you previewed')
        return bounded(store.commit(receipt_id, payload))

    @app.get('/api/intakes/{receipt_id}/artifact')
    def artifact(receipt_id: str):
        receipt = store.detail(receipt_id)
        if not receipt['artifact_sha']:
            raise ValueError('Reference-only receipt has no fetched artifact')
        return FileResponse(store.artifacts / receipt['artifact_sha'], filename=receipt['label'])

    @app.get('/api/intakes/{receipt_id}/quarantine')
    def quarantine(receipt_id: str):
        receipt = store.detail(receipt_id)
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(['locator','problems','original'])
        for row in (receipt['preview'] or {}).get('rows', []):
            if row['problems']:
                from .intake_store import packed
                writer.writerow([row['locator'], '; '.join(row['problems']), packed(row['original'])])
        return Response(stream.getvalue(), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename=quarantine.csv'})

    @app.get('/api/intakes/{receipt_id}/packet')
    def packet(receipt_id: str):
        receipt = store.detail(receipt_id)
        receipt['cases'] = [store.case(c['id']) for c in receipt['linked_cases']]
        return JSONResponse(receipt, headers={'Content-Disposition': 'attachment; filename=evidence-packet.json'})

    @app.post('/api/intakes/lookups')
    def lookup(payload: dict):
        from .intake_adapters import fetch_public, PublicFetchError
        source = payload.get('source')
        query = payload.get('query', {})
        if not payload.get('refresh', False):
            from datetime import datetime, timezone, timedelta
            with store.db() as conn:
                candidates = [dict(r) for r in conn.execute('select * from receipt where source=? and artifact_sha is not null order by received_at desc', (source,))]
            import json
            for candidate in candidates:
                metadata = json.loads(candidate['metadata'])
                if metadata.get('lookup_query') == query and not metadata.get('error') and datetime.fromisoformat(candidate['received_at']) > datetime.now(timezone.utc) - timedelta(minutes=15):
                    return store.receive((store.artifacts / candidate['artifact_sha']).read_bytes(), candidate['label'], source, 'public', candidate['profile'], {**metadata, 'cache_status':'retained_response', 'replayed_from':candidate['id']})
        try:
            fetched = fetch_public(source, payload.get('query', {}))
        except PublicFetchError as exc:
            if exc.payload:
                receipt = store.receive(exc.payload, exc.label + '.json', source, 'public', exc.profile, exc.metadata)
                with store.db() as conn:
                    conn.execute("update attempt set state='failed' where receipt_id=?", (receipt['id'],))
            else:
                receipt = store.link({'url': exc.metadata.get('request_url', 'https://data.cms.gov/'), 'title': exc.label, 'source': source, **exc.metadata})
            return JSONResponse({**store.detail(receipt['id']), 'state': 'failed', 'detail': str(exc)}, status_code=422)
        except ValueError as exc:
            receipt = store.link({'url': 'https://npiregistry.cms.hhs.gov/' if source == 'nppes' else 'https://data.cms.gov/', 'title': 'Failed ' + str(source) + ' lookup', 'source': str(source), 'observed_at': '', 'error': str(exc), 'query': payload.get('query', {})})
            return JSONResponse({**receipt, 'state': 'failed', 'detail': str(exc)}, status_code=422)
        return bounded(store.receive(fetched['payload'], fetched['label'] + '.json', source, 'public', fetched['profile'], {**fetched['metadata'], 'lookup_query':query}))

    @app.post('/api/intakes/links')
    def link(payload: dict):
        return store.link(payload)

    @app.get('/api/sources')
    def sources():
        items = []
        with store.db() as conn:
            for source in ['nppes','cms']:
                rows = [dict(r) for r in conn.execute('select * from receipt where source=? order by received_at desc', (source,))]
                import json
                success = next((r for r in rows if r['artifact_sha'] and not json.loads(r['metadata']).get('error')), None)
                failure = next((r for r in rows if json.loads(r['metadata']).get('error')), None)
                items.append({'source': source, 'adapter_version': '1', 'scope': 'Bounded public reference; not certified truth or complete directory', 'last_success': success['received_at'] if success else None, 'last_failure': json.loads(failure['metadata']) if failure else None, 'metadata': json.loads(success['metadata']) if success else {}})
        return {'items': items}

    @app.get('/api/work')
    def work():
        return store.work()

    @app.get('/api/work-export.xlsx')
    def work_export(case_id: str | None = None):
        from .work_export import handoff_workbook
        return Response(handoff_workbook(store.path, case_id),
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': 'attachment; filename=durable-work-handoff.xlsx'})

    @app.get('/api/work/{case_id}')
    def case(case_id: str):
        return store.case(case_id)

    @app.post('/api/work/{case_id}/events')
    def event(case_id: str, payload: dict):
        return store.event(case_id, payload)

    @app.post('/api/relationships')
    def relationship(payload: dict):
        return store.relationship(payload)

    return app


def run():
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(create_workbench(), host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    run()
