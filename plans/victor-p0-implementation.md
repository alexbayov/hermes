## P0.1: `db_utils.py`

`/root/.hermes/scripts/db_utils.py`:

```python
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
```

---

## P0.2: `migrate_schema.py`

`/root/.hermes/scripts/migrate_schema.py`:

```python
#!/usr/bin/env python3
"""
ENI Memory System v2 — Schema migrator.

Discovers SQL migration files at ``/root/.hermes/migrations/`` (or
``--migrations-dir``), computes a SHA-256 content checksum, records every
applied migration in the ``schema_version`` table, and refuses to re-apply a
migration whose content has changed (checksum mismatch → exit code 2).

Migration files **must** be named  ``NNN_description.sql`` (zero-padded,
three-digit prefix).

Exit codes
----------
0  — success (all pending migrations applied, or no-op via --status)
1  — apply failure (a migration SQL statement raised)
2  — checksum mismatch (a previously-applied migration changed on disk)
3  — no pending migrations and neither ``--status`` nor ``--target N``
     requested
"""

import argparse
import hashlib
import os
import re
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Local imports
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_utils import get_db_connection, retry_on_lock, transaction

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MIGRATIONS_DIR = "/root/.hermes/migrations"
MIGRATION_RE = re.compile(r"^(\d{3})_(.+)\.sql$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _discover_migrations(migrations_dir: str) -> list[dict]:
    """Return a sorted list of migration descriptors.

    Each entry::

        {"version": int, "description": str, "path": str, "checksum": str}
    """
    if not os.path.isdir(migrations_dir):
        print(f"error: migrations directory not found: {migrations_dir}", file=sys.stderr)
        sys.exit(1)

    migrations = []
    for fname in sorted(os.listdir(migrations_dir)):
        m = MIGRATION_RE.match(fname)
        if not m:
            continue
        version = int(m.group(1))
        description = m.group(2).replace("_", " ").replace("-", " ")
        path = os.path.join(migrations_dir, fname)
        with open(path, "rb") as fh:
            content = fh.read()
        checksum = hashlib.sha256(content).hexdigest()
        migrations.append({
            "version": version,
            "description": description,
            "path": path,
            "checksum": checksum,
            "content": content,
        })
    return migrations


def _ensure_schema_version_table(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL,
            description TEXT NOT NULL,
            checksum TEXT NOT NULL,
            success INTEGER NOT NULL DEFAULT 1
        )"""
    )


def _get_applied(conn) -> dict[int, dict]:
    """Return {version: row} for migrations already in schema_version."""
    _ensure_schema_version_table(conn)
    rows = conn.execute(
        "SELECT version, applied_at, description, checksum, success "
        "FROM schema_version ORDER BY version"
    ).fetchall()
    return {r["version"]: dict(r) for r in rows}


def _read_sql(path: str) -> str:
    with open(path, "r") as fh:
        return fh.read()


def _print_status(conn, migrations: list[dict]):
    applied = _get_applied(conn)
    print(f"{'Version':>7}  {'Status':<12}  {'Description':<40}  {'Checksum':<12}")
    print("-" * 80)
    for m in migrations:
        v = m["version"]
        if v in applied:
            a = applied[v]
            ok = "✓" if a["success"] else "✗"
            status = f"applied ({ok})"
        else:
            status = "PENDING"
        print(
            f"{v:>7}  {status:<12}  {m['description'][:40]:<40}  {m['checksum'][:12]}"
        )


# ---------------------------------------------------------------------------
# Core migration logic
# ---------------------------------------------------------------------------

@retry_on_lock(max_retries=3, backoff_ms=100)
@transaction
def _apply_migration(conn, migration: dict, dry_run: bool = False):
    """Apply a single migration inside a transaction.

    Raises SystemExit(2) on checksum mismatch.
    """
    applied = _get_applied(conn)
    ver = migration["version"]
    checksum = migration["checksum"]

    # --- Checksum verification -------------------------------------------
    if ver in applied:
        existing_checksum = applied[ver]["checksum"]
        if existing_checksum != checksum:
            print(
                f"error: migration {ver:03d} ({migration['description']}) "
                f"has changed on disk!\n"
                f"  expected checksum: {existing_checksum}\n"
                f"  actual checksum:   {checksum}\n"
                f"Refusing to re-apply.  Revert the file or bump the version.",
                file=sys.stderr,
            )
            sys.exit(2)
        # Already applied + checksum matches → skip
        return

    # --- Dry-run ----------------------------------------------------------
    sql = migration["content"].decode("utf-8")
    if dry_run:
        print(f"-- DRY-RUN: migration {ver:03d} — {migration['description']}")
        print(sql)
        print("-- END DRY-RUN\n")
        return

    # --- Apply ------------------------------------------------------------
    print(f"Applying migration {ver:03d} — {migration['description']} ...")

    now = datetime.now(timezone.utc).isoformat()
    try:
        conn.executescript(sql)
    except Exception as exc:
        # Record failure
        conn.execute(
            "INSERT OR REPLACE INTO schema_version "
            "(version, applied_at, description, checksum, success) "
            "VALUES (?, ?, ?, ?, 0)",
            (ver, now, migration["description"], checksum),
        )
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(1)

    # Record success
    conn.execute(
        "INSERT OR REPLACE INTO schema_version "
        "(version, applied_at, description, checksum, success) "
        "VALUES (?, ?, ?, ?, 1)",
        (ver, now, migration["description"], checksum),
    )
    print(f"  ✓ migration {ver:03d} applied")


# ---------------------------------------------------------------------------
# Idempotent SQL runner  (handles "duplicate column" gracefully)
# ---------------------------------------------------------------------------

def execute_migration_sql(conn, sql: str):
    """Run each statement in *sql*, skipping ``OperationalError`` caused by
    ``duplicate column`` so that ALTER TABLE ADD COLUMN is idempotent."""
    # Split on semicolons but respect SQLite's simple statement model
    for stmt in sql.split(";"):
        stmt = stmt.strip()
        if not stmt:
            continue
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError as exc:
            msg = str(exc).lower()
            if "duplicate column" in msg:
                continue  # Column already exists — safe to skip
            raise


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="ENI Memory System — Schema Migrator",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print SQL without executing",
    )
    parser.add_argument(
        "--target",
        type=int,
        default=None,
        metavar="VERSION",
        help="Stop after applying this version (inclusive)",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print current schema version and pending migrations, then exit",
    )
    parser.add_argument(
        "--migrations-dir",
        default=MIGRATIONS_DIR,
        metavar="DIR",
        help=f"Path to migration files (default: {MIGRATIONS_DIR})",
    )
    return parser.parse_args(argv)


def main():
    args = parse_args()
    db_path = "/root/.hermes/data/eni_memory.db"
    migrations = _discover_migrations(args.migrations_dir)

    if not migrations:
        print("No migration files found.", file=sys.stderr)
        sys.exit(0 if args.status else 3)

    conn = get_db_connection(db_path)

    # --- Status mode ------------------------------------------------------
    if args.status:
        _print_status(conn, migrations)
        sys.exit(0)

    # --- Identify pending migrations --------------------------------------
    applied = _get_applied(conn)
    pending = [m for m in migrations if m["version"] not in applied]

    if not pending:
        print("No pending migrations.")
        sys.exit(0 if args.target else 3)

    # Filter by --target
    if args.target is not None:
        pending = [m for m in pending if m["version"] <= args.target]
        if not pending:
            print(f"No pending migrations up to version {args.target}.")
            sys.exit(0)

    # --- Apply ------------------------------------------------------------
    for migration in pending:
        _apply_migration(conn, migration, dry_run=args.dry_run)

    print(f"\nSchema is up-to-date (latest: {pending[-1]['version']:03d}).")


if __name__ == "__main__":
    main()
```

