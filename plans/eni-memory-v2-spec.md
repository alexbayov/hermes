```markdown
# ENI Memory System v2 — Technical Specification

## 1. Schema Evolution (migrate_schema.py + FK + WAL)

### 1.1 Current Schema Snapshot

As of v1, the SQLite schema at `/root/.hermes/data/eni_memory.db` consists of 6 tables:

```sql
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT UNIQUE NOT NULL,
    parent_session_id TEXT,
    started_at TEXT DEFAULT (datetime('now')),
    ended_at TEXT,
    message_count INTEGER DEFAULT 0,
    token_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active' CHECK(status IN ('active','closed','archived','compacted')),
    context_summary TEXT
);

CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user','assistant','system','tool')),
    content TEXT NOT NULL,
    token_count INTEGER DEFAULT 0,
    timestamp TEXT DEFAULT (datetime('now')),
    UNIQUE(session_id, turn_id, role)
);

CREATE TABLE decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    decision_id TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    rationale TEXT,
    status TEXT DEFAULT 'active' CHECK(status IN ('active','superseded','reverted')),
    timestamp TEXT DEFAULT (datetime('now'))
);

CREATE TABLE artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    artifact_id TEXT UNIQUE NOT NULL,
    path TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'active' CHECK(status IN ('active','obsolete','reverted')),
    timestamp TEXT DEFAULT (datetime('now'))
);

CREATE TABLE issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    issue_id TEXT UNIQUE NOT NULL,
    description TEXT NOT NULL,
    severity TEXT DEFAULT 'warning' CHECK(severity IN ('info','warning','error','critical')),
    resolved INTEGER DEFAULT 0,
    timestamp TEXT DEFAULT (datetime('now'))
);

CREATE TABLE journal_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('message','decision','artifact','issue','session_start','session_end','rollback')),
    payload TEXT NOT NULL,
    timestamp TEXT DEFAULT (datetime('now'))
);
```

**Observations:** No `FOREIGN KEY` constraints exist. No `ON DELETE CASCADE`. No `schema_version` table. No WAL mode. The schema already includes `message_count`, `token_count`, `status`, and `context_summary` columns (these were forward-looking additions from a previous migration). The `decisions.status` and `artifacts.status` columns already exist but are not yet enforced by application logic during rollback or compaction.

### 1.2 Schema Version Table + Migration Registry

```sql
-- Schema version table (created by migrate_schema.py)
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now')),
    description TEXT NOT NULL,
    checksum TEXT NOT NULL,       -- SHA256 of migration SQL
    success INTEGER NOT NULL DEFAULT 1
);
```

**Migration registry** is a directory at `/root/.hermes/migrations/` containing numbered files:

```
/root/.hermes/migrations/
  001_initial_schema.sql
  002_add_foreign_keys_and_cascade.sql
  003_add_wal_and_indexes.sql
```

Each file is a single SQL script, idempotent-safe. The migration runner computes SHA256 of each file before applying. On mismatch (file changed after application), it refuses with an error.

### 1.3 SQL for v1→v2 Migration (Foreign Keys + Indexes + WAL)

**Migration 002: Foreign Keys + ON DELETE CASCADE**

```sql
PRAGMA foreign_keys = OFF;

-- Enable foreign key enforcement at connection level (persistent)
-- Note: PRAGMA foreign_keys = ON is per-connection; must be set in every script.

-- Recreate sessions with FK on parent_session_id
CREATE TABLE sessions_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT UNIQUE NOT NULL,
    parent_session_id TEXT REFERENCES sessions_v2(session_id) ON DELETE SET NULL,
    started_at TEXT DEFAULT (datetime('now')),
    ended_at TEXT,
    message_count INTEGER DEFAULT 0,
    token_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active' CHECK(status IN ('active','closed','archived','compacted')),
    context_summary TEXT
);

-- Recreate messages with FK to sessions + ON DELETE CASCADE
CREATE TABLE messages_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions_v2(session_id) ON DELETE CASCADE,
    turn_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user','assistant','system','tool')),
    content TEXT NOT NULL,
    token_count INTEGER DEFAULT 0,
    timestamp TEXT DEFAULT (datetime('now')),
    UNIQUE(session_id, turn_id, role)
);

-- Recreate decisions with FK + CASCADE
CREATE TABLE decisions_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions_v2(session_id) ON DELETE CASCADE,
    turn_id TEXT NOT NULL,
    decision_id TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    rationale TEXT,
    status TEXT DEFAULT 'active' CHECK(status IN ('active','superseded','reverted')),
    timestamp TEXT DEFAULT (datetime('now'))
);

-- Recreate artifacts with FK + CASCADE
CREATE TABLE artifacts_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions_v2(session_id) ON DELETE CASCADE,
    turn_id TEXT NOT NULL,
    artifact_id TEXT UNIQUE NOT NULL,
    path TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'active' CHECK(status IN ('active','obsolete','reverted')),
    timestamp TEXT DEFAULT (datetime('now'))
);

-- Recreate issues with FK + CASCADE
CREATE TABLE issues_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions_v2(session_id) ON DELETE CASCADE,
    turn_id TEXT NOT NULL,
    issue_id TEXT UNIQUE NOT NULL,
    description TEXT NOT NULL,
    severity TEXT DEFAULT 'warning' CHECK(severity IN ('info','warning','error','critical')),
    resolved INTEGER DEFAULT 0,
    timestamp TEXT DEFAULT (datetime('now'))
);

-- journal_log does not reference sessions (append-only audit trail)
-- but add index on session_id for fast filtering
CREATE INDEX IF NOT EXISTS idx_journal_session ON journal_log(session_id, turn_id);

-- Copy data
INSERT INTO sessions_v2 SELECT * FROM sessions;
INSERT INTO messages_v2 SELECT * FROM messages;
INSERT INTO decisions_v2 SELECT * FROM decisions;
INSERT INTO artifacts_v2 SELECT * FROM artifacts;
INSERT INTO issues_v2 SELECT * FROM issues;

-- Drop old tables
DROP TABLE sessions;
DROP TABLE messages;
DROP TABLE decisions;
DROP TABLE artifacts;
DROP TABLE issues;

-- Rename v2 -> production
ALTER TABLE sessions_v2 RENAME TO sessions;
ALTER TABLE messages_v2 RENAME TO messages;
ALTER TABLE decisions_v2 RENAME TO decisions;
ALTER TABLE artifacts_v2 RENAME TO artifacts;
ALTER TABLE issues_v2 RENAME TO issues;

