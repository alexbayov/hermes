#!/usr/bin/env python3
"""Deterministic fault-injection test for crash recovery via journal.log replay.

Simulates a crash by writing turns to journal.log but NOT to the DB,
then runs validate_and_repair.py and asserts full recovery.

Based on Viktor architecture review: crash recovery is untested until fault-injected.
"""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

# We will test against a TEMPORARY DB, not the real one
TEST_DB = ""
TEST_JOURNAL = ""
TEST_SESSION = ""


def _setup_test_env() -> str:
    """Create temp DB, journal, and inject test data."""
    global TEST_DB, TEST_JOURNAL, TEST_SESSION
    tmpdir = tempfile.mkdtemp(prefix="eni_test_")
    TEST_DB = os.path.join(tmpdir, "test_eni.db")
    TEST_JOURNAL = os.path.join(tmpdir, "test_journal.log")
    TEST_SESSION = f"test-session-{uuid.uuid4().hex[:8]}"

    # Copy schema from real DB (or init fresh)
    conn = sqlite3.connect(TEST_DB)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    # Minimal schema matching real DB
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'active',
            message_count INTEGER NOT NULL DEFAULT 0,
            started_at TEXT NOT NULL DEFAULT (datetime('now')),
            ended_at TEXT,
            context_summary TEXT
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            turn_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT,
            token_count INTEGER,
            tool_name TEXT,
            tool_result TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );
    """)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_unique ON messages(session_id, turn_id, role);")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            turn_id INTEGER NOT NULL,
            title TEXT,
            choice TEXT,
            rationale TEXT,
            rejected TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );
    """)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_decisions_unique ON decisions(session_id, turn_id, title);")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS artifacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            turn_id INTEGER NOT NULL,
            name TEXT,
            path TEXT,
            type TEXT,
            status TEXT,
            description TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );
    """)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_artifacts_unique ON artifacts(session_id, turn_id, name);")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            turn_id INTEGER NOT NULL,
            title TEXT,
            symptom TEXT,
            root_cause TEXT,
            fix TEXT,
            status TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );
    """)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_issues_unique ON issues(session_id, turn_id, title);")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            id INTEGER PRIMARY KEY,
            version INTEGER NOT NULL DEFAULT 0,
            applied_at TEXT
        );
    """)
    conn.execute("INSERT OR IGNORE INTO schema_version (id, version) VALUES (1, 6);")
    conn.execute("INSERT INTO sessions (id, status) VALUES (?, 'active');", (TEST_SESSION,))
    conn.commit()
    conn.close()
    return tmpdir


def _write_persisted_turns(n: int, session_id: str, journal_path: str, db_path: str):
    """Write n turns to BOTH journal and DB (successful persist)."""
    conn = sqlite3.connect(db_path)
    with open(journal_path, "a", encoding="utf-8") as jf:
        for i in range(n):
            turn_id = i + 1
            content = f"Turn {turn_id} persisted normally"
            ts = datetime.utcnow().isoformat()

            # Write to DB
            conn.execute(
                "INSERT INTO messages (session_id, turn_id, role, content, created_at) VALUES (?,?,?,?,?);",
                (session_id, turn_id, "assistant", content, ts),
            )
            conn.commit()

            # Write to journal
            entry = {
                "session_id": session_id,
                "turn_id": turn_id,
                "role": "assistant",
                "content": content,
                "ts": ts,
            }
            jf.write(json.dumps(entry, ensure_ascii=False) + "\n")
            jf.flush()
            os.fsync(jf.fileno())
    conn.close()


def _simulate_crash(n: int, session_id: str, journal_path: str, db_path: str, start_turn: int):
    """Simulate crash: write to journal but NOT to DB."""
    conn = sqlite3.connect(db_path)
    # Intentionally do NOT write to DB — but write to journal
    with open(journal_path, "a", encoding="utf-8") as jf:
        for i in range(n):
            turn_id = start_turn + i
            content = f"Turn {turn_id} lost in crash"
            ts = datetime.utcnow().isoformat()

            # Write to journal ONLY (simulates crash before DB commit)
            entry = {
                "session_id": session_id,
                "turn_id": turn_id,
                "role": "assistant",
                "content": content,
                "ts": ts,
            }
            jf.write(json.dumps(entry, ensure_ascii=False) + "\n")
            jf.flush()
            os.fsync(jf.fileno())
    conn.close()


def _corrupt_db(db_path: str, session_id: str, delete_turns: list):
    """Delete specific turns from DB to simulate corruption."""
    conn = sqlite3.connect(db_path)
    for turn_id in delete_turns:
        conn.execute(
            "DELETE FROM messages WHERE session_id = ? AND turn_id = ?;",
            (session_id, turn_id),
        )
    conn.commit()
    conn.close()


def _count_messages(db_path: str, session_id: str) -> int:
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE session_id = ?;", (session_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else 0


def _run_repair(session_id: str, journal_path: str, db_path: str) -> dict:
    """Run validate_and_repair against test DB."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "validate_and_repair",
        "/root/.hermes/skills/devops/eni-memory/scripts/validate_and_repair.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load validate_and_repair module spec")
    mod = importlib.util.module_from_spec(spec)
    # Monkey-patch db_utils DB_PATH before loading
    import db_utils
    original_db = db_utils.DB_PATH
    db_utils.DB_PATH = db_path
    try:
        spec.loader.exec_module(mod)
        counts = mod.repair(session_id, journal_path=journal_path, dry=False)
    finally:
        db_utils.DB_PATH = original_db
    return counts


