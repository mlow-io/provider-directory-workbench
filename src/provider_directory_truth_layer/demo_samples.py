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
]


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
