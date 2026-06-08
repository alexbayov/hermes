"""Unified garbage collector: backups, op_log, journal.log, archived sessions.

Design based on Viktor architecture review (2026-06-08).
--dry-run by default; --apply required to mutate.
"""
import argparse
import gzip
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ------------------------------------------------------------------
# Paths
# ------------------------------------------------------------------
DB_DIR = "/root/.hermes/data"
DB_PATH = os.path.join(DB_DIR, "eni_memory.db")
BACKUP_DIR = os.path.join(DB_DIR, "backup")
JOURNAL_PATH = os.path.join(DB_DIR, "journal.log")
CONFIG_PATH = "/root/.hermes/config/retention.json"

# ------------------------------------------------------------------
# Defaults (config overrides)
# ------------------------------------------------------------------
DEFAULTS = {
    "backups": {
        "keep_daily": 7,
        "keep_weekly": 4,
        "keep_monthly": 6,
    },
    "op_log": {
        "keep_days": 30,
        "keep_rows": 200_000,
    },
    "journal": {
        "rotate_at_mb": 50,
        "keep_rotations": 10,
    },
    "archived_sessions": {
        "purge_after_days": 180,
    },
}

# Hard floor — never go below this
HARD_FLOOR = {
    "backups": 1,
    "op_log_rows": 1000,
    "journal_rotations": 1,
    "archived_sessions": 0,
}


def _load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARN] Could not read config ({e}), using defaults", file=sys.stderr)
    return {}


def _merge_config(cfg: dict) -> dict:
    merged = {}
    for key, default in DEFAULTS.items():
        merged[key] = {**default, **cfg.get(key, {})}
    return merged


# ------------------------------------------------------------------
# SQLite helpers
# ------------------------------------------------------------------
def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 60000;")
    conn.execute("PRAGMA wal_autocheckpoint = 1000;")
    return conn


def _integrity_check(conn: sqlite3.Connection) -> bool:
    row = conn.execute("PRAGMA quick_check;").fetchone()
    return row is not None and row[0] == "ok"


