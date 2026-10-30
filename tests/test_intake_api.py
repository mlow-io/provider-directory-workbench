from pathlib import Path
from fastapi.testclient import TestClient
from provider_directory_truth_layer.intake_api import create_workbench

CSV = b'record_id,npi,provider_name,address,city,state,zip,phone,location_id,reference_phone\nA,1234567890,Synthetic Example,1 Main St,Boston,MA,02108,6175550100,L1,6175550199\nB,,Malformed,2 Main St,Boston,MA,02108,123,L2,6175550199\n'


def test_http_import_workflow_original_quarantine_repeat_and_conflict(tmp_path: Path):
    client = TestClient(create_workbench(tmp_path/'test.db', tmp_path))
    result = client.post('/api/intakes/files?filename=synthetic.csv', content=CSV)
    assert result.status_code == 200, result.text
    receipt = result.json()
    assert receipt['preview']['valid_count'] == 1
    assert receipt['preview']['quarantined_count'] == 1
    rid = receipt['id']
    assert client.get(f'/api/intakes/{rid}/artifact').content == CSV
    assert 'Missing npi' in client.get(f'/api/intakes/{rid}/quarantine').text
    assert client.post(f'/api/intakes/{rid}/commit', json={'policy':'valid_rows','actor':'Tester','reason':'Explicit acceptance','expected_attempt':receipt['attempt_id']}).status_code == 200
    case = client.get('/api/work').json()['items'][0]
    payload = {'action':'triage','actor':'Tester','reason':'Inspect source','expected_version':0}
    assert client.post(f"/api/work/{case['id']}/events",json=payload).status_code == 200
    assert client.post(f"/api/work/{case['id']}/events",json=payload).status_code == 409
    repeat = client.post('/api/intakes/files?filename=synthetic.csv',content=CSV).json()
    assert repeat['duplicate_of'] == rid
    committed = client.post(f"/api/intakes/{repeat['id']}/commit",json={'policy':'valid_rows','actor':'Tester','reason':'Repeat','expected_attempt':repeat['attempt_id']}).json()
    assert committed['state'] == 'duplicate_delivery'
    assert len(client.get('/api/work').json()['items']) == 1
    packet = client.get(f'/api/intakes/{rid}/packet').json()
    assert packet['cases'][0]['history'][0]['actor'] == 'Tester'
    assert packet['observations'][0]['normalized']['zip'] == '02108'
    assert client.get('/api/intakes/missing').status_code == 404


def test_failed_receipt_can_be_retried_and_links_are_assertions(tmp_path):
    client = TestClient(create_workbench(tmp_path/'test.db',tmp_path))
    receipt = client.post('/api/intakes/files?filename=bad.json',content=b'{').json()
    assert receipt['state'] == 'failed'
    assert client.get(f"/api/intakes/{receipt['id']}/artifact").content == b'{'
    assert client.post(f"/api/intakes/{receipt['id']}/mapping",json={}).json()['state'] == 'failed'
    link = client.post('/api/intakes/links',json={'url':'https://example.org','source':'clinic','title':'Asserted evidence'}).json()
    assert link['state'] == 'reference_only'
    assert 'not fetched' in link['metadata']['assertion']
    assert client.get(f"/api/intakes/{link['id']}/artifact").status_code == 422


def test_failed_public_envelope_retained_and_stale_preview_rejected(tmp_path, monkeypatch):
    from provider_directory_truth_layer import intake_adapters
    def fail(*args):
        raise intake_adapters.PublicFetchError('Source API failed',payload=b'{"Errors":[{"description":"upstream unavailable"}]}',metadata={'http_status':503,'error':'Source API failed'},source='nppes',profile='nppes',label='Failed response')
    monkeypatch.setattr(intake_adapters,'fetch_public',fail)
    client=TestClient(create_workbench(tmp_path/'test.db',tmp_path))
    response=client.post('/api/intakes/lookups',json={'source':'nppes','query':{'limit':1}})
    assert response.status_code == 422
    receipt=response.json()
    assert receipt['state']=='failed'
    assert client.get(f"/api/intakes/{receipt['id']}/artifact").content.startswith(b'{"Errors"')
    assert client.get('/api/sources').json()['items'][0]['last_failure']['http_status']==503
    original=client.post('/api/intakes/files?filename=synthetic.csv',content=CSV).json()
    client.post(f"/api/intakes/{original['id']}/mapping",json={'delimiter':','})
    response=client.post(f"/api/intakes/{original['id']}/commit",json={'actor':'Tester','reason':'stale','policy':'valid_rows','expected_attempt':original['attempt_id']})
    assert response.status_code==409


def test_public_lookup_replays_retained_bytes_without_second_network_read(tmp_path, monkeypatch):
    from provider_directory_truth_layer import intake_adapters
    import json
    calls=[]
    def fetch(*args):
        calls.append(args)
        return {'payload':json.dumps({'result_count':0,'results':[]}).encode(),'label':'NPPES zero matches','profile':'nppes','metadata':{'scope':{'city':'Synthetic'},'cache_status':'fresh_network'}}
    monkeypatch.setattr(intake_adapters,'fetch_public',fetch)
    client=TestClient(create_workbench(tmp_path/'test.db',tmp_path))
    first=client.post('/api/intakes/lookups',json={'source':'nppes','query':{'city':'Synthetic'}}).json()
    repeat=client.post('/api/intakes/lookups',json={'source':'nppes','query':{'city':'Synthetic'}}).json()
    assert len(calls)==1
    assert first['artifact_sha']==repeat['artifact_sha']
    assert repeat['metadata']['cache_status']=='retained_response'
    assert repeat['duplicate_of']==first['id']
