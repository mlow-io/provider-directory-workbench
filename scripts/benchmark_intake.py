"""Synthetic bounded-workload measurement; no performance promise for other machines."""
import csv
import io
import json
from pathlib import Path
import resource
import sys
import tempfile
import time

from provider_directory_truth_layer.intake_store import IntakeStore

count = int(sys.argv[1]) if len(sys.argv)>1 else 1000
root = Path(tempfile.mkdtemp(prefix='benchmark-'))
stream=io.StringIO()
writer=csv.writer(stream)
writer.writerow(['record_id','npi','provider_name','address','city','state','zip','phone','location_id'])
for index in range(count):
    writer.writerow([f'SYNTHETIC-{index}','1234567890','Synthetic Benchmark','1 Example Street','Boston','MA','02108','6175550100',f'SITE-{index}'])
payload=stream.getvalue().encode()
store=IntakeStore(root/'directory.sqlite3',root)
start=time.perf_counter()
receipt=store.receive(payload,'synthetic-benchmark.csv')
preview_seconds=time.perf_counter()-start
start=time.perf_counter()
accepted=store.commit(receipt['id'],{'actor':'Benchmark','reason':'Synthetic bounded qualification','policy':'valid_rows','expected_attempt':receipt['attempt_id']})
commit_seconds=time.perf_counter()-start
with store.db() as conn:
    integrity=conn.execute('pragma integrity_check').fetchone()[0]
    foreign_keys=conn.execute('pragma foreign_key_check').fetchall()
peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
result={'synthetic_rows':count,'bytes':len(payload),'preview_seconds':round(preview_seconds,3),'commit_seconds':round(commit_seconds,3),'committed_rows_per_second':round(count/commit_seconds,1),'peak_process_rss_mib':round(peak/(1024*1024 if sys.platform=='darwin' else 1024),1),'integrity':integrity,'foreign_key_violations':len(foreign_keys),'storage':str(root),'limits':{'artifact_bytes':10*1024*1024,'tabular_rows':20000},'scope':'Single local process; parsing plus retained JSON/evidence, no network; RSS is entire Python process'}
print(json.dumps(result,indent=2))