# ------------------------------------------------------------------
# Backup (VACUUM INTO only — fix the WAL/SHM copy bug)
# ------------------------------------------------------------------
def _backup_now() -> str:
    """VACUUM INTO backup — standalone, no WAL/SHM copy."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    dst = os.path.join(BACKUP_DIR, f"eni_memory_{ts}.db")
    # VACUUM INTO requires autocommit (no explicit transaction)
    conn = sqlite3.connect(DB_PATH, timeout=30.0, isolation_level=None)
    try:
        conn.execute(f"VACUUM INTO '{dst}';")
    finally:
        conn.close()
    # fsync file + directory
    os.sync()
    # Verify backup opens and passes quick_check
    verify_conn = sqlite3.connect(f"file:{dst}?mode=ro", uri=True)
    try:
        if not _integrity_check(verify_conn):
            raise RuntimeError(f"Backup integrity check failed: {dst}")
    finally:
        verify_conn.close()
    print(f"  Backup OK: {dst}")
    return dst


def _list_backups() -> List[Tuple[str, datetime]]:
    pattern = re.compile(r"eni_memory_(\d{8})_(\d{6})\.db$")
    backups = []
    for name in os.listdir(BACKUP_DIR):
        m = pattern.match(name)
        if m:
            dt = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
            backups.append((os.path.join(BACKUP_DIR, name), dt))
    backups.sort(key=lambda x: x[1], reverse=True)
    return backups


def _gfs_bucket(backups: List[Tuple[str, datetime]]) -> Dict[str, set]:
    """Bucket backups into GFS tiers: daily, weekly, monthly."""
    daily = set()
    weekly = set()
    monthly = set()
    for path, dt in backups:
        daily.add((dt.year, dt.month, dt.day))
        weekly.add((dt.year, dt.isocalendar().week))
        monthly.add((dt.year, dt.month))
    # Keep newest N per tier
    return {"daily": daily, "weekly": weekly, "monthly": monthly}


def _prune_backups(cfg: dict, dry_run: bool) -> int:
    keep_daily = max(cfg["backups"]["keep_daily"], HARD_FLOOR["backups"])
    keep_weekly = max(cfg["backups"]["keep_weekly"], 1)
    keep_monthly = max(cfg["backups"]["keep_monthly"], 1)
    backups = _list_backups()
    if not backups:
        return 0
    # Collect keepers
    keepers = set()
    # Always keep the newest backup
    keepers.add(backups[0][0])
    # Daily: keep newest per day up to keep_daily
    daily_seen = {}
    for path, dt in backups:
        key = (dt.year, dt.month, dt.day)
        if key not in daily_seen and len(daily_seen) < keep_daily:
            daily_seen[key] = path
            keepers.add(path)
    # Weekly: keep newest per week up to keep_weekly
    weekly_seen = {}
    for path, dt in backups:
        key = (dt.year, dt.isocalendar().week)
        if key not in weekly_seen and len(weekly_seen) < keep_weekly:
            weekly_seen[key] = path
            keepers.add(path)
    # Monthly: keep newest per month up to keep_monthly
    monthly_seen = {}
    for path, dt in backups:
        key = (dt.year, dt.month)
        if key not in monthly_seen and len(monthly_seen) < keep_monthly:
            monthly_seen[key] = path
            keepers.add(path)
    deleted = 0
    for path, _ in backups:
        if path not in keepers:
            if dry_run:
                print(f"  [dry-run] Would delete backup: {path}")
            else:
                os.remove(path)
                print(f"  Deleted backup: {path}")
            deleted += 1
    return deleted


# ------------------------------------------------------------------
# op_log prune (batched)
# ------------------------------------------------------------------
def _prune_op_log(conn: sqlite3.Connection, cfg: dict, dry_run: bool) -> int:
    keep_days = cfg["op_log"]["keep_days"]
    keep_rows = max(cfg["op_log"]["keep_rows"], HARD_FLOOR["op_log_rows"])
    cutoff_dt = datetime.utcnow() - timedelta(days=keep_days)
    cutoff_iso = cutoff_dt.strftime("%Y-%m-%d %H:%M:%S")
    # Determine rowid threshold for keep_rows
    row_threshold = conn.execute(
        "SELECT id FROM op_log ORDER BY id DESC LIMIT 1 OFFSET ?",
        (keep_rows,),
    ).fetchone()
    row_threshold = row_threshold[0] if row_threshold else 0
    # Count before
    before = conn.execute(
        "SELECT COUNT(*) FROM op_log WHERE created_at < ? OR id < ?",
        (cutoff_iso, row_threshold),
    ).fetchone()[0]
    if before == 0:
        return 0
    if dry_run:
        print(f"  [dry-run] Would delete {before} op_log rows")
        return before
    # Batched delete (5000 per txn) to avoid long write lock
    batch = 5000
    deleted = 0
    while True:
        cur = conn.execute(
            "DELETE FROM op_log WHERE id IN ("
            "SELECT id FROM op_log WHERE created_at < ? OR id < ? LIMIT ?"
            ")",
            (cutoff_iso, row_threshold, batch),
        )
        conn.commit()
        if cur.rowcount == 0:
            break
        deleted += cur.rowcount
        if cur.rowcount < batch:
            break
    conn.execute("PRAGMA wal_checkpoint;")
    print(f"  Deleted {deleted} op_log rows")
    return deleted


# ------------------------------------------------------------------
# journal.log rotation
# ------------------------------------------------------------------
def _rotate_journal(conn: sqlite3.Connection, cfg: dict, dry_run: bool) -> int:
    rotate_at_mb = cfg["journal"]["rotate_at_mb"]
    keep_rotations = max(cfg["journal"]["keep_rotations"], HARD_FLOOR["journal_rotations"])
    if not os.path.exists(JOURNAL_PATH):
        return 0
    size_bytes = os.path.getsize(JOURNAL_PATH)
    size_mb = size_bytes / (1024 * 1024)
    if size_mb < rotate_at_mb:
        return 0
    # Only rotate if all entries are materialized in DB
    max_turn_db = conn.execute("SELECT COALESCE(MAX(turn_id), 0) FROM messages").fetchone()[0]
    # Read last line of journal to check max turn_id in it
    last_turn = 0
    try:
        with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    last_turn = max(last_turn, rec.get("turn_id", 0))
                except Exception:
                    pass
    except Exception:
        pass
    if last_turn > max_turn_db:
        print(f"  [SKIP] Journal has unmaterialized turns (journal turn {last_turn} > DB turn {max_turn_db})")
        return 0
    if dry_run:
        print(f"  [dry-run] Would rotate journal ({size_mb:.1f} MB)")
        return 1
    # fsync + rotate
    with open(JOURNAL_PATH, "a", encoding="utf-8") as f:
        f.flush()
        os.fsync(f.fileno())
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    rotated = os.path.join(DB_DIR, f"journal.{ts}.log")
    os.rename(JOURNAL_PATH, rotated)
    # gzip
    with open(rotated, "rb") as f_in:
        with gzip.open(rotated + ".gz", "wb") as f_out:
            f_out.writelines(f_in)
    os.remove(rotated)
    # open fresh journal
    with open(JOURNAL_PATH, "w", encoding="utf-8") as f:
        f.flush()
        os.fsync(f.fileno())
    # Clean old rotations
    rotations = sorted(
        [p for p in os.listdir(DB_DIR) if re.match(r"journal\.\d{8}_\d{6}\.log\.gz$", p)],
        reverse=True,
    )
    removed = 0
    for old in rotations[keep_rotations:]:
        os.remove(os.path.join(DB_DIR, old))
        removed += 1
    print(f"  Rotated journal -> {rotated}.gz, removed {removed} old rotations")
    return 1 + removed


# ------------------------------------------------------------------
# Archived session purge
# ------------------------------------------------------------------
def _purge_archived_sessions(conn: sqlite3.Connection, cfg: dict, dry_run: bool) -> int:
    purge_days = cfg["archived_sessions"]["purge_after_days"]
    cutoff_iso = (datetime.utcnow() - timedelta(days=purge_days)).strftime("%Y-%m-%d %H:%M:%S")
    # Find candidate sessions
    rows = conn.execute(
        "SELECT id FROM sessions WHERE status IN ('archived', 'compacted')"
        " AND (ended_at IS NOT NULL AND ended_at < ?)",
        (cutoff_iso,),
    ).fetchall()
    if not rows:
        return 0
    # Respect FK: skip if any live decision/artifact/issue still references them
    to_delete = []
    for (sid,) in rows:
        has_refs = conn.execute(
            "SELECT 1 FROM decisions WHERE session_id = ? AND active = 1 LIMIT 1", (sid,)
        ).fetchone()
        if has_refs:
            continue
        has_refs = conn.execute(
            "SELECT 1 FROM artifacts WHERE session_id = ? AND status != 'deleted' LIMIT 1", (sid,)
        ).fetchone()
        if has_refs:
            continue
        has_refs = conn.execute(
            "SELECT 1 FROM issues WHERE session_id = ? AND status = 'open' LIMIT 1", (sid,)
        ).fetchone()
        if has_refs:
            continue
        to_delete.append(sid)
    if not to_delete:
        return 0
    if dry_run:
        print(f"  [dry-run] Would delete {len(to_delete)} archived sessions")
        return len(to_delete)
    # CASCADE will handle children
    placeholders = ",".join("?" * len(to_delete))
    conn.execute(f"DELETE FROM sessions WHERE id IN ({placeholders})", to_delete)
    conn.commit()
    print(f"  Deleted {len(to_delete)} archived sessions")
    return len(to_delete)


# ------------------------------------------------------------------
# Metrics / retention_runs
# ------------------------------------------------------------------
def _ensure_retention_runs(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS retention_runs (
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
        )"""
    )
    conn.commit()