def main() -> int:
    tmpdir = _setup_test_env()
    try:
        print(f"[test] Temp dir: {tmpdir}")
        print(f"[test] Session: {TEST_SESSION}")
        print(f"[test] DB: {TEST_DB}")
        print(f"[test] Journal: {TEST_JOURNAL}")

        # Phase 1: 10 normal persisted turns
        print("[test] Phase 1: writing 10 normal turns...")
        _write_persisted_turns(10, TEST_SESSION, TEST_JOURNAL, TEST_DB)
        assert _count_messages(TEST_DB, TEST_SESSION) == 10, "Expected 10 messages after normal persist"
        print("[test]   ✓ 10 messages in DB")

        # Phase 2: simulate crash — 5 turns in journal, NOT in DB
        print("[test] Phase 2: simulating crash (5 turns in journal only)...")
        _simulate_crash(5, TEST_SESSION, TEST_JOURNAL, TEST_DB, start_turn=11)
        assert _count_messages(TEST_DB, TEST_SESSION) == 10, "DB should still have 10 after crash"
        print("[test]   ✓ DB still has 10 messages")

        # Phase 3: simulate corruption — delete 3 turns from DB (turns 3,5,7)
        print("[test] Phase 3: corrupting DB (deleting turns 3,5,7)...")
        _corrupt_db(TEST_DB, TEST_SESSION, [3, 5, 7])
        assert _count_messages(TEST_DB, TEST_SESSION) == 7, "Expected 7 messages after corruption"
        print("[test]   ✓ DB now has 7 messages")

        # Phase 4: repair
        print("[test] Phase 4: running validate_and_repair...")
        counts = _run_repair(TEST_SESSION, TEST_JOURNAL, TEST_DB)
        print(f"[test]   Repair counts: {counts}")

        # Phase 5: assert
        final_count = _count_messages(TEST_DB, TEST_SESSION)
        print(f"[test] Phase 5: final DB message count = {final_count}")
        expected = 15  # 10 normal + 5 crash = 15 (corrupted 3 are restored by journal replay)
        if final_count != expected:
            print(f"[test] FAIL: expected {expected} messages, got {final_count}")
            return 1

        print("[test] ✓ PASS: all 15 messages recovered (10 normal + 5 crash-lost + 3 corruption-restored)")
        return 0

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        print(f"[test] Cleaned up {tmpdir}")


if __name__ == "__main__":
    sys.exit(main())
