"""Explicit, idempotent synthetic catalog preparation for the offline demo only."""
from uuid import NAMESPACE_URL, uuid5
from .intake_store import Conflict, now, packed

SOURCE='synthetic-network-demo'
SCOPE='synthetic-network-roster-v1'


def demo_id(name):
    return uuid5(NAMESPACE_URL,'https://example.invalid/provider-directory/synthetic-v1/'+name).hex


def settings():
    return {'roster_kind':'network','bindings':{
        'network':{code:demo_id('binding-network-'+code) for code in ['CEDAR','PINE']},
        'location':{code:demo_id('binding-location-'+code) for code in ['NORTH','SOUTH']},
        'organization':{'CLINIC':demo_id('binding-organization-CLINIC')}}}


def prepared_settings(store):
    selected=settings()
    with store.db() as conn:
        for kind,values in selected['bindings'].items():
            for code,binding_id in values.items():
                row=conn.execute('SELECT id FROM identity_binding WHERE source=? AND kind=? AND source_key=? ORDER BY revision DESC LIMIT 1',(SOURCE,kind,code)).fetchone()
                if row is None or row['id']!=binding_id:return None
    return selected


def prepare(store):
    actor,reason='Synthetic demo setup','Explicit offline preparation requested; no import, acceptance, verification or payer update'
    created=now()
    with store.db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        # IDs belong to this versioned fixture. Labels are never used to find/merge user records.
        for code,label,kind in [('PAYER','Synthetic Payer','payer'),('CLINIC','Synthetic Clinic','clinic')]:
            record_id=demo_id('organization-'+code)
            existing=conn.execute('SELECT * FROM organization WHERE id=?',(record_id,)).fetchone()
            if existing and (existing['label'],existing['kind'])!=(label,kind):raise Conflict('Synthetic catalog identity has changed; use a fresh isolated demo root')
            conn.execute('INSERT OR IGNORE INTO organization VALUES (?,?,?,?,?,?,?)',(record_id,label,kind,packed([{'namespace':'synthetic-demo','value':code}]),actor,reason,created))
        for code in ['CEDAR','PINE']:
            record_id=demo_id('network-'+code);owner=demo_id('organization-PAYER')
            existing=conn.execute('SELECT * FROM network WHERE id=?',(record_id,)).fetchone()
            if existing and (existing['label'],existing['payer_organization_id'])!=('Synthetic '+code,owner):raise Conflict('Synthetic network identity has changed; use a fresh demo root')
            conn.execute('INSERT OR IGNORE INTO network VALUES (?,?,?,?,?,?,?)',(record_id,'Synthetic '+code,owner,packed([{'namespace':'synthetic-demo','value':code}]),actor,reason,created))
        for code in ['NORTH','SOUTH']:
            record_id=demo_id('location-'+code);owner=demo_id('organization-CLINIC')
            existing=conn.execute('SELECT * FROM practice_location WHERE id=?',(record_id,)).fetchone()
            if existing and (existing['label'],existing['organization_id'])!=('Synthetic '+code,owner):raise Conflict('Synthetic location identity has changed; use a fresh demo root')
            conn.execute('INSERT OR IGNORE INTO practice_location VALUES (?,?,?,?,?,?)',(record_id,'Synthetic '+code,owner,actor,reason,created))
        for kind,values in settings()['bindings'].items():
            for code,binding_id in values.items():
                current=conn.execute('SELECT id FROM identity_binding WHERE source=? AND kind=? AND source_key=? ORDER BY revision DESC LIMIT 1',(SOURCE,kind,code)).fetchone()
                if current and current['id']!=binding_id:
                    raise Conflict('Synthetic source binding was reviewed differently; preserve it and use a fresh isolated demo root')
                targets={key:None for key in ['organization_id','network_id','practice_location_id']}
                column={'network':'network_id','location':'practice_location_id','organization':'organization_id'}[kind]
                targets[column]=demo_id(kind+'-'+code)
                conn.execute('INSERT OR IGNORE INTO identity_binding VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                    (binding_id,SOURCE,kind,code,targets['organization_id'],targets['network_id'],targets['practice_location_id'],None,1,actor,reason,created))
    return {'notice':'SYNTHETIC catalog and reviewed codebook prepared explicitly. No rows imported, accepted or verified.',
            'source':SOURCE,'settings':settings(),'catalog':store.catalog()}