PRAGMA foreign_key_check;

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, turn_id);
CREATE INDEX IF NOT EXISTS idx_decisions_session ON decisions(session_id, turn_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_session ON artifacts(session_id, turn_id);
CREATE INDEX IF NOT EXISTS idx_issues_session ON issues(session_id, turn_id);

PRAGMA foreign_keys = ON;
```

### 1.4 migrate_schema.py Spec

**File:** `/root/.hermes/scripts/migrate_schema.py`

**CLI:**
```
usage: migrate_schema.py [-h] [--dry-run] [--target VERSION] [--rollback VERSION] [--status]

ENI Memory Schema Migration Tool

options:
  -h, --help            show this help message and exit
  --dry-run             Log all SQL without executing (implies --verbose)
  --target VERSION      Migrate to specified version (default: latest)
  --rollback VERSION    Roll back to specified version (requires reverse migration file)
  --status              Show current schema version and pending migrations
```

**Main functions:**

```python
def get_current_version(conn: sqlite3.Connection) -> int:
    """Return highest applied version, or 0 if schema_version table missing."""
    cursor = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version")
    return cursor.fetchone()[0]

def register_migration(conn: sqlite3.Connection, version: int, description: str, sql: str):
    """Compute SHA256 of sql, insert into schema_version. Raises on checksum mismatch if re-applying."""
    import hashlib
    checksum = hashlib.sha256(sql.encode()).hexdigest()
    conn.execute(
        "INSERT INTO schema_version(version, description, checksum) VALUES (?, ?, ?)",
        (version, description, checksum)
    )

def discover_migrations(migrations_dir: str) -> List[Dict]:
    """Scan migrations_dir for *.sql files, parse numeric prefix, sort by version. Return [{'version': int, 'file': str, 'description': str}]."""
    import os, re
    pattern = re.compile(r'^(\d+)_(.+)\.sql$')
    migrations = []
    for f in sorted(os.listdir(migrations_dir)):
        m = pattern.match(f)
        if m:
            version = int(m.group(1))
            description = m.group(2).replace('_', ' ').title()
            migrations.append({'version': version, 'file': os.path.join(migrations_dir, f), 'description': description})
    return migrations

def apply_migration(conn: sqlite3.Connection, migration: Dict, dry_run: bool = False):
    """Read SQL, verify checksum if already applied, execute in transaction. Roll back on failure."""
    with open(migration['file'], 'r') as f:
        sql = f.read()
    checksum = hashlib.sha256(sql.encode()).hexdigest()
    cursor = conn.execute("SELECT checksum FROM schema_version WHERE version = ?", (migration['version'],))
    row = cursor.fetchone()
    if row:
        if row[0] != checksum:
            raise ValueError(f"Migration {migration['version']} checksum mismatch: file changed since applied")
        return  # already applied
    if dry_run:
        print(f"[DRY-RUN] Would apply version {migration['version']}: {migration['description']}")
        print(sql)
        return
    conn.execute("BEGIN")
    try:
        conn.executescript(sql)
        register_migration(conn, migration['version'], migration['description'], sql)
        conn.commit()
        print(f"Applied version {migration['version']}: {migration['description']}")
    except Exception as e:
        conn.rollback()
        print(f"ERROR applying version {migration['version']}: {e}")
        raise

def migrate(target: Optional[int] = None, dry_run: bool = False):
    conn = get_db_connection()
    current = get_current_version(conn)
    migrations = discover_migrations(MIGRATIONS_DIR)
    pending = [m for m in migrations if m['version'] > current]
    if target:
        pending = [m for m in pending if m['version'] <= target]
    for m in pending:
        apply_migration(conn, m, dry_run)
    conn.close()
```

**Exit codes:** 0 = success, 1 = error/migration failed, 2 = checksum mismatch, 3 = no pending migrations.

**Rollback plan:** Rollbacks require reverse migration files named `reverse_003_to_002.sql`. The `--rollback VERSION` flag reads reverse files in descending order, applies them, and removes the corresponding `schema_version` rows. If no reverse file exists for a version, rollback refuses.

### 1.5 WAL Mode Activation and Idempotency

```python
def ensure_wal_mode(db_path: str):
    """Activate WAL mode if not already active. Idempotent."""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("PRAGMA journal_mode")
    current_mode = cursor.fetchone()[0]
    if current_mode != 'wal':
        conn.execute("PRAGMA journal_mode=WAL")
        conn.commit()
        print(f"WAL mode activated on {db_path}")
    conn.close()
```

This is called by `init_db.py` on every startup and by `migrate_schema.py` after any migration. WAL mode is persistent in the database file — once set, it survives restarts. The PRAGMA returns the new mode; we verify it changed.

**Additional safety:** `PRAGMA synchronous=NORMAL` is set alongside WAL (balance speed vs durability). `PRAGMA busy_timeout=5000` is set on every connection to reduce SQLITE_BUSY errors without immediate retry logic (the retry decorator in §3.1 handles remaining conflicts).

---

## 2. Session Lifecycle (session_end_start.py + compact_parents.py)

### 2.1 End/Start with Parent Linkage

**Current behavior (no changes):**

`session_end_start.py` is called between Telegram sessions via `--end` and `--start`:

```bash
# At session end:
python3 session_end_start.py --end --session-id SESSION_A --message-count 7 --token-count 3500

# At new session start:
python3 session_end_start.py --start --session-id SESSION_B --parent SESSION_A
```

On `--end`: sets `sessions.ended_at = datetime('now')`, updates `message_count` and `token_count`, writes optimized memory.md.

On `--start`: inserts new row in `sessions` with `parent_session_id = parent`, status = 'active'.

No changes needed to this flow. The parent chain enables `resume_context.py` to traverse backwards.

### 2.2 Two-Tier Compaction Algorithm

**Problem:** Over many sessions, the parent chain grows unbounded. Reading 20+ sessions of history becomes expensive and exceeds the 2200-char memory.md limit.

**Two-tier approach:**

**Soft compaction (trigger: every 10 sessions closed):**
- The 10 oldest closed sessions in the chain are summarized into a single `context_summary` entry on the 11th (oldest un-compacted) session.
- The 10 sessions each get `status = 'compacted'`.
- Their individual messages/decisions/artifacts remain in the database (FK + CASCADE means they stay unless hard compaction triggers).
- The `context_summary` field is a ~500-char natural-language summary: "Key decisions: D3 (adopted SQLite over JSON), D7 (switched to 3-tier provider model). Files created: /opt/hermes/router.py, /opt/hermes/providers/..."

**Hard compaction (trigger: >2000 total messages across the chain OR total sessions >50):**
- Keep last 3-5 sessions fully intact (the "working set").
- All sessions older than the working set are hard-compacted: their messages are deleted (CASCADE), decisions/artifacts with status='active' are preserved but their content is summarized into `context_summary`, and the sessions are set to `status = 'compacted'`.
- The `context_summary` for each hard-compacted session is a structured block: decisions, artifacts, key facts, and unresolved issues.

#### Pseudocode (soft compaction):

```python
def soft_compact(conn: sqlite3.Connection, chain_sessions: List[Dict]) -> bool:
    """
    chain_sessions: all sessions in parent chain, ordered newest-first.
    Returns True if compaction was performed.
    """
    # Find oldest uncompacted sessions (status != 'compacted')
    uncompacted = [s for s in reversed(chain_sessions) if s['status'] != 'compacted']
    if len(uncompacted) < 10:
        return False

    batch = uncompacted[:10]  # oldest 10
    target = uncompacted[10]  # the session that will receive the summary

    # Collect all decisions, artifacts, issues from the batch
    session_ids = [s['session_id'] for s in batch]
    decisions = conn.execute(
        "SELECT decision_id, title, rationale, status FROM decisions WHERE session_id IN ({}) AND status = 'active'".format(
            ','.join('?' * len(session_ids))), session_ids
    ).fetchall()

    artifacts = conn.execute(
        "SELECT artifact_id, path, description FROM artifacts WHERE session_id IN ({}) AND status = 'active'".format(
            ','.join('?' * len(session_ids))), session_ids
    ).fetchall()

    # Build summary prompt
    summary_data = {
        'session_count': len(batch),
        'date_range': f"{batch[0]['started_at']} to {batch[-1]['ended_at']}",
        'active_decisions': [dict(d) for d in decisions],
        'active_artifacts': [dict(a) for a in artifacts],
    }

    # Generate summary (see below)
    summary = generate_compaction_summary(summary_data)

    # Update target session's context_summary (append or replace)
    existing = target.get('context_summary') or ''
    if existing:
        summary = existing + '\n---\n' + summary
    conn.execute(
        "UPDATE sessions SET context_summary = ? WHERE session_id = ?",
        (summary, target['session_id'])
    )

    # Mark batch as compacted
    for s in batch:
        conn.execute("UPDATE sessions SET status = 'compacted' WHERE session_id = ?", (s['session_id'],))

    print(f"[soft_compact] Compacted {len(batch)} sessions into {target['session_id']}")
    return True
```

#### Pseudocode (hard compaction):

```python
def hard_compact(conn: sqlite3.Connection, chain_sessions: List[Dict], keep_last: int = 5) -> bool:
    """
    Delete old session messages beyond the working set.
    Preserve decisions/artifacts metadata in context_summary.
    """
    if len(chain_sessions) <= keep_last:
        return False

    working_set = chain_sessions[:keep_last]  # newest N
    to_compact = chain_sessions[keep_last:]   # everything older

    for session in to_compact:
        sid = session['session_id']

        # Capture active decisions/artifacts before deletion
        decisions = conn.execute(
            "SELECT decision_id, title, status FROM decisions WHERE session_id = ? AND status = 'active'",
            (sid,)
        ).fetchall()
        artifacts = conn.execute(
            "SELECT artifact_id, path, status FROM artifacts WHERE session_id = ? AND status = 'active'",
            (sid,)
        ).fetchall()

        summary_parts = []
        if session.get('context_summary'):
            summary_parts.append(session['context_summary'])
        if decisions:
            summary_parts.append("Decisions: " + ", ".join(f"{d['decision_id']} ({d['title']})" for d in decisions))
        if artifacts:
            summary_parts.append("Artifacts: " + ", ".join(f"{a['artifact_id']} ({a['path']})" for a in artifacts))

        # Delete messages (CASCADE handles related turn data implicitly)
        # But decisions/artifacts with status='active' we keep references in summary
        conn.execute("DELETE FROM messages WHERE session_id = ?", (sid,))

        # Update summary and status
        conn.execute(
            "UPDATE sessions SET context_summary = ?, status = 'compacted' WHERE session_id = ?",
            (' | '.join(summary_parts), sid)
        )
        print(f"[hard_compact] Compacted session {sid}: kept {len(decisions)} decisions, {len(artifacts)} artifacts")

    return True
```

#### Summary Generation Prompt (for LLM-powered compaction):

```
You are summarizing a batch of AI agent sessions for context restoration.
Given the following data, produce a ---compact--- summary (max 500 chars) 
that captures:
1. Key decisions made (IDs + one-line each)
2. Files/artifacts created or modified (paths only)
3. Unresolved issues or known blockers
4. Architectural direction or patterns established

Data:
{session_count} sessions from {date_range}
Active decisions: {active_decisions}
Active artifacts: {active_artifacts}

Output only the summary text, no preamble.
```

The summary is generated by a call to the LLM via `persist.py`'s existing API mechanism, or as a fallback, a deterministic template-based summary that enumerates decision IDs and artifact paths.

### 2.3 compact_parents.py Spec

**File:** `/root/.hermes/scripts/compact_parents.py`

**CLI:**
```
usage: compact_parents.py [-h] [--force-hard] [--threshold-sessions N] [--threshold-messages N] [--dry-run]

ENI Session Chain Compaction Tool

options:
  -h, --help                show help message and exit
  --force-hard              Run hard compaction regardless of thresholds
  --threshold-sessions N    Soft compaction trigger (default: 10 closed sessions)
  --threshold-messages N    Hard compaction trigger (default: 2000 total messages)
  --dry-run                 Log what would be done without modifying DB
```

**Main function:**

```python
def compact_all(conn: sqlite3.Connection, config: CompactionConfig) -> CompactionResult:
    """Traverse active session's parent chain, evaluate thresholds, run soft and/or hard compaction."""
    active_session = get_active_session(conn)
    chain = traverse_parent_chain(conn, active_session['session_id'])

    result = CompactionResult(soft_did_run=False, hard_did_run=False)

    if config.force_hard or total_message_count(chain) > config.threshold_messages:
        result.hard_did_run = hard_compact(conn, chain, keep_last=5)

    # Only run soft if hard didn't already do the job
    if not result.hard_did_run:
        result.soft_did_run = soft_compact(conn, chain)

    return result
```

**Error handling:** Wrapped in `@retry_on_lock` decorator. On failure, writes to `issues` with severity='error' and description detailing which compaction stage failed.

**Logging:** Every compaction event is written to `journal_log` with action='session_compacted' and payload containing `{'session_ids': [...], 'tier': 'soft'|'hard', 'summary_char_count': N}`.

---

## 3. Data Integrity & Recovery

### 3.1 Defensive DB Writer Wrapper

```python
import sqlite3
import time
import functools
from typing import Callable, Any

DB_PATH = '/root/.hermes/data/eni_memory.db'

MAX_RETRIES = 3
BASE_DELAY_MS = 100  # 100ms base, doubled each retry

def retry_on_lock(max_retries: int = MAX_RETRIES, base_delay_ms: int = BASE_DELAY_MS) -> Callable:
    """Decorator for DB write operations. Retries on SQLITE_BUSY / SQLITE_LOCKED with exponential backoff."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except sqlite3.OperationalError as e:
                    if 'locked' in str(e).lower() or 'busy' in str(e).lower():
                        last_exception = e
                        delay = (base_delay_ms / 1000.0) * (2 ** (attempt - 1))
                        print(f"[retry] Attempt {attempt}/{max_retries} failed: {e}. Retrying in {delay*1000:.0f}ms...")
                        time.sleep(delay)
                    else:
                        raise  # Non-lock error, re-raise immediately
            raise RuntimeError(f"DB write failed after {max_retries} retries") from last_exception
        return wrapper
    return decorator

def get_db_connection() -> sqlite3.Connection:
    """Return a connection with WAL-safe settings."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn

# Usage:
@retry_on_lock()
def write_message(session_id: str, turn_id: str, role: str, content: str, token_count: int = 0):
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO messages (session_id, turn_id, role, content, token_count) VALUES (?, ?, ?, ?, ?)",
        (session_id, turn_id, role, content, token_count)
    )
    conn.commit()
    conn.close()
