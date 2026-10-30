"""Explicit storage ownership shared by CLI, services and disposable runners."""
import os
import sqlite3
from pathlib import Path


def storage_root() -> Path:
    return Path(os.environ.get('PDTL_ROOT', '.runtime/local')).resolve()


def database_path() -> Path:
    return Path(os.environ.get('PDTL_DB', str(storage_root() / 'directory.sqlite3')))


def output_path() -> Path:
    return storage_root() / 'exports'


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('pragma foreign_keys=ON')
    conn.execute('pragma journal_mode=WAL')
    conn.execute('pragma busy_timeout=10000')
    return conn
