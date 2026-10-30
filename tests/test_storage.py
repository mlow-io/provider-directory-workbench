import os
from pathlib import Path
import subprocess
import sys

from provider_directory_truth_layer.storage import connect


def test_connection_enforces_settings(tmp_path):
    with connect(tmp_path/'test.db') as conn:
        assert conn.execute('pragma foreign_keys').fetchone()[0] == 1
        assert conn.execute('pragma journal_mode').fetchone()[0] == 'wal'
        assert conn.execute('pragma busy_timeout').fetchone()[0] == 10000


def test_validation_owns_storage_even_with_inherited_database(tmp_path):
    sentinel=tmp_path/'working.sqlite3'
    sentinel.write_bytes(b'ORIGINAL WORKING DATA: MUST NOT TOUCH')
    result=subprocess.run([sys.executable,'scripts/run_validation.py'],env={**os.environ,'PDTL_DB':str(sentinel),'PDTL_ROOT':str(tmp_path/'working')},capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    assert sentinel.read_bytes()==b'ORIGINAL WORKING DATA: MUST NOT TOUCH'
    assert not (tmp_path/'working').exists()