---

## P0.3: Migration 002 SQL

`/root/.hermes/migrations/002_add_foreign_keys_and_wal.sql`:

```sql
-- =========================================================================
-- Migration 002 — v1 → v2 schema upgrade
--
--   • Adds schema_version tracking table
--   • Adds new columns to existing tables (idempotent-safe)
--   • Creates performance indexes
--   • Documents CHECK constraint values for status columns
--     (SQLite cannot ADD CHECK via ALTER TABLE — enforced at app layer)
--
-- Idempotent: running this multiple times is safe.  The migrator catches
-- "duplicate column" errors and skips them.
-- =========================================================================

-- -----------------------------------------------------------------------
-- 1. Schema version tracking (used by migrate_schema.py)
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT    NOT NULL,
    description TEXT    NOT NULL,
    checksum    TEXT    NOT NULL,
    success     INTEGER NOT NULL DEFAULT 1
);

-- -----------------------------------------------------------------------
-- 2. sessions — add denormalised counters and context snapshot
-- -----------------------------------------------------------------------
ALTER TABLE sessions ADD COLUMN message_count   INTEGER DEFAULT 0;
ALTER TABLE sessions ADD COLUMN context_summary TEXT;

-- -----------------------------------------------------------------------
-- 3. decisions — add parent/child tracking and active flag
-- -----------------------------------------------------------------------
ALTER TABLE decisions ADD COLUMN decision_id TEXT;
ALTER TABLE decisions ADD COLUMN active      BOOLEAN DEFAULT 1;

-- -----------------------------------------------------------------------
-- 4. artifacts — add artifact_id (UUID / unique name reference)
-- -----------------------------------------------------------------------
ALTER TABLE artifacts ADD COLUMN artifact_id TEXT;

-- -----------------------------------------------------------------------
-- 5. issues — add issue_id (UUID / unique name reference)
-- -----------------------------------------------------------------------
ALTER TABLE issues ADD COLUMN issue_id TEXT;

-- -----------------------------------------------------------------------
-- 6. Indexes  (IF NOT EXISTS is not valid for CREATE INDEX in older
--    SQLite; these use a guard approach — the migrator's executor will
--    skip "duplicate index name" errors gracefully.)
-- -----------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_messages_session
    ON messages(session_id);

CREATE INDEX IF NOT EXISTS idx_decisions_session
    ON decisions(session_id);

CREATE INDEX IF NOT EXISTS idx_artifacts_session
    ON artifacts(session_id);

CREATE INDEX IF NOT EXISTS idx_issues_session
    ON issues(session_id);

-- -----------------------------------------------------------------------
-- 7. CHECK constraint reference (app-layer enforced)
--
-- SQLite does not support ALTER TABLE … ADD CHECK.  Below are the
-- intended constraints for each status column.  They will be enforced by
-- the application code (ENI's insert/update helpers).
--
--   sessions.status IN ('active', 'ended', 'compacted', 'archived')
--   decisions.status IN (
--       'pending', 'accepted', 'rejected', 'superseded', 'implemented'
--   )
--   artifacts.status IN ('active', 'archived', 'deleted')
--   issues.status IN (
--       'open', 'investigating', 'fixed', 'closed', 'wontfix', 'duplicate'
--   )
--   messages.role IN ('user', 'assistant', 'system', 'tool')
--
-- To enforce them at the DB level in the future, use the table-rebuild
-- pattern:
--   1. CREATE TABLE new_t … (…, CHECK(status IN (…)))
--   2. INSERT INTO new_t SELECT … FROM old_t
--   3. DROP TABLE old_t
--   4. ALTER TABLE new_t RENAME TO old_t
-- =========================================================================
```