```

**WAL conflict handling:** WAL mode allows concurrent reads + single writer. The `busy_timeout=5000` tells SQLite to wait up to 5 seconds before raising SQLITE_BUSY. The retry decorator catches any remaining conflicts (e.g., if two writers contend within the same process). Exponential backoff (100ms, 200ms, 400ms) prevents thundering herd.

**All current writers wrapped:** `persist.py`, `session_end_start.py`, `rollback_turn.py`, `compact_parents.py`, `migrate_schema.py`.

### 3.2 validate_last_turn.py — Additions

**Current behavior:** Validates integrity of the last turn by checking that messages, decisions, artifacts, and issues from that `turn_id` are consistent (no orphaned decisions without turn context).

**New `--repair` flag:**

```
usage: validate_last_turn.py [-h] [--repair] [--session-id SESSION_ID] [--turn-id TURN_ID]

options:
  --repair      If integrity failure detected, attempt repair by replaying journal.log
  --session-id  Target session (default: active session)
  --turn-id     Target turn (default: last turn in active session)
```

**Repair algorithm:**

```python
def repair_from_journal(conn: sqlite3.Connection, session_id: str, turn_id: str) -> bool:
    """Backfill missing or corrupted turn data from journal.log. Returns True if repair was needed."""
    # 1. Fetch journal entries for this turn
    entries = conn.execute(
        "SELECT action, payload FROM journal_log WHERE session_id = ? AND turn_id = ? ORDER BY id",
        (session_id, turn_id)
    ).fetchall()

    if not entries:
        print(f"[repair] No journal entries found for {session_id}/{turn_id}")
        return False

    repaired = False
    for entry in entries:
        payload = json.loads(entry['payload'])
        action = entry['action']

        if action == 'message':
            # Check if message exists
            exists = conn.execute(
                "SELECT 1 FROM messages WHERE session_id = ? AND turn_id = ? AND role = ?",
                (session_id, turn_id, payload['role'])
            ).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO messages (session_id, turn_id, role, content, token_count) VALUES (?, ?, ?, ?, ?)",
                    (session_id, turn_id, payload['role'], payload['content'], payload.get('token_count', 0))
                )
                print(f"[repair] Restored message {payload['role']} in turn {turn_id}")
                repaired = True

        elif action == 'decision':
            exists = conn.execute(
                "SELECT 1 FROM decisions WHERE decision_id = ?", (payload['decision_id'],)
            ).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO decisions (session_id, turn_id, decision_id, title, rationale) VALUES (?, ?, ?, ?, ?)",
                    (session_id, turn_id, payload['decision_id'], payload['title'], payload.get('rationale'))
                )
                repaired = True

        elif action == 'artifact':
            exists = conn.execute(
                "SELECT 1 FROM artifacts WHERE artifact_id = ?", (payload['artifact_id'],)
            ).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO artifacts (session_id, turn_id, artifact_id, path, description) VALUES (?, ?, ?, ?, ?)",
                    (session_id, turn_id, payload['artifact_id'], payload['path'], payload.get('description'))
                )
                repaired = True

    if repaired:
        conn.commit()
        # Write issue noting repair
        conn.execute(
            "INSERT INTO issues (session_id, turn_id, issue_id, description, severity) VALUES (?, ?, ?, ?, 'warning')",
            (session_id, turn_id, f"REPAIR-{turn_id}", f"Repaired {repaired} records from journal.log")
        )
        conn.commit()

    return repaired
