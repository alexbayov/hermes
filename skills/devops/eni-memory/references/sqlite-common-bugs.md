# SQLite Common Bugs — ENI Memory System

Bugs encountered during development of the SQLite persistent memory layer. All are classic SQLite + Python gotchas that cost time if not documented.

## 1. Connection vs Cursor — `fetchall()` on Connection

### Symptom
```python
with sqlite3.connect(DB) as c:
    c.execute("SELECT * FROM t")
    rows = c.fetchall()   # AttributeError: 'sqlite3.Connection' object has no attribute 'fetchall'
```

### Root cause
`sqlite3.connect(...)` returns a `Connection`. `Connection.execute()` is a convenience method that creates a temporary cursor, executes, and returns the cursor. But the temporary cursor is discarded immediately — you cannot call `.fetchall()` on the connection.

### Fix
```python
with sqlite3.connect(DB) as c:
    cur = c.cursor()
    cur.execute("SELECT * FROM t")
    rows = cur.fetchall()   # ✓ works
```

### Rule
Always create a named `cursor` variable if you need `.fetchall()`, `.fetchone()`, or `.fetchmany()`. Only use `conn.execute()` for DDL or INSERT/UPDATE where you don't need results.

---

## 2. Global vs Per-Session Aggregates

### Symptom
`validate_last_turn.py` reported `last_turn=6` for a brand-new session that only had turns 0-1. The session had 2 messages but the validator claimed 6.

### Root cause
```python
# WRONG — global across all sessions
row = c.execute("SELECT MAX(turn_id) FROM messages").fetchone()

# CORRECT — scoped to the active session
row = c.execute(
    "SELECT MAX(turn_id) FROM messages WHERE session_id=?",
    (sid,)
).fetchone()
```

All aggregate queries (`MAX`, `MIN`, `COUNT`, `SUM`) must include `WHERE session_id=?` unless you explicitly want cross-session statistics. In a parent-chain system, the DB contains multiple sessions and aggregates are almost always session-scoped.

---

## 3. PRAGMA foreign_keys = ON is Per-Connection

`PRAGMA foreign_keys=ON` must be executed on *every* connection. It does not persist in the database file. The `db_utils.get_db_connection()` helper should always set it.

---

## 4. WAL Mode Activation Check

`PRAGMA journal_mode=WAL` returns a string. On some systems it returns `'wal'` (lowercase), on others `'WAL'` (uppercase). Always compare with `.upper()`.

```python
current = conn.execute("PRAGMA journal_mode").fetchone()[0]
if current.upper() != "WAL":
    conn.execute("PRAGMA journal_mode=WAL")
```

---

## 5. Schema Discovery After Schema Changes

When debugging schema mismatches, use `PRAGMA table_info(table_name)` instead of guessing column names from memory.

```python
cur.execute("PRAGMA table_info(messages)")
for col in cur.fetchall():
    print(f"  {col[1]} ({col[2]})")  # name, type
```

---

## 6. VACUUM INTO Cannot Run Inside a Transaction

### Symptom
```python
with tx(write=True) as conn:      # db_utils.tx() wraps BEGIN IMMEDIATE
    conn.execute("VACUUM INTO '/tmp/backup.db';")
# sqlite3.OperationalError: cannot VACUUM from within a transaction
```

### Root cause
`VACUUM INTO` is a special operation that rewrites the entire database file. SQLite forbids it inside any explicit transaction (`BEGIN`, `BEGIN IMMEDIATE`, or `SAVEPOINT`).

### Fix
Create a **fresh, separate connection** that is not inside any transaction:
```python
import sqlite3
conn = sqlite3.connect(DB_PATH)
conn.execute("VACUUM INTO '/tmp/backup.db';")
conn.close()
```

Do not use `get_conn()` (which may be inside `tx()`) for `VACUUM INTO`. This also applies to `PRAGMA wal_checkpoint(TRUNCATE)` — while it usually works inside a transaction, it is cleaner to run it on a fresh connection.

---

## 7. Thread-Local Connection Staleness After `close()`

### Symptom
```python
conn = get_conn()   # thread-local, cached
conn.close()
# ... later in the same thread ...
conn = get_conn()   # returns the CLOSED connection
conn.execute("SELECT 1")  # sqlite3.ProgrammingError: Cannot operate on a closed database
```

### Root cause
`db_utils._local` caches the connection object per thread. Calling `.close()` does not clear the thread-local cache. Any subsequent `get_conn()` returns the stale handle.

### Fix
Add a liveness probe inside `get_conn()` and re-create if the connection is dead:
```python
def get_conn():
    if hasattr(_local, "conn"):
        try:
            _local.conn.execute("SELECT 1")
            return _local.conn
        except (sqlite3.ProgrammingError, sqlite3.OperationalError):
            del _local.conn
    _local.conn = _connect()
    return _local.conn
```

---

## 8. SQLite RETURNING Clause Requires 3.35+

### Symptom
```python
row = conn.execute(
    "INSERT INTO compaction_runs (...) VALUES (...) RETURNING id"
).fetchone()["id"]
# sqlite3.OperationalError: near "RETURNING": syntax error
```

### Root cause
The `RETURNING` clause was added in SQLite 3.35.0 (released March 2021). Python 3.11 bundles SQLite 3.39+, so this is usually safe on modern systems. However, older Python builds, Alpine Linux musl builds, or custom SQLite compiles may ship an older version.

### Fix
Use the traditional `lastrowid` approach for maximum compatibility, or guard with a version check:
```python
# Universal fallback
import sqlite3
version = sqlite3.sqlite_version_info
if version >= (3, 35, 0):
    row = conn.execute("INSERT INTO t (...) VALUES (...) RETURNING id").fetchone()
    new_id = row[0]
else:
    cur = conn.execute("INSERT INTO t (...) VALUES (...)")
    new_id = cur.lastrowid
```

### Rule
When writing scripts that may run on diverse environments (containers, older distros, minimal Python builds), prefer `lastrowid` over `RETURNING`. If you use `RETURNING`, document the minimum SQLite version in the script header.