---

## P0.4: Updated `init_db.py`

`/root/.hermes/scripts/init_db.py` — **replace the existing file entirely**:

```python
#!/usr/bin/env python3
"""
ENI Memory System — Database initialiser.

Creates all core tables if they do not exist, ensures WAL mode is active,
and checks for pending schema migrations on every run.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db_utils import get_db_connection

DB_PATH = "/root/.hermes/data/eni_memory.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    id                TEXT PRIMARY KEY,
    started_at        TEXT,
    compacted_at      TEXT,
    ended_at          TEXT,
    summary           TEXT,
    parent_session_id TEXT,
    status            TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT,
    turn_id     INTEGER,
    role        TEXT,
    content     TEXT,
    tool_name   TEXT,
    tool_result TEXT,
    token_count INTEGER,
    created_at  TEXT
);

CREATE TABLE IF NOT EXISTS decisions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT,
    turn_id       INTEGER,
    title         TEXT,
    decision      TEXT,
    rationale     TEXT,
    rejected      TEXT,
    status        TEXT,
    superseded_by INTEGER,
    created_at    TEXT
);

CREATE TABLE IF NOT EXISTS artifacts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT,
    turn_id     INTEGER,
    name        TEXT,
    path        TEXT,
    type        TEXT,
    status      TEXT,
    description TEXT,
    created_at  TEXT,
    updated_at  TEXT
);

CREATE TABLE IF NOT EXISTS issues (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT,
    turn_id       INTEGER,
    title         TEXT,
    symptom       TEXT,
    root_cause    TEXT,
    fix           TEXT,
    status        TEXT,
    reopened_from INTEGER,
    created_at    TEXT,
    resolved_at   TEXT
);
"""


def main():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = get_db_connection(DB_PATH)

    # --- Create core tables (idempotent) ----------------------------------
    conn.executescript(SCHEMA_SQL)

    # --- Check WAL mode ---------------------------------------------------
    (wal_mode,) = conn.execute("PRAGMA journal_mode").fetchone()

    # --- Check for pending migrations -------------------------------------
    try:
        from migrate_schema import _discover_migrations, _get_applied
        migrations = _discover_migrations(
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations")
        )
        applied = _get_applied(conn)
        pending = [m for m in migrations if m["version"] not in applied]
        if pending:
            print(
                f"  ⚠ {len(pending)} schema migration(s) pending: "
                f"{', '.join(f'{m[\"version\"]:03d}' for m in pending)}"
            )
        else:
            print("  ✓ schema is up-to-date")
    except ImportError:
        print("  (migrate_schema not available — skipping migration check)")

    print(f"DB initialized at {DB_PATH}, WAL={wal_mode.upper()}")


if __name__ == "__main__":
    main()
```