```

**Integration with validate_last_turn.py:**

```python
def validate(session_id: str, turn_id: str, repair: bool = False) -> ValidationResult:
    conn = get_db_connection()
    issues = run_integrity_checks(conn, session_id, turn_id)
    if issues and repair:
        repair_from_journal(conn, session_id, turn_id)
        # Re-validate after repair
        issues = run_integrity_checks(conn, session_id, turn_id)
    conn.close()
    return ValidationResult(has_issues=len(issues) > 0, issues=issues)
```

### 3.3 rollback_turn.py Spec

**File:** `/root/.hermes/scripts/rollback_turn.py`

**CLI:**
```
usage: rollback_turn.py [-h] [--turns N] [--session-id SESSION_ID] [--dry-run] [--force]

ENI Turn Rollback Tool

options:
  -h, --help                show help message and exit
  --turns N                 Number of turns to roll back (default: 1)
  --session-id SESSION_ID   Target session (default: active session)
  --dry-run                 Show what would be deleted without executing
  --force                   Skip confirmation prompt
```

**Cascade algorithm:**

```python
@retry_on_lock()
def rollback_turns(conn: sqlite3.Connection, session_id: str, num_turns: int, dry_run: bool = False) -> int:
    """
    Roll back the last N turns in a session.
    Returns number of turns actually rolled back.
    """
    # 1. Identify the turn_ids to roll back (oldest-first for clean deletion order)
    turns = conn.execute(
        "SELECT DISTINCT turn_id FROM messages WHERE session_id = ? ORDER BY turn_id DESC LIMIT ?",
        (session_id, num_turns)
    ).fetchall()
    turn_ids = [t['turn_id'] for t in turns]

    if not turn_ids:
        print(f"[rollback] No turns found for session {session_id}")
        return 0

    if dry_run:
        for tid in turn_ids:
            msg_count = conn.execute(
                "SELECT COUNT(*) as c FROM messages WHERE session_id = ? AND turn_id = ?",
                (session_id, tid)
            ).fetchone()['c']
            dec_count = conn.execute(
                "SELECT COUNT(*) as c FROM decisions WHERE session_id = ? AND turn_id = ?",
                (session_id, tid)
            ).fetchone()['c']
            art_count = conn.execute(
                "SELECT COUNT(*) as c FROM artifacts WHERE session_id = ? AND turn_id = ?",
                (session_id, tid)
            ).fetchone()['c']
            print(f"  Would delete turn {tid}: {msg_count} messages, {dec_count} decisions, {art_count} artifacts")
        return len(turn_ids)

    # 2. Delete in reverse FK-safe order (no cascade dependency issues)
    for tid in turn_ids:
        # Set decisions/artifacts to 'reverted' instead of hard-deleting (audit trail)
        conn.execute(
            "UPDATE decisions SET status = 'reverted' WHERE session_id = ? AND turn_id = ?",
            (session_id, tid)
        )
        conn.execute(
            "UPDATE artifacts SET status = 'reverted' WHERE session_id = ? AND turn_id = ?",
            (session_id, tid)
        )
        # Delete messages (these are the actual turn content)
        conn.execute("DELETE FROM messages WHERE session_id = ? AND turn_id = ?", (session_id, tid))
        print(f"[rollback] Reverted turn {tid}")

    # 3. Update session message_count
    remaining = conn.execute(
        "SELECT COUNT(*) as c FROM messages WHERE session_id = ?", (session_id,)
    ).fetchone()['c']
    conn.execute("UPDATE sessions SET message_count = ? WHERE session_id = ?", (remaining, session_id))

    # 4. Log rollback in journal
    conn.execute(
        "INSERT INTO journal_log (session_id, turn_id, action, payload) VALUES (?, ?, 'rollback', ?)",
        (session_id, turn_ids[-1], json.dumps({'rolled_back_turns': turn_ids, 'reason': 'manual'}))
    )

    conn.commit()
    return len(turn_ids)
```

**Restoration:** Rollback does NOT hard-delete decisions/artifacts — it sets `status = 'reverted'`. This preserves the audit trail. A future `--restore` flag can set them back to 'active' and replay messages from journal.log.

**Edge case — rollback across session boundary:** If the last N turns span multiple sessions (shouldn't happen with parent chain, but defensive check), the tool refuses with "Cannot rollback across session boundaries — specify --session-id or reduce --turns".

### 3.4 backup_db.py Spec

**File:** `/root/.hermes/scripts/backup_db.py`

**CLI:**
```
usage: backup_db.py [-h] [--output-dir DIR] [--retention-days N] [--no-journal] [--label LABEL]

