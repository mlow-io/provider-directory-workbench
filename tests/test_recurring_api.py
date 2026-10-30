"""Recurring intake HTTP bounds and accountable mapping/acceptance decisions."""
import io
import csv

from fastapi.testclient import TestClient

from provider_directory_truth_layer.intake_api import create_workbench


def csv_payload(count=1, phone='5550100000'):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=['record_id','npi','provider_name','address','city','state','zip','phone','location_id'])
    writer.writeheader()
    for index in range(count):
        writer.writerow(dict(record_id=f'{index:03}', npi='1000000001', provider_name='Synthetic Provider',
                             address='1 Example St', city='Example', state='MA', zip='02108', phone=phone, location_id='NORTH'))
    return out.getvalue().encode()


def test_http_mapping_review_expected_attempt_full_packet_and_stale_baseline(tmp_path):
    client = TestClient(create_workbench(tmp_path/'directory.sqlite3', tmp_path/'runtime', demo=False))
    def upload(data):
        response = client.post('/api/intakes/files?filename=synthetic.csv&source=recurring-api', content=data)
        assert response.status_code == 200
        return response.json()
    def accept(receipt):
        return client.post(f"/api/intakes/{receipt['id']}/commit", json={'actor':'Synthetic Reviewer', 'reason':'Reviewed',
             'expected_attempt':receipt['attempt_id'], 'policy':'valid_rows'})
    first = upload(csv_payload(60))
    assert len(first['preview']['comparison']['entries']) == 50
    assert first['preview']['comparison']['entry_count'] == 60
    save_url = f"/api/intakes/{first['id']}/saved-mappings"
    assert client.post(save_url,json={'name':'Monthly','actor':'Reviewer','reason':'Reviewed'}).status_code == 409
    revision = client.post(save_url,json={'name':'Monthly','actor':'Reviewer','reason':'Reviewed','expected_attempt':first['attempt_id']}).json()
    assert revision['required_headers']
    assert client.get('/api/work').json()['items'] == []
    assert accept(first).status_code == 200
    incoming = upload(csv_payload(60, '5550100001'))
    mapped = client.post(f"/api/intakes/{incoming['id']}/mapping", json={'mapping_revision_id':revision['id']}).json()
    assert mapped['preview']['comparison']['baseline']['attempt_id'] == first['attempt_id']
    intervening = upload(csv_payload(60, '5550100002'))
    assert accept(intervening).status_code == 200
    stale = accept(mapped)
    assert stale.status_code == 409
    assert 'baseline changed' in stale.json()['detail']
    refreshed = client.post(f"/api/intakes/{incoming['id']}/mapping",json={'mapping_revision_id':revision['id']}).json()
    assert accept(refreshed).status_code == 200
    packet = client.get(f"/api/intakes/{incoming['id']}/packet").json()
    assert len(packet['preview']['comparison']['entries']) == 60
    assert packet['attempts'][-1]['spec']['mapping_revision_id'] == revision['id']
    assert len(packet['observations']) == 60
    assert all(case['status']=='new' for case in packet['linked_cases'])
    assert len(client.get(save_url).json()['items']) == 1
