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
