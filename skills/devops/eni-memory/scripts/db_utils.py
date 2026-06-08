"""SQLite production connection helpers with WAL, FK, and thread-safe transactions."""
import sqlite3
import threading
from contextlib import contextmanager

DB_PATH = "/root/.hermes/data/eni_memory.db"

_local = threading.local()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(
        DB_PATH,
        timeout=30.0,
        isolation_level=None,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        PRAGMA journal_mode = WAL;
        PRAGMA synchronous = NORMAL;
        PRAGMA foreign_keys = ON;
        PRAGMA busy_timeout = 5000;
        PRAGMA temp_store = MEMORY;
        PRAGMA cache_size = -65536;
        PRAGMA mmap_size = 268435456;
        PRAGMA wal_autocheckpoint = 1000;
        """
    )
    return conn


def get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn"):
        _local.conn = _connect()
    return _local.conn


@contextmanager
def tx(write: bool = False):
    conn = get_conn()
    conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
    try:
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def checkpoint():
    conn = get_conn()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")


def integrity_check() -> bool:
    conn = get_conn()
    row = conn.execute("PRAGMA integrity_check;").fetchone()
    return row[0] == "ok"


def backup(dst_path: str):
    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(dst_path)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