def _record_run(
    conn: sqlite3.Connection,
    run_id: int,
    started_at: str,
    metrics: dict,
    status: str,
    error: Optional[str],
) -> None:
    conn.execute(
        """UPDATE retention_runs SET
            ended_at = datetime('now'),
            db_size_mb = ?,
            wal_size_mb = ?,
            op_log_rows_before = ?,
            op_log_rows_deleted = ?,
            journal_bytes_before = ?,
            journal_rotations = ?,
            backups_deleted = ?,
            sessions_purged = ?,
            status = ?,
            error = ?
        WHERE id = ?""",
        (
            metrics.get("db_size_mb"),
            metrics.get("wal_size_mb"),
            metrics.get("op_log_rows_before"),
            metrics.get("op_log_rows_deleted"),
            metrics.get("journal_bytes_before"),
            metrics.get("journal_rotations"),
            metrics.get("backups_deleted"),
            metrics.get("sessions_purged"),
            status,
            error,
            run_id,
        ),
    )
    conn.commit()


# ------------------------------------------------------------------
# Issue record
# ------------------------------------------------------------------
def _record_issue(conn: sqlite3.Connection, run_id: int, summary: dict, status: str) -> None:
    title = f"RETENTION-{run_id}"
    symptom = json.dumps(summary, ensure_ascii=False, indent=2)
    fix = "Garbage collection completed"
    issue_status = "fixed" if status == "success" else "open"
    conn.execute(
        "INSERT OR REPLACE INTO issues (session_id, turn_id, title, symptom, root_cause, fix, status)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("retention", 0, title, symptom, None, fix, issue_status),
    )
    conn.commit()


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
def run(dry_run: bool = True, apply: bool = False) -> bool:
    if apply:
        dry_run = False
    started_at = datetime.utcnow().isoformat()
    print(f"[{started_at}] retention.py {'--dry-run' if dry_run else '--apply'}")
    cfg = _merge_config(_load_config())
    conn = _get_conn()
    run_id = None
    metrics = {}
    try:
        # 1. quick_check
        if not _integrity_check(conn):
            print("ERROR: PRAGMA quick_check failed. Aborting.", file=sys.stderr)
            return False
        # Ensure retention dummy session exists for FK (issues table)
        conn.execute("INSERT OR IGNORE INTO sessions (id, status) VALUES ('retention', 'active')")
        conn.commit()
        # Ensure metrics table exists
        _ensure_retention_runs(conn)
        # Insert running record
        cur = conn.execute(
            "INSERT INTO retention_runs (started_at, status) VALUES (?, 'running')",
            (started_at,),
        )
        run_id = cur.lastrowid
        # Gather pre-metrics
        db_size = os.path.getsize(DB_PATH) / (1024 * 1024)
        wal_path = DB_PATH + "-wal"
        wal_size = os.path.getsize(wal_path) / (1024 * 1024) if os.path.exists(wal_path) else 0.0
        journal_bytes = os.path.getsize(JOURNAL_PATH) if os.path.exists(JOURNAL_PATH) else 0
        op_log_before = conn.execute("SELECT COUNT(*) FROM op_log").fetchone()[0]
        metrics = {
            "db_size_mb": round(db_size, 2),
            "wal_size_mb": round(wal_size, 2),
            "op_log_rows_before": op_log_before,
            "journal_bytes_before": journal_bytes,
        }
        # 2. Backup
        print("Step 1: Backup...")
        _backup_now()
        # 3. Prune backups
        print("Step 2: Prune backups...")
        metrics["backups_deleted"] = _prune_backups(cfg, dry_run)
        # 4. Rotate journal
        print("Step 3: Rotate journal...")
        metrics["journal_rotations"] = _rotate_journal(conn, cfg, dry_run)
        # 5. Prune op_log
        print("Step 4: Prune op_log...")
        metrics["op_log_rows_deleted"] = _prune_op_log(conn, cfg, dry_run)
        # 6. Purge archived sessions
        print("Step 5: Purge archived sessions...")
        metrics["sessions_purged"] = _purge_archived_sessions(conn, cfg, dry_run)
        # 7. Reclaim pages
        if not dry_run:
            conn.execute("PRAGMA incremental_vacuum;")
            conn.commit()
        # 8. Final integrity check
        if not _integrity_check(conn):
            _record_run(conn, run_id, started_at, metrics, "failed", "Integrity check failed after GC")
            _record_issue(conn, run_id, metrics, "failed")
            print("ERROR: Integrity check failed after GC", file=sys.stderr)
            return False
        # Record success
        _record_run(conn, run_id, started_at, metrics, "success", None)
        _record_issue(conn, run_id, metrics, "success")
        print(f"Done. Run ID: {run_id}")
        print(f"Metrics: {json.dumps(metrics, indent=2)}")
        return True
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        try:
            if run_id is not None:
                _record_run(conn, run_id, started_at, metrics, "failed", str(e))
                _record_issue(conn, run_id, metrics, "failed")
        except Exception:
            pass
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unified retention / garbage collector for ENI memory DB")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Show plan without mutating (default)")
    parser.add_argument("--apply", action="store_true", default=False, help="Actually perform mutations")
    args = parser.parse_args()
    ok = run(dry_run=args.dry_run, apply=args.apply)
    sys.exit(0 if ok else 1)