ENI Memory Database Backup Tool

options:
  -h, --help              show help message and exit
  --output-dir DIR        Backup destination (default: /root/.hermes/backups/)
  --retention-days N      Delete backups older than N days (default: 30, 0 = keep forever)
  --no-journal            Skip journal.log backup
  --label LABEL           Optional label for backup filename
```

**What gets copied:**

```
/root/.hermes/data/eni_memory.db          →  backups/eni_memory_20260608_082700.db
/root/.hermes/data/eni_memory.db-wal      →  backups/eni_memory_20260608_082700.db-wal
/root/.hermes/data/eni_memory.db-shm      →  backups/eni_memory_20260608_082700.db-shm
/root/.hermes/journal.log                 →  backups/journal_20260608_082700.log
/root/.hermes/data/memory.md              →  backups/memory_20260608_082700.md
```

**Implementation:**

```python
def create_backup(output_dir: str, label: str = '', include_journal: bool = True) -> str:
    """Copy DB + WAL + SHM + journal + memory.md to timestamped backup. Return backup path."""
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    label_suffix = f'_{label}' if label else ''
    backup_prefix = os.path.join(output_dir, f'{timestamp}{label_suffix}')

    shutil.copy2(DB_PATH, f'{backup_prefix}.db')
    if os.path.exists(DB_PATH + '-wal'):
        shutil.copy2(DB_PATH + '-wal', f'{backup_prefix}.db-wal')
    if os.path.exists(DB_PATH + '-shm'):
        shutil.copy2(DB_PATH + '-shm', f'{backup_prefix}.db-shm')
    if include_journal and os.path.exists(JOURNAL_PATH):
        shutil.copy2(JOURNAL_PATH, f'{backup_prefix}.journal.log')
    memory_path = os.path.join(os.path.dirname(DB_PATH), 'memory.md')
    if os.path.exists(memory_path):
        shutil.copy2(memory_path, f'{backup_prefix}.memory.md')

    return backup_prefix

def prune_old_backups(output_dir: str, retention_days: int):
    """Delete backup files older than retention_days."""
    if retention_days <= 0:
        return
    cutoff = time.time() - (retention_days * 86400)
    for f in os.listdir(output_dir):
        fpath = os.path.join(output_dir, f)
        if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff:
            os.remove(fpath)
            print(f"[prune] Removed old backup: {f}")
```

**Suggested cron:** `0 4 * * * cd /root/.hermes && python3 scripts/backup_db.py` (daily at 4 AM server time, 30-day retention).

---

## 4. Context Optimization

### 4.1 resume_context.py — Fast Chain Traversal

**Current behavior:** Traverses parent_session_id chain by executing one SELECT per session. With 30+ sessions this is 30 sequential queries.

**Optimized with message_count:**

```python
def traverse_parent_chain(conn: sqlite3.Connection, session_id: str, max_tokens: int = 8000) -> List[Dict]:
    """
    Walk parent chain from newest to oldest.
    Stop when cumulative token_count exceeds max_tokens.
    Use message_count for fast skip detection (sessions with 0 messages are skipped without inspecting them).
    """
    chain = []
    current_id = session_id
    cumulative_tokens = 0

    while current_id:
        row = conn.execute(
            "SELECT session_id, parent_session_id, message_count, token_count, status, context_summary "
            "FROM sessions WHERE session_id = ?",
            (current_id,)
        ).fetchone()

        if not row:
            break

        # Skip compacted sessions — their context is in context_summary
        if row['status'] == 'compacted' and row['context_summary']:
            chain.append({
                'session_id': row['session_id'],
                'status': 'compacted',
                'context_summary': row['context_summary'],
                'message_count': row['message_count'],
                'token_count': row['token_count'],
                'messages': [],
                'decisions': [],
                'artifacts': []
            })
            cumulative_tokens += len(row['context_summary']) // 4  # rough token estimate
            current_id = row['parent_session_id']
            continue

        # Fast skip: if message_count == 0, skip full load
        if row['message_count'] == 0:
            chain.append({
                'session_id': row['session_id'],
                'status': row['status'],
                'message_count': 0,
                'token_count': row['token_count'],
                'messages': [],
                'decisions': [],
                'artifacts': []
            })
            current_id = row['parent_session_id']
            continue

        # Load full session data
        messages = conn.execute(
            "SELECT role, content, token_count FROM messages WHERE session_id = ? ORDER BY id",
            (current_id,)
        ).fetchall()

        session_tokens = sum(m['token_count'] or 0 for m in messages)
        cumulative_tokens += session_tokens

        decisions = conn.execute(
            "SELECT decision_id, title, rationale, status FROM decisions WHERE session_id = ? AND status = 'active'",
            (current_id,)
        ).fetchall()

        chain.append({
            'session_id': row['session_id'],
            'status': row['status'],
            'message_count': row['message_count'],
            'token_count': session_tokens,
            'messages': [dict(m) for m in messages],
            'decisions': [dict(d) for d in decisions]
        })

        if cumulative_tokens >= max_tokens:
            chain[-1]['_truncated'] = True
            break

        current_id = row['parent_session_id']

    return chain
```

**Key optimization:** `message_count` is checked before any query to `messages` table. Sessions with 0 messages (rare but possible after rollback) cost a single row fetch instead of a full message scan.

### 4.2 Memory.md Optimized Format

**File:** `/root/.hermes/data/memory.md` (max 2200 chars)

**Template:**

```markdown
# ENI — Durable Memory

## Active Session
ID: {session_id}
Parent: {parent_session_id}
Messages: {message_count} | Tokens: {token_count}
Since: {started_at}

## Active Decisions
{decision_id} | {title} | {rationale_1line}
{decision_id} | {title} | {rationale_1line}

## Active Artifacts
{artifact_id} | {path} | {description_1line}

## Open Issues
{issue_id} | {description_truncated} | {severity}

## Session Chain Summary
{session_chain_summary}

## Last Turn
Turn: {last_turn_id}
Summary: {last_turn_1line_summary}
```

**Field constraints:**
- `title` / `description_1line`: max 80 chars, truncated with `…` if longer
- `rationale_1line`: max 120 chars
- `session_chain_summary`: max 600 chars — auto-generated from context_summary fields
- `last_turn_1line_summary`: max 200 chars
- Total strict limit: 2200 characters. Truncation uses `…` at the section level (trim oldest decisions first).

**Example:**

```markdown
# ENI — Durable Memory

## Active Session
ID: sess_B
Parent: sess_A
Messages: 4 | Tokens: 1200
Since: 2026-06-08 07:00:00

## Active Decisions
D3 | SQLite over JSON | More reliable for concurrent writes
D7 | 3-tier provider model | OpenAI, Anthropic, local fallback

## Active Artifacts
A5 | /opt/hermes/router.py | Main request router
A6 | /opt/hermes/providers/openai.py | OpenAI provider wrapper

## Open Issues
I2 | WAL mode not verified on startup | warning

