import os
from pathlib import Path
import subprocess
import sys
import gc
import hashlib
import sqlite3
import pytest

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


def test_connection_context_commits_rolls_back_closes_and_finishes_wal_before_return(tmp_path):
    path=tmp_path/'lifecycle.sqlite3'
    with connect(path) as conn:
        conn.execute('CREATE TABLE retained(id TEXT PRIMARY KEY)')
        conn.execute("INSERT INTO retained VALUES ('original')")
    with pytest.raises(sqlite3.ProgrammingError,match='closed'):
        conn.execute('SELECT * FROM retained')
    committed=hashlib.sha256(path.read_bytes()).hexdigest()
    gc.collect()
    assert hashlib.sha256(path.read_bytes()).hexdigest()==committed
    with pytest.raises(RuntimeError,match='interrupted'):
        with connect(path) as interrupted:
            interrupted.execute("INSERT INTO retained VALUES ('rollback')")
            raise RuntimeError('interrupted')
    with pytest.raises(sqlite3.ProgrammingError,match='closed'):
        interrupted.execute('SELECT * FROM retained')
    with connect(path) as recovered:
        assert [row['id'] for row in recovered.execute('SELECT * FROM retained')]==['original']
