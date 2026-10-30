"""Reviewable network absence/validation evidence, separate from accepted membership."""
from __future__ import annotations
import json
from .intake_store import digest, uid, packed, now
from .recurring import identity


def record_comparison_work(store, conn, receipt, attempt, preview, spec):
    if spec.get('roster_kind') != 'network':return
    rows_by_locator={row['locator']:row for row in preview.get('rows',[])}
    old={}
    if spec.get('baseline_attempt_id'):
        for record in conn.execute('SELECT * FROM observation WHERE attempt_id=?',(spec['baseline_attempt_id'],)):
            item=store.observation(dict(record));key=identity(item)
            if key:old[key]=item
    for entry in preview.get('comparison',{}).get('entries',[]):
        status=entry['status']
        if status not in {'missing','blocked_invalid'}:continue
        norm=entry.get('new') or entry.get('old') or {}
        part=norm.get('participation',{})
        if not all(part.get(key) for key in ['provider_id','location_id','network_id']):continue
        native=json.loads(entry['key'])[0]
        field='participation_missing' if status=='missing' else 'participation_validation'
        stable=[receipt['source'],json.loads(receipt['metadata']).get('scope'),part['network_id'],part['provider_id'],part['location_id'],native]
        key=digest([stable,'qa',field])
        prior=conn.execute('SELECT id FROM work_case WHERE identity_key=?',(key,)).fetchone()
        case_id=prior['id'] if prior else uid()
        source_row=rows_by_locator.get(entry.get('current_locator'))
        baseline_row=old.get(entry['key'])
        payload={'comparison':entry,'source_row':source_row,'baseline_observation':baseline_row,
                 'meaning':'Source comparison evidence only; not accepted membership, termination, or human verification'}
        if not prior:
            evidence={'original':source_row['original'] if source_row else baseline_row['original'] if baseline_row else {},
                      'normalized':norm,'locator':entry.get('current_locator') or 'Absent from this delivery; see baseline locator',
                      'receipt_id':receipt['id'],'observation_id':None,'source':receipt['source'],'designation':receipt['designation'],
                      'provider_id':part['provider_id'],'location_id':part['location_id'],'listing_value':part.get('listed_status'),
                      'reference_value':None,'baseline_receipt_id':entry.get('previous_receipt_id'),
                      'baseline_observation_id':baseline_row['id'] if baseline_row else None,
                      'comparison_status':status,'mapping_revision_id':spec.get('mapping_revision_id'),'binding_ids':part.get('binding_ids',[])}
            issue='Participation missing from this delivery' if status=='missing' else 'Quarantined participation requires review'
            conn.execute('INSERT INTO work_case VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (case_id,'qa',key,str(norm.get('provider_name','')),part['location_id'],field,issue,'medium',
                 'Source comparison is review evidence; no automatic membership change','new',None,None,0,packed(evidence),None,None,now(),now()))
            conn.execute('INSERT INTO case_scope VALUES (?,?,?,?,?)',(case_id,part['network_id'],part.get('organization_id'),part['location_id'],native))
        conn.execute('INSERT OR IGNORE INTO participation_review_evidence(case_id,attempt_id,status,identity_key,locator,payload) VALUES (?,?,?,?,?,?)',
                     (case_id,attempt['id'],status,key,entry.get('current_locator') or '',packed(payload)))


def case_scope(conn, case_id):
    row=conn.execute('''SELECT s.*, n.label network_label, o.label organization_label, l.label location_label
       FROM case_scope s JOIN network n ON n.id=s.network_id
       LEFT JOIN organization o ON o.id=s.organization_id
       JOIN practice_location l ON l.id=s.practice_location_id WHERE s.case_id=?''',(case_id,)).fetchone()
    return dict(row) if row else None


def review_evidence(conn, case_id):
    items=[dict(row) for row in conn.execute('''SELECT e.*, a.receipt_id,a.spec,r.label receipt_label,r.metadata receipt_metadata
        FROM participation_review_evidence e JOIN attempt a ON a.id=e.attempt_id
        JOIN receipt r ON r.id=a.receipt_id WHERE e.case_id=? ORDER BY e.id''',(case_id,))]
    for item in items:
        for field in ['payload','spec','receipt_metadata']:item[field]=json.loads(item[field])
    return items


def export_scope(conn, cases, result):
    """All reads use the exporter's pinned snapshot; only selected operational scope is projected."""
    result.update(participations=[],review_evidence=[],catalog={'organizations':[],'networks':[],'locations':[]},bindings=[])
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='case_scope'").fetchone() is None:return
    networks,organizations,locations,binding_ids=set(),set(),set(),set()
    if result.get('network_id'):networks.add(result['network_id'])
    for case in cases:
        scope=case_scope(conn,case['id']);case['scope']=scope
        if not scope:continue
        networks.add(scope['network_id']);locations.add(scope['practice_location_id'])
        if scope['organization_id']:organizations.add(scope['organization_id'])
        for record in conn.execute('''SELECT p.*,a.receipt_id,r.source,r.designation,r.received_at,r.metadata receipt_metadata FROM participation_observation p
            JOIN work_evidence w ON w.observation_id=p.observation_id
            JOIN observation o ON o.id=p.observation_id JOIN attempt a ON a.id=o.attempt_id JOIN receipt r ON r.id=a.receipt_id
            WHERE w.case_id=? AND p.network_id=? AND p.practice_location_id=? ORDER BY p.observation_id''',
            (case['id'],scope['network_id'],scope['practice_location_id'])):
            item=dict(record);item['case_id']=case['id']
            item['binding_snapshot']=json.loads(item['binding_snapshot']);item['raw_labels']=json.loads(item['raw_labels']);item['receipt_metadata']=json.loads(item['receipt_metadata'])
            if item['organization_id']:organizations.add(item['organization_id'])
            binding_ids.update(item['binding_snapshot']);result['participations'].append(item)
        result['review_evidence'].extend(review_evidence(conn,case['id']))
        binding_ids.update(case['evidence'].get('binding_ids',[]))
    for network_id in sorted(networks):
        item=dict(conn.execute('SELECT * FROM network WHERE id=?',(network_id,)).fetchone())
        item['identifiers']=json.loads(item['identifiers'])
        if item['payer_organization_id']:organizations.add(item['payer_organization_id'])
        result['catalog']['networks'].append(item)
    for location_id in sorted(locations):
        item=dict(conn.execute('SELECT * FROM practice_location WHERE id=?',(location_id,)).fetchone())
        if item['organization_id']:organizations.add(item['organization_id'])
        result['catalog']['locations'].append(item)
    for organization_id in sorted(organizations):
        item=dict(conn.execute('SELECT * FROM organization WHERE id=?',(organization_id,)).fetchone())
        item['identifiers']=json.loads(item['identifiers'])
        result['catalog']['organizations'].append(item)
    from .network_store import binding_record
    for binding_id in sorted(binding_ids):
        row=conn.execute('SELECT * FROM identity_binding WHERE id=?',(binding_id,)).fetchone()
        if row:
            binding=binding_record(row)
            # Only bindings belonging to selected scope; source configs remain separately labeled context.
            if (binding['kind']=='network' and binding['target_id'] in networks or
                binding['kind']=='location' and binding['target_id'] in locations or
                binding['kind']=='organization' and binding['target_id'] in organizations):
                result['bindings'].append(binding)
