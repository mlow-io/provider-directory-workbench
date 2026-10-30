"""Generate unmistakably synthetic, offline employer demonstration inputs."""
from pathlib import Path
import csv
import json
from openpyxl import Workbook
from datetime import datetime
from functools import lru_cache
import io
import tempfile
import zipfile

WORKBOOK_MAPPING = dict(zip(
    ['record_id','npi','provider_name','address','city','state','zip','phone','location_id','reference_phone'],
    ['Roster key','Registry number','Clinician','Street','Town','Region','Postal','Listed phone','Site key','Requested phone'],
))

SAMPLES = [
    {'id': 'clinic-workbook', 'label': 'Synthetic clinic workbook', 'description': 'Start here: one clinician, two sites, unfamiliar columns and one malformed row.', 'filename': 'synthetic-clinic.xlsx', 'profile': 'flat'},
    {'id': 'clinic-csv', 'label': 'Synthetic clinic CSV', 'description': 'Same two sites in a different file shape; preserve work and attach later evidence.', 'filename': 'synthetic-clinic.csv', 'profile': 'flat'},
    {'id': 'clinic-changed', 'label': 'Synthetic changed delivery', 'description': 'Reordered sites and a changed NORTH phone; later evidence does not verify work.', 'filename': 'synthetic-changed.csv', 'profile': 'flat'},
    {'id': 'nppes', 'label': 'Synthetic NPPES response', 'description': 'Offline saved response with two practice addresses; not a live lookup.', 'filename': 'synthetic-nppes.json', 'profile': 'nppes'},
    {'id': 'cms', 'label': 'Synthetic CMS clinician response', 'description': 'Offline enrollment/group/address example; not a live lookup.', 'filename': 'synthetic-cms.json', 'profile': 'cms'},
    {'id': 'network-baseline', 'label': 'Synthetic network baseline CSV', 'description': 'Prepare explicit synthetic organization, network, and location catalog records; review source bindings, save a mapping, then accept this three-row roster.', 'filename': 'synthetic-network-baseline.csv', 'profile': 'flat'},
    {'id': 'network-changed', 'label': 'Synthetic changed network CSV', 'description': 'Apply the reviewed network mapping explicitly to a changed delivery; inspect new, changed, blocked, unresolved, and missing rows before acceptance.', 'filename': 'synthetic-network-changed.csv', 'profile': 'flat'},
    {'id': 'network-header-drift', 'label': 'Synthetic network header drift CSV', 'description': 'The required phone header is renamed. Review and save a new mapping revision explicitly before any acceptance.', 'filename': 'synthetic-network-header-drift.csv', 'profile': 'flat'},
]

NETWORK_HEADERS = ['record_id','npi','provider_name','address','city','state','zip','phone','location_id',
                   'network_code','network_label','organization_code','organization_label',
                   'participation_status','effective_date','end_date']


def _network_row(native_id, network, location, phone, status='listed'):
    address, postal = ('1 Example Street', '02108') if location == 'NORTH' else ('2 Example Street', '02109')
    return {'record_id': native_id, 'npi': '1234567890', 'provider_name': 'Synthetic Avery Example',
            'address': address, 'city': 'Boston', 'state': 'MA', 'zip': postal, 'phone': phone,
            'location_id': location, 'network_code': network, 'network_label': 'Synthetic ' + network,
            'organization_code': 'CLINIC', 'organization_label': 'Synthetic Clinic',
            'participation_status': status, 'effective_date': '2026-01-01', 'end_date': ''}


