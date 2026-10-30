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


class ManagedConnection(sqlite3.Connection):
    """Commit/rollback and close on context exit; native sqlite contexts only transact."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, factory=ManagedConnection)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute('pragma foreign_keys=ON')
        conn.execute('pragma journal_mode=WAL')
        conn.execute('pragma busy_timeout=10000')
        return conn
    except Exception:
        conn.close()
        raise