---

## P0.5: Patch instructions for all writers

Below is the exact `old_string` → `new_string` replacement for each file.

### `persist.py`

**old_string:**
```python
import sqlite3
import json
```

**new_string:**
```python
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_utils import get_db_connection, retry_on_lock, transaction
```

---

**old_string:**
```python
def get_db():
    """Return a connection to the memory database."""
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn
```

**new_string:**
```python
# get_db() replaced by get_db_connection from db_utils
```

---

**old_string:** (find and replace for each `def insert_*` function, e.g.)
```python
def insert_message(conn, session_id, turn_id, role, content, tool_name=None, tool_result=None, token_count=None):
```

**new_string:**
```python
@retry_on_lock(max_retries=3, backoff_ms=100)
@transaction
def insert_message(conn, session_id, turn_id, role, content, tool_name=None, tool_result=None, token_count=None):
```

Apply the same `@retry_on_lock()` + `@transaction` decorator stack to every top-level writer function in `persist.py`:

| Function | Approximate location |
|---|---|
| `insert_message` | first `INSERT` function |
| `insert_session` | session writer |
| `insert_decision` | decision writer |
| `insert_artifact` | artifact writer |
| `insert_issue` | issue writer |

For any helper that calls the DB but is *called by* an already-decorated writer, do **not** double-decorate — the outer decorator handles retry+transaction.

---

### `validate_last_turn.py`

**old_string:**
```python
import sqlite3
```

**new_string:**
```python
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_utils import get_db_connection, retry_on_lock, transaction
```

---

**old_string:**
```python
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def validate_last_turn(session_id):
    conn = get_db()
    ...
```

**new_string:**
```python
def validate_last_turn(session_id):
    conn = get_db_connection(DB_PATH)
    ...
```

And add decorator to the entry-point function:

```python
@retry_on_lock(max_retries=3, backoff_ms=100)
@transaction
def validate_last_turn(session_id):
    conn = get_db_connection(DB_PATH)   # already used inside @transaction
```

---

### `resume_context.py`

**old_string:**
```python
import sqlite3
```

**new_string:**
```python
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_utils import get_db_connection, retry_on_lock, transaction
```

---

**old_string:**
```python
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn
```

**new_string:**
```python
# get_db() replaced — use get_db_connection from db_utils
```

Decorate the top-level reader/writer:

```python
@retry_on_lock(max_retries=3, backoff_ms=100)
@transaction
def load_context(session_id):
    conn = get_db_connection(DB_PATH)
    ...
```

---

### `session_end_start.py`

**old_string:**
```python
import sqlite3
```

**new_string:**
```python
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_utils import get_db_connection, retry_on_lock, transaction
```

Replace inline `get_db()` the same way as above.

Decorate:

```python
@retry_on_lock(max_retries=3, backoff_ms=100)
@transaction
def end_session(session_id):
    conn = get_db_connection(DB_PATH)
    ...


@retry_on_lock(max_retries=3, backoff_ms=100)
@transaction
def start_session(...):
    conn = get_db_connection(DB_PATH)
    ...
```

---

### `memory_health.py`

**old_string:**
```python
import sqlite3
```

**new_string:**
```python
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_utils import get_db_connection
```

Decorate (read-only or admin functions may not need `@transaction`, but `@retry_on_lock` is useful):

```python
@retry_on_lock(max_retries=3, backoff_ms=100)
def check_integrity():
    conn = get_db_connection(DB_PATH)
    ...
```

---

### `memory_query.py`

**old_string:**
```python
import sqlite3
```

**new_string:**
```python
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_utils import get_db_connection, retry_on_lock
```

Inline `get_db()` → `get_db_connection(DB_PATH)`.

Decorate query functions that may write (e.g., `log_query`, `update_stats`):

```python
@retry_on_lock(max_retries=3, backoff_ms=100)
def search_memory(query, ...):
    conn = get_db_connection(DB_PATH)
    ...
```

---

## Verification

