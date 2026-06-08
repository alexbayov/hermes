"""SQLite production connection helpers with WAL, FK, and thread-safe transactions."""
import sqlite3
import threading
import time
import functools
from contextlib import contextmanager

DB_PATH = "/root/.hermes/data/eni_memory.db"

_local = threading.local()


def retry_on_lock(max_retries=3, delays=(0.1, 0.2, 0.4)):
    """Decorator: retry sqlite3 OperationalError containing 'locked' or 'busy' with exponential backoff."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except sqlite3.OperationalError as e:
                    error_msg = str(e).lower()
                    if 'locked' in error_msg or 'busy' in error_msg:
                        if attempt < max_retries:
                            time.sleep(delays[attempt])
                            continue
                    raise
        return wrapper
    return decorator


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
    if hasattr(_local, "conn"):
        try:
            _local.conn.execute("SELECT 1")
            return _local.conn
        except (sqlite3.ProgrammingError, sqlite3.OperationalError):
            del _local.conn
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


@retry_on_lock()
def checkpoint():
    conn = get_conn()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")


@retry_on_lock()
def integrity_check() -> bool:
    conn = get_conn()
    row = conn.execute("PRAGMA integrity_check;").fetchone()
    return row[0] == "ok"


@retry_on_lock()
def backup(dst_path: str):
    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(dst_path)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
