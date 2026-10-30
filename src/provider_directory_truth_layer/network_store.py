"""Explicit organization/network identities and source-asserted participation.

Catalog labels never establish identity. All bindings are reviewed immutable revisions.
"""
from __future__ import annotations

import json
from datetime import date
from .intake_store import Conflict, digest, now, packed, uid

MIGRATION_4 = '''
CREATE TABLE organization (
 id TEXT PRIMARY KEY, label TEXT NOT NULL, kind TEXT NOT NULL, identifiers TEXT NOT NULL,
 actor TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE network (
 id TEXT PRIMARY KEY, label TEXT NOT NULL, payer_organization_id TEXT REFERENCES organization(id),
 identifiers TEXT NOT NULL, actor TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE practice_location (
 id TEXT PRIMARY KEY, label TEXT NOT NULL, organization_id TEXT REFERENCES organization(id),
 actor TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE identity_binding (
 id TEXT PRIMARY KEY, source TEXT NOT NULL, kind TEXT NOT NULL, source_key TEXT NOT NULL,
 organization_id TEXT REFERENCES organization(id), network_id TEXT REFERENCES network(id),
 practice_location_id TEXT REFERENCES practice_location(id), previous_id TEXT REFERENCES identity_binding(id),
 revision INTEGER NOT NULL, actor TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(source,kind,source_key,revision),
 CHECK ((kind='organization' AND organization_id IS NOT NULL AND network_id IS NULL AND practice_location_id IS NULL)
 OR (kind='network' AND network_id IS NOT NULL AND organization_id IS NULL AND practice_location_id IS NULL)
 OR (kind='location' AND practice_location_id IS NOT NULL AND organization_id IS NULL AND network_id IS NULL)));
CREATE TABLE participation_observation (
 observation_id TEXT PRIMARY KEY REFERENCES observation(id), native_key TEXT NOT NULL,
 provider_id TEXT NOT NULL, practice_location_id TEXT NOT NULL REFERENCES practice_location(id),
 network_id TEXT NOT NULL REFERENCES network(id), organization_id TEXT REFERENCES organization(id),
 mapping_revision_id TEXT REFERENCES mapping_revision(id), listed_status TEXT,
 effective_date TEXT, end_date TEXT, binding_snapshot TEXT NOT NULL, raw_labels TEXT NOT NULL);
CREATE INDEX participation_scope ON participation_observation(network_id,practice_location_id,provider_id,native_key);
CREATE TABLE case_scope (
 case_id TEXT PRIMARY KEY REFERENCES work_case(id), network_id TEXT NOT NULL REFERENCES network(id),
 organization_id TEXT REFERENCES organization(id), practice_location_id TEXT NOT NULL REFERENCES practice_location(id),
 native_key TEXT NOT NULL);
CREATE TABLE participation_review_evidence (
 id INTEGER PRIMARY KEY, case_id TEXT NOT NULL REFERENCES work_case(id),
 attempt_id TEXT NOT NULL REFERENCES attempt(id), status TEXT NOT NULL, identity_key TEXT,
 locator TEXT, payload TEXT NOT NULL, UNIQUE(case_id,attempt_id,status,identity_key,locator));
'''
for _table in ['organization','network','practice_location','identity_binding','participation_observation','case_scope','participation_review_evidence']:
    for _action in ['UPDATE','DELETE']:
        MIGRATION_4 += f"CREATE TRIGGER {_table}_no_{_action.lower()} BEFORE {_action} ON {_table} BEGIN SELECT RAISE(ABORT,'Immutable {_table}'); END;\n"

TABLES = {'organizations': 'organization', 'networks': 'network', 'locations': 'practice_location'}
TARGETS = {'organization': ('organization','organization_id'), 'network': ('network','network_id'), 'location': ('practice_location','practice_location_id')}
NETWORK_FIELDS = ['network_code','organization_code','network_label','organization_label','participation_status','effective_date','end_date']


def binding_record(row, current=None):
    item = dict(row)
    item['target_id'] = item.get('network_id') or item.get('organization_id') or item.get('practice_location_id')
    if current is not None:
        item['current'] = current
    return item


def catalog(conn):
    result = {name: [dict(row) for row in conn.execute(f'SELECT * FROM {table} ORDER BY label,id')] for name,table in TABLES.items()}
    for key in ('organizations','networks'):
        for row in result[key]:row['identifiers'] = json.loads(row['identifiers'])
    result['bindings'] = [binding_record(row, bool(row['is_current'])) for row in conn.execute('''SELECT b.*,
      NOT EXISTS(SELECT 1 FROM identity_binding newer WHERE newer.source=b.source AND newer.kind=b.kind
       AND newer.source_key=b.source_key AND newer.revision>b.revision) AS is_current
      FROM identity_binding b ORDER BY b.source,b.kind,b.source_key,b.revision''')]
    return result