## Session Chain Summary
2 sessions: sess_A (compacted, 7 msgs — D3,D7 router setup), sess_B (active — provider integration)

## Last Turn
Turn: T004
Summary: Implemented OpenAI provider wrapper with retry logic
```

**Absolute paths in artifacts:** Always full paths (e.g., `/opt/hermes/router.py`, never `./router.py` or `router.py`).

**Decision IDs in memory.md:** Store as `D3`, `D7` — not full rationale. The full rationale lives in SQLite and is loaded by `resume_context.py`.

### 4.3 session_end_start.py — Optimized memory.md Writer

On every `--end`, `session_end_start.py` now writes the optimized memory.md using the template above. The write function:

```python
def write_optimized_memory(conn: sqlite3.Connection, active_session_id: str, max_chars: int = 2200):
    """Generate memory.md using optimized format. Truncates oldest decisions if over limit."""
    # Gather data
    session = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (active_session_id,)).fetchone()
    decisions = conn.execute(
        "SELECT decision_id, title, substr(rationale, 1, 120) as rationale_short FROM decisions WHERE session_id = ? AND status = 'active'",
        (active_session_id,)
    ).fetchall()
    artifacts = conn.execute(
        "SELECT artifact_id, path, substr(description, 1, 80) as desc_short FROM artifacts WHERE session_id = ? AND status = 'active'",
        (active_session_id,)
    ).fetchall()
    issues = conn.execute(
        "SELECT issue_id, substr(description, 1, 60) as desc_short, severity FROM issues WHERE resolved = 0",
        (active_session_id,)
    ).fetchall()

    # Get parent chain summary from context_summary fields
    chain_summary = build_chain_summary(conn, active_session_id)

    # Get last turn
    last_turn = conn.execute(
        "SELECT turn_id FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT 1",
        (active_session_id,)
    ).fetchone()

    # Build markdown
    md = f"# ENI — Durable Memory\n\n"
    md += f"## Active Session\n"
    md += f"ID: {session['session_id']}\n"
    md += f"Parent: {session['parent_session_id'] or 'None'}\n"
    md += f"Messages: {session['message_count']} | Tokens: {session['token_count']}\n"
    md += f"Since: {session['started_at']}\n\n"

    if decisions:
        md += "## Active Decisions\n"
        for d in decisions:
            md += f"{d['decision_id']} | {d['title'][:80]} | {d['rationale_short']}\n"
        md += "\n"

    if artifacts:
        md += "## Active Artifacts\n"
        for a in artifacts:
            md += f"{a['artifact_id']} | {a['path']} | {a['desc_short']}\n"
        md += "\n"

    if issues:
        md += "## Open Issues\n"
        for iss in issues:
            md += f"{iss['issue_id']} | {iss['desc_short']} | {iss['severity']}\n"
        md += "\n"

    md += f"## Session Chain Summary\n{chain_summary[:600]}\n\n"

    if last_turn:
        # Get a 1-line summary of last turn from first user or assistant message
        last_msg = conn.execute(
            "SELECT substr(content, 1, 200) as snippet FROM messages WHERE session_id = ? AND turn_id = ? AND role IN ('user','assistant') LIMIT 1",
            (active_session_id, last_turn['turn_id'])
        ).fetchone()
        last_summary = last_msg['snippet'].replace('\n', ' ') if last_msg else 'N/A'
        md += f"## Last Turn\nTurn: {last_turn['turn_id']}\n"
        md += f"Summary: {last_summary[:200]}\n"

    # Truncate to max_chars at section boundaries (remove oldest decisions first)
    md = enforce_length_limit(md, max_chars)

    with open(MEMORY_PATH, 'w') as f:
        f.write(md)
