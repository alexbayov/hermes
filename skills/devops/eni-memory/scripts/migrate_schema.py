"""Idempotent schema migrations with versioning and backup-first safety."""
import os
import sys
import argparse
import shutil
import sqlite3
from datetime import datetime
from db_utils import DB_PATH, get_conn, tx, integrity_check

BACKUP_DIR = "/root/.hermes/data/backup"

MIGRATIONS = {
    2: """
        ALTER TABLE sessions ADD COLUMN status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'closed', 'compacted', 'archived'));
        ALTER TABLE sessions ADD COLUMN message_count INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE sessions ADD COLUMN context_summary TEXT;
        ALTER TABLE messages ADD COLUMN token_count INTEGER;
        ALTER TABLE messages ADD COLUMN tool_name TEXT;
        ALTER TABLE messages ADD COLUMN tool_result TEXT;
    """,
    3: """
        CREATE TABLE IF NOT EXISTS op_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            turn_id INTEGER NOT NULL,
            op TEXT NOT NULL CHECK (op IN ('insert', 'update', 'delete')),
            table_name TEXT NOT NULL,
            row_id INTEGER,
            old_value TEXT,
            new_value TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_op_log_session ON op_log(session_id, turn_id);
        CREATE INDEX IF NOT EXISTS idx_op_log_table ON op_log(table_name, row_id);
        CREATE TABLE IF NOT EXISTS compaction_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL DEFAULT (datetime('now')),
            ended_at TEXT,
            sessions_compacted INTEGER NOT NULL DEFAULT 0,
            messages_archived INTEGER NOT NULL DEFAULT 0,
            messages_kept INTEGER NOT NULL DEFAULT 0,
            archive_path TEXT,
            status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'success', 'failed')),
            error TEXT
        );
    """,
    4: """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_decisions_unique ON decisions(session_id, turn_id, title);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_artifacts_unique ON artifacts(session_id, turn_id, name);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_issues_unique ON issues(session_id, turn_id, title);
    """,
    5: """
        CREATE TABLE IF NOT EXISTS retention_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL DEFAULT (datetime('now')),
            ended_at TEXT,
            db_size_mb REAL,
            wal_size_mb REAL,
            op_log_rows_before INTEGER,
            op_log_rows_deleted INTEGER,
            journal_bytes_before INTEGER,
            journal_rotations INTEGER,
            backups_deleted INTEGER,
            sessions_purged INTEGER,
            status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'success', 'failed')),
            error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_messages_session_turn ON messages(session_id, turn_id);
        CREATE INDEX IF NOT EXISTS idx_decisions_session_active ON decisions(session_id, active);
        CREATE INDEX IF NOT EXISTS idx_artifacts_session_status ON artifacts(session_id, status);
        CREATE INDEX IF NOT EXISTS idx_oplog_created ON op_log(created_at);
    """,
}


def _backup_first():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    dst = os.path.join(BACKUP_DIR, f"eni_memory_{ts}.db")
    # Use separate connection (VACUUM INTO cannot run inside a transaction)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(f"VACUUM INTO '{dst}';")
    conn.close()
    print(f"Pre-migration backup: {dst}")
    return dst


def _run_migration(version: int, sql: str):
    conn = get_conn()
    for stmt in sql.strip().split(";"):
        stmt = stmt.strip()
        if not stmt or stmt.startswith("--"):
            continue
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e) or "already exists" in str(e):
                print(f"  [skip] {stmt[:60]}... — already applied")
            else:
                raise
    conn.execute(
        "INSERT OR REPLACE INTO schema_version (id, version, applied_at) VALUES (1, ?, datetime('now'))",
        (version,),
    )
    print(f"Migration v{version} applied")


def migrate(target: int = None, backup_first: bool = True):
    conn = get_conn()
    row = conn.execute("SELECT version FROM schema_version WHERE id = 1").fetchone()
    current = row[0] if row else 0
    target = target or (max(MIGRATIONS.keys()) + 1)

    print(f"Current schema version: {current}, target: {target}")

    if current >= target:
        print("No migrations needed")
        return

    if backup_first:
        _backup_first()

    if not integrity_check():
        print("ERROR: integrity_check failed, aborting", file=sys.stderr)
        sys.exit(1)

    for v in sorted(MIGRATIONS.keys()):
        if v > current and v <= target:
            print(f"Applying migration v{v}...")
            _run_migration(v, MIGRATIONS[v])

    # Post-migration integrity check
    if not integrity_check():
        print("ERROR: integrity_check failed after migration", file=sys.stderr)
        sys.exit(1)

    print("Migrations complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, help="Target schema version (default: latest)")
    parser.add_argument("--no-backup", action="store_true", help="Skip pre-migration backup")
    args = parser.parse_args()
    migrate(target=args.target, backup_first=not args.no_backup)
