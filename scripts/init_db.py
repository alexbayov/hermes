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