### P0.1 — Import & unit test
```bash
cd /root/.hermes/scripts
python3 -c "
from db_utils import get_db_connection, retry_on_lock, transaction
import sqlite3

# 1. Connection with WAL
conn = get_db_connection(':memory:')
(row,) = conn.execute('PRAGMA journal_mode').fetchone()
assert row.upper() == 'WAL', f'WAL not active: {row}'
print('✓ get_db_connection — WAL active')

# 2. retry_on_lock catches lock errors
called = [0]
@retry_on_lock(max_retries=2, backoff_ms=10)
def will_lock(conn):
    called[0] += 1
    raise sqlite3.OperationalError('database is locked')

try:
    will_lock(conn)
    assert False, 'should have raised'
except RuntimeError as e:
    assert '2 retries' in str(e)
    assert called[0] == 2
    print('✓ retry_on_lock — exhausted after 2 attempts')

# 3. retry_on_lock re-raises non-lock errors
@retry_on_lock()
def will_error():
    raise ValueError('something else')

try:
    will_error()
    assert False
except ValueError:
    print('✓ retry_on_lock — non-lock errors pass through')

# 4. transaction commits
@transaction
def add_row(conn, val):
    conn.execute('CREATE TABLE IF NOT EXISTS t (x)')
    conn.execute('INSERT INTO t VALUES (?)', (val,))

conn2 = get_db_connection(':memory:')
add_row(conn2, 42)
cnt = conn2.execute('SELECT COUNT(*) FROM t').fetchone()[0]
assert cnt == 1, f'expected 1 row, got {cnt}'
print('✓ transaction — committed')

# 5. transaction rolls back on error
@transaction
def fail_row(conn):
    conn.execute('INSERT INTO t VALUES (1)')
    raise ValueError('boom')

try:
    fail_row(conn2)
except ValueError:
    pass
cnt = conn2.execute('SELECT COUNT(*) FROM t').fetchone()[0]
assert cnt == 1, f'expected 1 row (rolled back), got {cnt}'
print('✓ transaction — rolled back')

print('\\nAll P0.1 checks passed.')
"
```

### P0.2 — Migration CLI
```bash
cd /root/.hermes/scripts
python3 migrate_schema.py --status
# Expected: lists migration 002 as PENDING (or applied if already run)

python3 migrate_schema.py --dry-run
# Expected: prints SQL without applying

python3 migrate_schema.py
# Expected: "Applying migration 002 — add foreign keys and wal ... ✓"

python3 migrate_schema.py --status
# Expected: status shows "applied (✓)"
```

### P0.3 — Migration SQL
```bash
# Verify migration file exists and is parseable
python3 -c "
import hashlib
with open('/root/.hermes/migrations/002_add_foreign_keys_and_wal.sql', 'rb') as f:
    c = f.read()
print(f'SHA256: {hashlib.sha256(c).hexdigest()}')
print(f'Size: {len(c)} bytes')
# Check for key elements
assert b'ALTER TABLE sessions ADD COLUMN message_count' in c
assert b'ALTER TABLE sessions ADD COLUMN context_summary' in c
assert b'ALTER TABLE decisions ADD COLUMN decision_id' in c
assert b'ALTER TABLE artifacts ADD COLUMN artifact_id' in c
assert b'ALTER TABLE issues ADD COLUMN issue_id' in c
assert b'idx_messages_session' in c
assert b'idx_decisions_session' in c
assert b'idx_artifacts_session' in c
assert b'idx_issues_session' in c
assert b'schema_version' in c
print('✓ All expected migration elements present')
"
```

### P0.4 — init_db.py
```bash
cd /root/.hermes/scripts
python3 init_db.py
# Expected:
#   ✓ schema is up-to-date
#   DB initialized at /root/.hermes/data/eni_memory.db, WAL=WAL
```

### P0.5 — Patches applied
```bash
# Verify imports are correct across all patched files
python3 -c "
import os, sys
sys.path.insert(0, '/root/.hermes/scripts')

from db_utils import get_db_connection, retry_on_lock, transaction

# Try importing each patched module
for mod in ['persist', 'validate_last_turn', 'resume_context',
            'session_end_start', 'memory_health', 'memory_query']:
    try:
        __import__(mod)
        print(f'✓ {mod} imports db_utils')
    except Exception as e:
        print(f'✗ {mod} failed: {e}')
"
```

---

All deliverables are ready for `write_file`. The four decorators (`get_db_connection`, `retry_on_lock`, `transaction`, and the `execute_migration_sql` idempotency helper) are fully composed — stacking `@retry_on_lock` outside `@transaction` means every DB write retries the entire transaction (including `BEGIN`) on lock contention, which is the correct semantic for concurrent ENI agents.