def create_catalog(store, kind, payload):
    if kind not in TABLES:raise ValueError('Choose organizations, networks or locations')
    label, actor, reason = (store.required(payload, key) for key in ('label','actor','reason'))
    identifiers = payload.get('identifiers', [])
    if not isinstance(identifiers,list) or any(not isinstance(item,dict) or not str(item.get('namespace','')).strip() or not isinstance(item.get('value'),str) or not item['value'].strip() for item in identifiers):
        raise ValueError('Identifiers require an issuing namespace and a nonblank text value')
    item = {'id':uid(), 'label':label, 'actor':actor, 'reason':reason, 'created_at':now()}
    with store.db() as conn:
        conn.execute('begin immediate')
        if kind == 'organizations':
            org_kind = payload.get('kind','other')
            if org_kind not in {'clinic','payer','group','health_system','other'}:raise ValueError('Unknown organization kind')
            item.update(kind=org_kind,identifiers=identifiers)
            conn.execute('INSERT INTO organization VALUES (?,?,?,?,?,?,?)',(item['id'],label,org_kind,packed(identifiers),actor,reason,item['created_at']))
        elif kind == 'networks':
            owner = payload.get('payer_organization_id') or None
            if owner and conn.execute("SELECT id FROM organization WHERE id=? AND kind='payer'",(owner,)).fetchone() is None:
                raise ValueError('Network owner must be an explicitly selected payer organization')
            item.update(payer_organization_id=owner,identifiers=identifiers)
            conn.execute('INSERT INTO network VALUES (?,?,?,?,?,?,?)',(item['id'],label,owner,packed(identifiers),actor,reason,item['created_at']))
        else:
            org = payload.get('organization_id') or None
            if org and conn.execute('SELECT id FROM organization WHERE id=?',(org,)).fetchone() is None:raise ValueError('Organization not found')
            item['organization_id'] = org
            conn.execute('INSERT INTO practice_location VALUES (?,?,?,?,?,?)',(item['id'],label,org,actor,reason,item['created_at']))
    return item


def bind_source(store, payload):
    source, kind, key, target, actor, reason = (store.required(payload, field) for field in ('source','kind','source_key','target_id','actor','reason'))
    if kind not in TARGETS:raise ValueError('Binding kind must be network, organization or location')
    table, column = TARGETS[kind]
    with store.db() as conn:
        conn.execute('begin immediate')
        if not conn.execute(f'SELECT id FROM {table} WHERE id=?',(target,)).fetchone():raise ValueError('Binding target not found')
        prior = conn.execute('SELECT * FROM identity_binding WHERE source=? AND kind=? AND source_key=? ORDER BY revision DESC LIMIT 1',(source,kind,key)).fetchone()
        expected = payload.get('expected_binding_id')
        if expected != (prior['id'] if prior else None):raise Conflict('Source binding changed; review its current revision before replacing')
        item = {'id':uid(),'source':source,'kind':kind,'source_key':key,
                'organization_id':None,'network_id':None,'practice_location_id':None,
                'previous_id':prior['id'] if prior else None,'revision':prior['revision']+1 if prior else 1,
                'actor':actor,'reason':reason,'created_at':now()}
        item[column]=target
        conn.execute('INSERT INTO identity_binding VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',tuple(item.values()))
    return binding_record(item,True)


def binding_snapshot(conn, receipt, settings):
    if settings.get('roster_kind','clinic') not in {'clinic','network'}:raise ValueError('Choose clinic or network roster kind')
    if settings.get('roster_kind') != 'network':return {}
    if receipt['profile'] != 'flat' or not receipt['label'].lower().endswith(('.csv','.xlsx')):
        raise ValueError('Network rosters require a mapped CSV or XLSX file')
    bindings = settings.get('bindings',{})
    if not isinstance(bindings,dict) or set(bindings)-set(TARGETS):raise ValueError('Choose typed source bindings')
    snapshot = {}
    for kind, choices in bindings.items():
        if not isinstance(choices,dict):raise ValueError('Bindings map exact source codes to revision IDs')
        for key, binding_id in choices.items():
            row=conn.execute('SELECT * FROM identity_binding WHERE id=?',(binding_id,)).fetchone()
            if not row or row['source'] != receipt['source'] or row['kind'] != kind or row['source_key'] != key:
                raise ValueError('Binding revision has incompatible source, kind or source key')
            snapshot[binding_id]=binding_record(row)
    fixed = settings.get('fixed_network_binding_id')
    if fixed:
        row=conn.execute('SELECT * FROM identity_binding WHERE id=?',(fixed,)).fetchone()
        if not row or row['source']!=receipt['source'] or row['kind']!='network':raise ValueError('Fixed network needs a reviewed network source binding')
        snapshot[fixed]=binding_record(row)
    check_bindings(conn,snapshot)
    return snapshot