def _write_network_csv(path, rows, headers):
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def generate(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Clinic roster'
    sheet.append(['SYNTHETIC clinic roster — no real clinicians'])
    sheet.append(['Roster key','Registry number','Clinician','Street','Town','Region','Postal','Listed phone','Site key','Requested phone'])
    sheet.append(['ROSTER-A','1234567890','Synthetic Avery Example','1 Example Street','Boston','MA','02108','6175550100','NORTH','6175550199'])
    sheet.append(['ROSTER-B','1234567890','Synthetic Avery Example','2 Example Street','Boston','MA','02109','6175550101','SOUTH','6175550198'])
    sheet.append(['ROSTER-BAD','','Synthetic Incomplete Example','3 Example Street','Boston','MA','02108','123','UNKNOWN','6175550199'])
    workbook.properties.created = workbook.properties.modified = datetime(2026, 6, 26)
    raw = io.BytesIO()
    workbook.save(raw)
    # Stable archive timestamps make repeat samples identical across processes/restarts.
    with zipfile.ZipFile(raw) as source, zipfile.ZipFile(root/'synthetic-clinic.xlsx', 'w', zipfile.ZIP_DEFLATED) as target:
        for name in source.namelist():
            content = source.read(name)
            if name == 'docProps/core.xml':
                import re
                content = re.sub(rb'(<dcterms:modified[^>]*>).*?(</dcterms:modified>)', rb'\g<1>2026-06-26T00:00:00Z\2', content)
            target.writestr(zipfile.ZipInfo(name, (2026, 6, 26, 0, 0, 0)), content)
    headers=['record_id','npi','provider_name','address','city','state','zip','phone','location_id','reference_phone']
    rows=[['ROSTER-A','1234567890','Synthetic Avery Example','1 Example Street','Boston','MA','02108','6175550100','NORTH','6175550199'],['ROSTER-B','1234567890','Synthetic Avery Example','2 Example Street','Boston','MA','02109','6175550101','SOUTH','6175550198']]
    for filename, values in [('synthetic-clinic.csv',rows),('synthetic-changed.csv',[rows[1], [*rows[0][:7],'6175550177',*rows[0][8:]]])]:
        with (root/filename).open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(headers);writer.writerows(values)
    nppes={'result_count':1,'results':[{'number':1234567890,'enumeration_type':'NPI-1','basic':{'first_name':'SYNTHETIC','last_name':'PUBLIC EXAMPLE','status':'A','last_updated':'2026-10-02'},'addresses':[{'address_purpose':'LOCATION','address_1':'1 Example Street','city':'Boston','state':'MA','postal_code':'02108','telephone_number':'6175550100'},{'address_purpose':'LOCATION','address_1':'2 Example Street','city':'Boston','state':'MA','postal_code':'02109','telephone_number':'6175550101'}],'taxonomies':[{'code':'207Q00000X','desc':'Family Medicine','primary':True}]}]}
    cms={'results':[{'npi':'1234567890','ind_enrl_id':'ENROLL-SYNTHETIC','org_pac_id':'GROUP-SYNTHETIC','adrs_id':'ADDRESS-SYNTHETIC','provider_first_name':'SYNTHETIC','provider_last_name':'MEDICARE EXAMPLE','adr_ln_1':'1 Example Street','citytown':'Boston','state':'MA','zip_code':'02108','telephone_number':'6175550100'}]}
    (root/'synthetic-nppes.json').write_text(json.dumps(nppes,indent=2))
    (root/'synthetic-cms.json').write_text(json.dumps(cms,indent=2))
    network_baseline = [
        _network_row('PART-001', 'CEDAR', 'NORTH', '6175550100'),
        _network_row('PART-002', 'CEDAR', 'SOUTH', '6175550101'),
        _network_row('PART-003', 'PINE', 'NORTH', '6175550100'),
    ]
    network_changed = [
        {**_network_row('PART-004', 'PINE', 'SOUTH', '6175550101'), 'delivery_note': 'Synthetic new participation'},
        {**_network_row('PART-003', 'PINE', 'NORTH', '6175550100'), 'delivery_note': 'Synthetic duplicate conflict'},
        {**_network_row('PART-001', 'CEDAR', 'NORTH', '6175550177'), 'delivery_note': 'Synthetic changed phone'},
        {**_network_row('PART-U', 'UNKNOWN', 'NORTH', '6175550100'), 'delivery_note': 'Synthetic unresolved network'},
        {**_network_row('PART-003', 'PINE', 'NORTH', '6175550100', 'not_listed'), 'delivery_note': 'Synthetic duplicate conflict'},
    ]
    changed_headers = ['network_code', 'location_id', 'record_id', 'npi', 'phone', 'provider_name',
                       'organization_code', 'network_label', 'organization_label', 'participation_status',
                       'effective_date', 'end_date', 'address', 'city', 'state', 'zip', 'delivery_note']
    _write_network_csv(root/'synthetic-network-baseline.csv', network_baseline, NETWORK_HEADERS)
    _write_network_csv(root/'synthetic-network-changed.csv', network_changed, changed_headers)
    _write_network_csv(root/'synthetic-network-header-drift.csv',
                       [{('Published phone' if key == 'phone' else key): value for key, value in item.items()}
                        for item in network_changed],
                       [('Published phone' if key == 'phone' else key) for key in changed_headers])
    return root


@lru_cache(maxsize=1)
def sample_payloads():
    """Generate only fixed synthetic inputs; callers cannot select a path or URL."""
    with tempfile.TemporaryDirectory(prefix='pdtl-samples-') as directory:
        root = generate(Path(directory))
        return {sample['id']: (root/sample['filename']).read_bytes() for sample in SAMPLES}


if __name__ == '__main__':
    import sys
    print(generate(Path(sys.argv[1]) if len(sys.argv)>1 else Path('.runtime/demo-inputs')))
