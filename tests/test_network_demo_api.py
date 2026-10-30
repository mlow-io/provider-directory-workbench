"""The guided network setup is explicit, demo-only and never accepts/overwrites work."""
import sqlite3
from fastapi.testclient import TestClient
from provider_directory_truth_layer.intake_api import create_workbench
from provider_directory_truth_layer.intake_store import IntakeStore
from provider_directory_truth_layer.demo_network import SOURCE


def test_setup_is_demo_only_explicit_idempotent_and_preserves_reviewed_binding(tmp_path):
    path=tmp_path/'directory.sqlite3';root=tmp_path/'runtime'
    normal=TestClient(create_workbench(path,root,demo=False))
    assert normal.post('/api/demo/network-setup').status_code==404
    demo=TestClient(create_workbench(path,root,demo=True))
    first=demo.post('/api/demo/samples/network-baseline').json()
    assert 'suggested_network_settings' not in first['metadata']
    assert first['state']=='needs_mapping'
    assert 'network roster scope' in first['preview']['error']
    assert demo.get('/api/work').json()['items']==[]
    setup=demo.post('/api/demo/network-setup').json()
    assert setup['source']==SOURCE
    assert demo.post('/api/demo/network-setup').json()==setup
    assert demo.get('/api/work').json()['items']==[]
    baseline=demo.post('/api/demo/samples/network-baseline').json()
    spec={'mapping':baseline['preview']['mapping'],**baseline['metadata']['suggested_network_settings']}
    baseline=demo.post(f"/api/intakes/{baseline['id']}/mapping",json=spec).json()
    assert baseline['preview']['valid_count']==3
    revision=demo.post(f"/api/intakes/{baseline['id']}/saved-mappings",json={'name':'Network v1','actor':'Synthetic Reviewer','reason':'Reviewed explicit scope','expected_attempt':baseline['attempt_id']}).json()
    def accept(receipt):
        response=demo.post(f"/api/intakes/{receipt['id']}/commit",json={'actor':'Synthetic Reviewer','reason':'Reviewed source assertions','policy':'valid_rows','expected_attempt':receipt['attempt_id']})
        assert response.status_code==200,response.text
        return response.json()
    baseline=accept(baseline)
    changed=demo.post('/api/demo/samples/network-changed').json()
    changed=demo.post(f"/api/intakes/{changed['id']}/mapping",json={'mapping_revision_id':revision['id']}).json()
    assert changed['preview']['valid_count']==2 and changed['preview']['quarantined_count']==3
    comparison=changed['preview']['comparison']
    assert {key:comparison[key] for key in ['new','changed','blocked_invalid','unresolved','missing_from_this_delivery']}=={'new':1,'changed':1,'blocked_invalid':2,'unresolved':1,'missing_from_this_delivery':1}
    changed=accept(changed)
    assert len(demo.get('/api/work').json()['items'])==6
    assert len(changed['observations'])==2
    assert all(c['status']=='new' for c in changed['linked_cases'])
    store=IntakeStore(path,root)
    cedar=next(item for item in setup['catalog']['networks'] if 'CEDAR' in item['label'])
    original_id=setup['settings']['bindings']['network']['CEDAR']
    store.bind_source({'source':SOURCE,'kind':'network','source_key':'CEDAR','target_id':cedar['id'],'expected_binding_id':original_id,'actor':'Synthetic Reviewer','reason':'Reviewed again'})
    before=store.catalog()
    assert demo.post('/api/demo/network-setup').status_code==409
    assert store.catalog()==before
    with sqlite3.connect(path) as conn:assert conn.execute('pragma foreign_key_check').fetchall()==[]