def check_bindings(conn, snapshot):
    for binding in snapshot.values():
        current=conn.execute('SELECT id FROM identity_binding WHERE source=? AND kind=? AND source_key=? ORDER BY revision DESC LIMIT 1',
                             (binding['source'],binding['kind'],binding['source_key'])).fetchone()
        if current is None or current['id']!=binding['id']:
            raise Conflict('Source binding changed; review a new mapping revision before acceptance')


def interpret_rows(rows, spec):
    if spec.get('roster_kind')!='network':return
    snapshot=spec.get('binding_snapshot',{})
    bindings=spec.get('bindings',{})
    fixed=snapshot.get(spec.get('fixed_network_binding_id'))
    for row in rows:
        norm=row['normalized']; problems=row['problems']; used=[]
        def resolve(kind,key,required=True):
            binding=snapshot.get(bindings.get(kind,{}).get(str(key or '')))
            if binding:used.append(binding['id']);return binding['target_id']
            if required:problems.append(f'Unresolved {kind} source binding: {key or "missing code"}')
            return None
        code=norm.get('network_code')
        if fixed:
            used.append(fixed['id']);network=fixed['target_id']
            if code and code!=fixed['source_key']:
                problems.append('Row network code conflicts with explicit fixed network scope')
                network=None  # Contradictory scope cannot establish presence in the default network.
        else:network=resolve('network',code)
        location=resolve('location',norm.get('location_id'))
        org=resolve('organization',norm.get('organization_code')) if norm.get('organization_code') else None
        if not row.get('native_id'):problems.append('Network participation requires a source-native record key')
        provider='NPI:'+str(norm['npi']) if len(str(norm.get('npi','')))==10 and str(norm['npi']).isdigit() else None
        dates={}
        for field in ('effective_date','end_date'):
            value=norm.get(field) or None;dates[field]=value
            if value:
                try:
                    parsed=date.fromisoformat(value)
                    if parsed.isoformat()!=value:raise ValueError()
                except (TypeError,ValueError):problems.append(f'{field} must use YYYY-MM-DD or remain unknown')
        if dates['effective_date'] and dates['end_date'] and dates['effective_date']>dates['end_date']:
            problems.append('Participation end date precedes effective date')
        norm['participation']={'network_id':network,'location_id':location,'organization_id':org,'provider_id':provider,
                               'binding_ids':sorted(used),'listed_status':norm.get('participation_status') or None,**dates}


def link_participation(store, conn, receipt, observation, spec):
    norm=observation['normalized'];part=norm['participation']
    conn.execute('INSERT INTO participation_observation VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
        (observation['id'],observation['native_id'],part['provider_id'],part['location_id'],part['network_id'],part['organization_id'],
         spec.get('mapping_revision_id'),part['listed_status'],part['effective_date'],part['end_date'],
         packed({key:spec['binding_snapshot'][key] for key in part['binding_ids']}),
         packed({key:norm.get(key) for key in ['network_label','organization_label','network_code','organization_code','location_id']})))
    stable=[receipt['source'],json.loads(receipt['metadata']).get('scope'),part['network_id'],part['provider_id'],part['location_id'],observation['native_id']]
    identity=digest([stable,'qa','participation'])
    prior=conn.execute('SELECT id FROM work_case WHERE identity_key=?',(identity,)).fetchone()
    cid=prior['id'] if prior else uid()
    if not prior:
        evidence={'original':observation['original'],'normalized':norm,'locator':observation['locator'],
                  'receipt_id':receipt['id'],'observation_id':observation['id'],'source':receipt['source'],'designation':receipt['designation'],
                  'provider_id':part['provider_id'],'location_id':part['location_id'],'listing_value':part['listed_status'],
                  'reference_value':None,'mapping_revision_id':spec.get('mapping_revision_id'),'binding_ids':part['binding_ids']}
        conn.execute('INSERT INTO work_case VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
             (cid,'qa',identity,str(norm.get('provider_name','')),part['location_id'],'participation','Review source-asserted network participation',
              'medium','Source assertion requires scoped human review','new',None,None,0,packed(evidence),None,None,now(),now()))
        conn.execute('INSERT INTO case_scope VALUES (?,?,?,?,?)',(cid,part['network_id'],part['organization_id'],part['location_id'],observation['native_id']))
    conn.execute('INSERT OR IGNORE INTO work_evidence VALUES (?,?)',(cid,observation['id']))
    conn.execute('INSERT INTO participation_review_evidence(case_id,attempt_id,status,identity_key,locator,payload) VALUES (?,?,?,?,?,?)',
         (cid,observation['attempt_id'],observation.get('comparison','accepted'),identity,observation['locator'],packed({'observation_id':observation['id'],'assertion':'Source listed; not human verification'})))
