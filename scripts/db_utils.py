"""
ENI Memory System v2 — Database utilities.

Provides connection factory with WAL/journal/Sync tuning, a retry-on-lock
decorator for concurrent access, and a transaction decorator for atomic writes.

All decorators are composable.  Stacking order:
    @retry_on_lock()   # outer: retries the entire transaction
    @transaction        # inner: wraps in BEGIN/COMMIT/ROLLBACK
"""

import sqlite3
import time
import logging
from functools import wraps

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Connection factory
# ---------------------------------------------------------------------------

def get_db_connection(db_path: str) -> sqlite3.Connection:
    """Return a *single* sqlite3.Connection with production-safe PRAGMAs.

    WAL mode is set idempotently — the function first reads the current
    journal mode and only switches if it isn't already ``wal``.  This also
    means the first call on a fresh DB will convert it to WAL permanently.
    """
    conn = sqlite3.connect(db_path, timeout=5.0)

    conn.execute("PRAGMA foreign_keys=ON")

    # Idempotent WAL activation
    (current_mode,) = conn.execute("PRAGMA journal_mode").fetchone()
    if current_mode.upper() != "WAL":
        conn.execute("PRAGMA journal_mode=WAL")

    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")

    conn.row_factory = sqlite3.Row
    return conn

# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def retry_on_lock(max_retries: int = 3, backoff_ms: int = 100):
    """Decorate a DB-writing function to retry on ``sqlite3.OperationalError``
    caused by ``locked`` or ``busy`` conditions.

    Parameters
    ----------
    max_retries : int
        Maximum number of attempts (including the first).
    backoff_ms : int
        Initial back-off in milliseconds.  Doubles after each failed attempt.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            delay_s = backoff_ms / 1000.0

            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except sqlite3.OperationalError as exc:
                    msg = str(exc).lower()
                    if "locked" not in msg and "busy" not in msg:
                        raise  # Non-lock error — re-raise immediately
                    last_exc = exc
                    if attempt < max_retries:
                        print(
                            f"[retry_on_lock] {func.__name__} locked/busy — "
                            f"retry {attempt}/{max_retries} after "
                            f"{delay_s*1000:.0f}ms",
                            file=__import__('sys').stderr,
                        )
                        time.sleep(delay_s)
                        delay_s *= 2  # exponential back-off

            raise RuntimeError(
                f"Database lock after {max_retries} retries on "
                f"{func.__name__}: {last_exc}"
            ) from last_exc
        return wrapper
    return decorator


def transaction(func):
    """Decorate a function that expects a ``sqlite3.Connection`` as its first
    positional argument (or the ``conn`` keyword argument).

    Wraps the call in ``BEGIN`` / ``COMMIT`` / ``ROLLBACK``.  If the
    ``ROLLBACK`` itself fails (e.g. the connection is already in a bad state)
    it is silently swallowed so the original exception propagates.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Extract the connection — first positional arg, or conn= kwarg
        conn = args[0] if args else kwargs.get("conn")
        if conn is None:
            raise ValueError(
                "transaction() requires a sqlite3.Connection as the first "
                "positional argument or as the 'conn' keyword argument."
            )

        conn.execute("BEGIN")
        try:
            result = func(*args, **kwargs)
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass  # best-effort — original exception takes priority
            raise
        else:
            conn.commit()
            return result
    return wrapper