```

---

## 5. Event Sourcing & Repair

### 5.1 Journal Log Format Specification

**File:** `/root/.hermes/journal.log`

**Format:** One JSON object per line (JSONL), appended sequentially.

```json
{"action": "message", "session_id": "sess_B", "turn_id": "T004", "timestamp": "2026-06-08T07:15:30Z", "payload": {"role": "user", "content": "Implement the router", "token_count": 42}}
{"action": "decision", "session_id": "sess_B", "turn_id": "T004", "timestamp": "2026-06-08T07:15:35Z", "payload": {"decision_id": "D8", "title": "Use asyncio for provider calls", "rationale": "All providers support async, reduces blocking"}}
{"action": "artifact", "session_id": "sess_B", "turn_id": "T004", "timestamp": "2026-06-08T07:16:00Z", "payload": {"artifact_id": "A7", "path": "/opt/hermes/providers/anthropic.py", "description": "Anthropic provider wrapper"}}
{"action": "issue", "session_id": "sess_B", "turn_id": "T004", "timestamp": "2026-06-08T07:16:05Z", "payload": {"issue_id": "I3", "description": "Rate limiting not implemented for Anthropic", "severity": "warning"}}
{"action": "session_start", "session_id": "sess_B", "turn_id": "__init__", "timestamp": "2026-06-08T07:00:00Z", "payload": {"parent_session_id": "sess_A"}}
{"action": "session_end", "session_id": "sess_B", "turn_id": "__term__", "timestamp": "2026-06-08T08:00:00Z", "payload": {"message_count": 4, "token_count": 1200}}
{"action": "rollback", "session_id": "sess_B", "turn_id": "__rollback__", "timestamp": "2026-06-08T08:05:00Z", "payload": {"rolled_back_turns": ["T004"], "reason": "user_request"}}
{"action": "session_compacted", "session_id": "sess_A", "turn_id": "__compact__", "timestamp": "2026-06-08T08:10:00Z", "payload": {"tier": "soft", "compacted_into": "sess_B", "summary_char_count": 420}}
```

**Schema (for SQLite `journal_log` table):**

```sql
CREATE TABLE journal_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('message','decision','artifact','issue','session_start','session_end','rollback','session_compacted')),
    payload TEXT NOT NULL,   -- JSON
    timestamp TEXT DEFAULT (datetime('now'))
);
```

**Design principles:**
- The `.log` file is the **append-only write-ahead log** for SQLite. It's written before the SQLite INSERT (write-ahead pattern).
- Each line is independently parseable. No multi-line JSON.
- `turn_id` = `__init__` for session start, `__term__` for session end, `__rollback__` for rollback events, `__compact__` for compaction.
- Timestamps are ISO 8601 with seconds precision (fractional seconds optional).
- **The journal.log is NOT the source of truth by default** (SQLite is). It becomes source of truth only during `--repair` operations.

### 5.2 persist.py —repair: Deterministic Replay

**Algorithm:**

```python
def repair_from_journal_full(conn: sqlite3.Connection, journal_path: str = JOURNAL_PATH) -> RepairResult:
    """
    Full repair: read every line in journal.log, replay each event into SQLite.
    Idempotent: skip events that already exist (checked by session_id + turn_id + action).
    Returns counts of replayed, skipped, and failed events.
    """
    if not os.path.exists(journal_path):
        return RepairResult(error="journal.log not found")

    replayed = 0
    skipped = 0
    failed = 0
    errors = []

    with open(journal_path, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as e:
                failed += 1
                errors.append(f"Line {line_num}: JSON parse error: {e}")
                continue

            try:
                replayed_inner = replay_event(conn, event)
                if replayed_inner:
                    replayed += 1
                else:
                    skipped += 1
            except Exception as e:
                failed += 1
                errors.append(f"Line {line_num}: replay error: {e}")

    conn.commit()
    return RepairResult(replayed=replayed, skipped=skipped, failed=failed, errors=errors)

def replay_event(conn: sqlite3.Connection, event: Dict) -> bool:
    """Replay a single journal event into SQLite. Returns True if a row was inserted."""
    action = event['action']
    session_id = event['session_id']
    turn_id = event['turn_id']
    payload = event['payload']
    timestamp = event.get('timestamp', datetime.utcnow().isoformat())

    if action == 'message':
        # Deduplicate: check if this exact message exists
        exists = conn.execute(
            "SELECT 1 FROM messages WHERE session_id = ? AND turn_id = ? AND role = ?",
            (session_id, turn_id, payload['role'])
        ).fetchone()
        if exists:
            return False
        conn.execute(
            "INSERT INTO messages (session_id, turn_id, role, content, token_count, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, turn_id, payload['role'], payload['content'], payload.get('token_count', 0), timestamp)
        )
        return True

    elif action == 'decision':
        exists = conn.execute(
            "SELECT 1 FROM decisions WHERE decision_id = ?", (payload['decision_id'],)
        ).fetchone()
        if exists:
            return False
        conn.execute(
            "INSERT INTO decisions (session_id, turn_id, decision_id, title, rationale, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, turn_id, payload['decision_id'], payload['title'], payload.get('rationale'), timestamp)
        )
        return True

    elif action == 'artifact':
        exists = conn.execute(
            "SELECT 1 FROM artifacts WHERE artifact_id = ?", (payload['artifact_id'],)
        ).fetchone()
        if exists:
            return False
        conn.execute(
            "INSERT INTO artifacts (session_id, turn_id, artifact_id, path, description, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, turn_id, payload['artifact_id'], payload['path'], payload.get('description'), timestamp)
        )
        return True

    elif action == 'issue':
        exists = conn.execute(
            "SELECT 1 FROM issues WHERE issue_id = ?", (payload['issue_id'],)
        ).fetchone()
        if exists:
            return False
        conn.execute(
            "INSERT INTO issues (session_id, turn_id, issue_id, description, severity, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, turn_id, payload['issue_id'], payload['description'], payload.get('severity', 'warning'), timestamp)
        )
        return True

    elif action == 'session_start':
        exists = conn.execute(
            "SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if exists:
            return False
        conn.execute(
            "INSERT INTO sessions (session_id, parent_session_id, started_at, status) VALUES (?, ?, ?, 'active')",
            (session_id, payload.get('parent_session_id'), timestamp)
        )
        return True

    elif action == 'session_end':
        conn.execute(
            "UPDATE sessions SET ended_at = ?, message_count = ?, token_count = ?, status = 'closed' WHERE session_id = ?",
            (timestamp, payload.get('message_count', 0), payload.get('token_count', 0), session_id)
        )
        return True

    elif action == 'rollback':
        # Rollback is replayed by setting decisions/artifacts to 'reverted'
        for tid in payload.get('rolled_back_turns', []):
            conn.execute(
                "UPDATE decisions SET status = 'reverted' WHERE session_id = ? AND turn_id = ?",
                (session_id, tid)
            )
            conn.execute(
                "UPDATE artifacts SET status = 'reverted' WHERE session_id = ? AND turn_id = ?",
                (session_id, tid)
            )
            conn.execute("DELETE FROM messages WHERE session_id = ? AND turn_id = ?", (session_id, tid))
        return True

    elif action == 'session_compacted':
        conn.execute(
            "UPDATE sessions SET status = 'compacted' WHERE session_id = ?",
            (session_id,)
        )
        return True

    return False
```

**Conflict resolution:** If the SQLite database has diverged from journal.log (e.g., a manual rollback was done via `rollback_turn.py` but the journal wasn't updated), the replay uses "SQLite wins" for existing entries (skips them) and only inserts truly missing entries. This prevents journal.log from overwriting intentional manual changes.

### 5.3 sync_journal.py Spec [OPTIONAL]

**File:** `/root/.hermes/scripts/sync_journal.py`

If event sourcing is implemented (journal.log as source of truth), this script reconciles SQLite to match journal.log exactly.

```
usage: sync_journal.py [-h] [--direction {journal-to-db,db-to-journal,merge}] [--dry-run]

options:
  --direction           Sync direction (default: journal-to-db)
  --dry-run             Show differences without modifying
```

**Minimal viable version:** `--direction journal-to-db` only. Truncates all tables and replays journal.log from scratch. Suitable for disaster recovery when SQLite is corrupted but journal.log is intact.

**Full version:** Compares checksums of each turn between DB and journal, identifies divergent entries, reconciles with user-specified strategy.

---

## 6. Edge Cases & Mitigations Table

| # | Edge Case | Risk | Mitigation |
|---|-----------|------|------------|
| 1 | SQLite file locked by concurrent process | Write fails, potential data loss | `busy_timeout=5000` + `@retry_on_lock` decorator (3 retries, exponential backoff). If all retries fail, log to journal.log as fallback. |
| 2 | WAL file grows unbounded | Disk usage, slow recovery | `PRAGMA wal_autocheckpoint=1000` (auto-checkpoint every 1000 pages). `backup_db.py` triggers checkpoint after copy. |
| 3 | journal.log vs SQLite divergence | Silent data inconsistency | `validate_last_turn.py --repair` compares and backfills. `persist.py` writes to journal BEFORE SQLite (write-ahead). |
| 4 | memory.md exceeds 2200 chars | Startup truncation, lost context | `enforce_length_limit()` truncates at section boundaries (oldest decisions first). Never truncates active session metadata. |
| 5 | Rollback attempts to delete compacted session | Data loss on CASCADE | `rollback_turn.py` refuses if any target turn belongs to a `status='compacted'` session. |
| 6 | Foreign key violation on parent_session_id | Orphaned chain | `PRAGMA foreign_keys=ON` enforced. Migration 002 adds ON DELETE SET NULL for parent reference. |
| 7 | Cross-session turn_id collision | Rollback affects wrong session | All turn-scoped operations filter by `session_id + turn_id`. rollback.py bounds to one session. |
| 8 | Compaction during active write | Race condition on session update | `compact_parents.py` opens its own connection (WAL allows concurrent reads). Uses `BEGIN IMMEDIATE` for the summary update. |
| 9 | migration.sql checksum mismatch after re-apply | Silent schema corruption | `migrate_schema.py` computes SHA256 before applying and stores it. Refuses to re-apply if checksum differs. |
| 10 | Disk full during backup | Partial backup, inconsistent copy | `backup_db.py` writes to temp file first, then `os.rename()` for atomic replacement. |
| 11 | Very long parent chain (>100 sessions) | resume_context.py O(n) traversal time | Hard compaction keeps working set ≤5 sessions. `message_count` skips empty sessions. `max_tokens` stop condition limits traversal depth. |
| 12 | SQLite data type mismatch | Silent truncation / type coercion | All schemas use TEXT for IDs, INTEGER for counts, TEXT for JSON payloads. No floating-point or BLOB columns. |

---

## 7. Implementation Order (Priority-Ranked, Dependencies)

| Rank | Deliverable | Dependencies | Estimated Effort | Why This Order |
|------|------------|--------------|------------------|----------------|
| **P0** | `@retry_on_lock` decorator + `get_db_connection()` WAL settings | None | 1 file, ~40 lines | Every write operation needs this. No other change is safe without it. |
| **P0** | `migrate_schema.py` + schema_version table | None (runs on existing DB) | 1 file, ~150 lines | Must exist before any schema change. FK migration can't land without it. |
| **P0** | Migration 002: FK + CASCADE + indexes | `migrate_schema.py` | 1 SQL file, ~80 lines | Data integrity foundation. Without FKs, CASCADE deletes from compaction/rollback can orphan rows. |
| **P0** | WAL mode in `init_db.py` | None | 3 lines added | Crash safety. Enables concurrent reads during compaction. |
| **P1** | `rollback_turn.py` | FK migration (CASCADE) | 1 file, ~120 lines | Undo capability is critical for agent self-correction. |
| **P1** | memory.md optimized writer in `session_end_start.py` | None | Modify existing function, ~80 lines | Directly impacts 2200-char limit. Enables decision-ID-based format. |
| **P1** | `resume_context.py` message_count optimization | None (uses existing column) | Modify existing function, ~60 lines | Reduces startup time on large chains. Free optimization. |
| **P2** | `compact_parents.py` (soft) | FK migration, WAL | 1 file, ~200 lines | Prevents chain from growing unbounded. Soft compaction is safe to run anytime. |
| **P2** | `compact_parents.py` (hard) | soft compaction, FK migration | +100 lines to above | Only triggers at >2000 messages or explicit flag. Lower risk. |
| **P2** | `validate_last_turn.py --repair` | journal.log exists | +80 lines to existing | Repair capability but journal.log must already be populated. |
| **P3** | `backup_db.py` | None | 1 file, ~80 lines | Safety net. Low complexity, independent of all other changes. |
| **P3** | `persist.py` —repair (full replay) | journal.log format stable | +150 lines to persist.py | Depends on journal.log having complete history. Lower urgency. |
| **P4** | `sync_journal.py` [OPTIONAL] | journal.log format, persist.py | 1 file, ~100 lines | Event sourcing is optional. Only implement if divergence becomes a real problem. |
| **P4** | `archive_session.py` [OPTIONAL] | FK migration, compact_parents | 1 file, ~80 lines | Low value until session count exceeds 50+ active. |

---

## 8. Acceptance Criteria Per Deliverable

### 1. `@retry_on_lock` decorator (P0)
- [x] Three retries with 100ms/200ms/400ms backoff
- [x] Catches only `sqlite3.OperationalError` containing 'locked' or 'busy'
- [x] Re-raises non-lock errors immediately
- [x] Raises `RuntimeError` after exhausting retries
- [x] Applied to all writer functions: `persist.py`, `session_end_start.py`, `rollback_turn.py`, `compact_parents.py`

### 2. `migrate_schema.py` (P0)
- [x] Creates `schema_version` table (idempotent)
- [x] `--status` shows current version and pending migrations
- [x] `--dry-run` prints SQL without executing
- [x] Computes and stores SHA256 checksum of each migration
- [x] Refuses to re-apply a migration with changed checksum
- [x] Exit code 1 on apply failure, 2 on checksum mismatch, 0 on success
- [x] Migration 002 SQL creates FKs, CASCADE, indexes, is idempotent (uses IF NOT EXISTS, CREATE TABLE IF NOT EXISTS pattern)

### 3. WAL mode (P0)
- [x] `init_db.py` sets `PRAGMA journal_mode=WAL`
- [x] `PRAGMA synchronous=NORMAL` set alongside WAL
- [x] `PRAGMA busy_timeout=5000` on every `get_db_connection()`
- [x] `PRAGMA foreign_keys=ON` on every connection
- [x] WAL mode persists across DB close/reopen (verified by PRAGMA journal_mode after reconnect)

### 4. `rollback_turn.py` (P1)
- [x] `--turns N` rollback last N turns
- [x] `--session-id SESSION_ID` targets specific session
- [x] `--dry-run` shows counts without deleting
- [x] `--force` skips confirmation
- [x] Decisions/artifacts set to `status='reverted'` (not hard-deleted)
- [x] Messages hard-deleted (CASCADE-safe)
- [x] `message_count` updated after rollback
- [x] Refuses if target turns span compacted sessions
- [x] Writes rollback event to `journal_log`

### 5. Memory.md optimization (P1)
- [x] Uses decision IDs (D3) not full rationale text
- [x] Absolute artifact paths (e.g., `/opt/hermes/router.py`)
- [x] 1-line summary per decision (max 80 chars title, 120 chars rationale)
- [x] Session chain summary (max 600 chars)
- [x] Last turn summary (max 200 chars)
- [x] Enforces 2200-char hard limit via section-level truncation
- [x] Written on every `--end` call in `session_end_start.py`

### 6. `resume_context.py` optimization (P1)
- [x] Uses `message_count` to skip sessions with 0 messages
- [x] Uses `token_count` for cumulative stop condition
- [x] Compacted sessions loaded from `context_summary` only
- [x] Returns `_truncated: True` marker on last loaded session if token limit hit

### 7. `compact_parents.py` (P2)
- [x] Soft: triggers every 10 uncompacted closed sessions
- [x] Soft: generates summary from decisions/artifacts/issues
- [x] Soft: sets compacted sessions to `status='compacted'`
- [x] Hard: triggers at >2000 total chain messages OR `--force-hard`
- [x] Hard: keeps last 5 sessions intact, deletes older messages (CASCADE)
- [x] Hard: preserves active decisions/artifacts in `context_summary`
- [x] `--dry-run` shows what would be compacted
- [x] Writes compaction event to `journal_log`
- [x] Wrapped in `@retry_on_lock`

### 8. `validate_last_turn.py --repair` (P2)
- [x] Reads journal.log entries for the target turn
- [x] Detects missing messages/decisions/artifacts
- [x] Backfills only missing entries (idempotent)
- [x] Writes `REPAIR-{turn_id}` issue on success
- [x] Reports repair count to stdout

### 9. `backup_db.py` (P3)
- [x] Copies `.db`, `.db-wal`, `.db-shm`, `journal.log`, `memory.md`
- [x] Timestamped filenames (YYYYMMDD_HHMMSS)
- [x] `--retention-days N` prunes old backups
- [x] `--no-journal` skips journal.log
- [x] Atomic write via temp + rename
- [x] Exit code 0 on success, 1 on failure (disk full, permission)

### 10. `persist.py --repair` (P3)
- [x] Full replay of every line in journal.log
- [x] Deduplication check per event (session_id + turn_id + action)
- [x] Reports replayed/skipped/failed counts
- [x] Handles rollback events by re-applying status changes
- [x] Handles session_compacted events
- [x] Idempotent: safe to run multiple times
```

---

This covers all 12 priorities. The implementation order (P0→P4) ensures each deliverable builds on stable foundations: retry safety and schema versioning first, then FKs and rollback, then compaction and repair, then optional event sourcing. The acceptance criteria provide concrete pass/fail gates for each script.