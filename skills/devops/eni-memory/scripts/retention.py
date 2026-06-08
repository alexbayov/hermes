#!/usr/bin/env python3
"""
retention.py -- garbage-collection / retention toolkit for the Hermes SQLite
persistent-memory store.

Performs, in a single idempotent pass:
  * integrity gate (quick_check) before any work
  * VACUUM INTO backup + per-backup quick_check verification
  * GFS backup rotation (daily / weekly / monthly)
  * op_log pruning (age + hard row cap), batched
  * journal.log size-based rotation + gzip, only for materialized entries
  * archived/compacted session purge, respecting foreign-key references
  * metrics row in retention_runs
  * summary issue row in issues

Stdlib only. Dry-run is the default; pass --apply to actually mutate anything.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import shutil
import sqlite3
import sys
import time
import traceback
from datetime import datetime, timezone

# --------------------------------------------------------------------------- #
# Defaults / configuration
# --------------------------------------------------------------------------- #

DEFAULT_DB_PATH = "/root/.hermes/data/eni_memory.db"
DEFAULT_BACKUP_DIR = "/root/.hermes/data/backup/"
DEFAULT_JOURNAL_PATH = "/root/.hermes/data/journal.log"
DEFAULT_CONFIG_PATH = "/root/.hermes/config/retention.json"

DEFAULTS = {
    "db_path": DEFAULT_DB_PATH,
    "backup_dir": DEFAULT_BACKUP_DIR,
    "journal_path": DEFAULT_JOURNAL_PATH,
    "backup_prefix": "eni_memory",
    # GFS rotation
    "keep_daily": 7,
    "keep_weekly": 4,
    "keep_monthly": 6,
    # op_log prune
    "op_log_retention_days": 30,
    "op_log_max_rows": 200000,
    "op_log_batch_size": 5000,
    # journal rotation
    "journal_max_bytes": 50 * 1024 * 1024,  # 50 MB
    "journal_keep_rotations": 10,
    # session purge
    "session_purge_days": 180,
}

# filenames look like:  eni_memory_YYYYMMDD_HHMMSS.db
BACKUP_RE = re.compile(r"^(?P<prefix>.+)_(?P<ts>\d{8}_\d{6})\.db$")


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #

def log(msg: str) -> None:
    print(f"[retention] {msg}", flush=True)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def file_size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def mb(n_bytes: int) -> float:
    return round(n_bytes / (1024 * 1024), 3)


def load_config(path: str) -> dict:
    cfg = dict(DEFAULTS)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            user_cfg = json.load(fh)
        if isinstance(user_cfg, dict):
            cfg.update({k: v for k, v in user_cfg.items() if v is not None})
            log(f"loaded config overrides from {path}")
        else:
            log(f"config at {path} is not a JSON object; using defaults")
    except FileNotFoundError:
        log(f"no config file at {path}; using inline defaults")
    except (json.JSONDecodeError, OSError) as exc:
        log(f"could not read config {path}: {exc}; using inline defaults")
    return cfg


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=60.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 60000;")
    return conn


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def column_names(conn: sqlite3.Connection, table: str) -> set:
    try:
        return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    except sqlite3.Error:
        return set()


def quick_check(conn: sqlite3.Connection) -> bool:
    try:
        rows = conn.execute("PRAGMA quick_check;").fetchall()
    except sqlite3.Error as exc:
        log(f"quick_check raised: {exc}")
        return False
    results = [str(r[0]).strip().lower() for r in rows]
    ok = results == ["ok"]
    if not ok:
        log(f"quick_check failed: {results}")
    return ok


def quick_check_path(db_path: str) -> bool:
    try:
        c = sqlite3.connect(db_path, timeout=30.0)
    except sqlite3.Error as exc:
        log(f"cannot open {db_path} for verification: {exc}")
        return False
    try:
        return quick_check(c)
    finally:
        c.close()


# --------------------------------------------------------------------------- #
# Schema bootstrap (only the tables this script owns)
# --------------------------------------------------------------------------- #

def ensure_retention_runs(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS retention_runs (
            id                   INTEGER PRIMARY KEY,
            started_at           TEXT,
            ended_at             TEXT,
            db_size_mb           REAL,
            wal_size_mb          REAL,
            op_log_rows_before   INTEGER,
            op_log_rows_deleted  INTEGER,
            journal_bytes_before INTEGER,
            journal_rotations    INTEGER,
            backups_deleted      INTEGER,
            sessions_purged      INTEGER,
            status               TEXT,
            error                TEXT
        );
        """
    )


# --------------------------------------------------------------------------- #
# 1. Backups + GFS rotation
# --------------------------------------------------------------------------- #

def make_backup(conn: sqlite3.Connection, cfg: dict, apply: bool) -> str | None:
    backup_dir = cfg["backup_dir"]
    prefix = cfg["backup_prefix"]
    ts = utcnow().strftime("%Y%m%d_%H%M%S")
    target = os.path.join(backup_dir, f"{prefix}_{ts}.db")

    if not apply:
        log(f"[dry-run] would VACUUM INTO {target}")
        return None

    os.makedirs(backup_dir, exist_ok=True)
    if os.path.exists(target):
        log(f"backup target already exists, skipping create: {target}")
        return target

    # VACUUM INTO produces a single clean DB file (no -wal / -shm sidecars).
    conn.execute("VACUUM INTO ?;", (target,))
    log(f"created backup {target} ({mb(file_size(target))} MB)")

    if not quick_check_path(target):
        log(f"backup verification FAILED, removing bad file: {target}")
        try:
            os.remove(target)
        except OSError as exc:
            log(f"could not remove bad backup {target}: {exc}")
        return None

    log(f"backup verified ok: {target}")
    return target


def _parse_backup_ts(name: str, prefix: str) -> datetime | None:
    m = BACKUP_RE.match(name)
    if not m:
        return None
    if m.group("prefix") != prefix:
        return None
    try:
        return datetime.strptime(m.group("ts"), "%Y%m%d_%H%M%S").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def select_gfs_keep(backups: list[tuple[str, datetime]], cfg: dict) -> set:
    """
    Grandfather-Father-Son selection.

    `backups` is a list of (path, datetime) for valid backups.
    Returns the set of paths to KEEP.
    """
    keep: set = set()
    # newest first
    ordered = sorted(backups, key=lambda t: t[1], reverse=True)

    def take(bucket_key, limit):
        seen = {}
        for path, dt in ordered:
            k = bucket_key(dt)
            # first (newest) backup we see for each bucket represents that bucket
            if k not in seen:
                seen[k] = path
            if len(seen) >= limit:
                break
        keep.update(seen.values())

    # daily: keep N most recent distinct calendar days
    take(lambda d: d.strftime("%Y-%m-%d"), cfg["keep_daily"])
    # weekly: keep N most recent distinct ISO weeks
    take(lambda d: f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}", cfg["keep_weekly"])
    # monthly: keep N most recent distinct months
    take(lambda d: d.strftime("%Y-%m"), cfg["keep_monthly"])

    return keep


def rotate_backups(cfg: dict, apply: bool, just_created: str | None) -> int:
    backup_dir = cfg["backup_dir"]
    prefix = cfg["backup_prefix"]
    if not os.path.isdir(backup_dir):
        log(f"backup dir {backup_dir} does not exist; nothing to rotate")
        return 0

    candidates: list[tuple[str, datetime]] = []
    for name in os.listdir(backup_dir):
        dt = _parse_backup_ts(name, prefix)
        if dt is None:
            continue
        candidates.append((os.path.join(backup_dir, name), dt))

    if not candidates:
        log("no parseable backups found to rotate")
        return 0

    keep = select_gfs_keep(candidates, cfg)
    # never delete the backup we just made this run
    if just_created:
        keep.add(just_created)

    to_delete = [p for p, _ in candidates if p not in keep]
    to_delete.sort()

    log(
        f"backups: {len(candidates)} total, keep {len(keep)}, "
        f"delete {len(to_delete)}"
    )

    deleted = 0
    for path in to_delete:
        if not apply:
            log(f"[dry-run] would delete backup {os.path.basename(path)}")
            deleted += 1
            continue
        try:
            os.remove(path)
            deleted += 1
            log(f"deleted backup {os.path.basename(path)}")
        except OSError as exc:
            log(f"could not delete {path}: {exc}")
    return deleted


# --------------------------------------------------------------------------- #
# 2. op_log prune
# --------------------------------------------------------------------------- #

def op_log_counts(conn: sqlite3.Connection) -> int:
    if not table_exists(conn, "op_log"):
        return 0
    return conn.execute("SELECT COUNT(*) FROM op_log;").fetchone()[0]


def prune_op_log(conn: sqlite3.Connection, cfg: dict, apply: bool) -> int:
    if not table_exists(conn, "op_log"):
        log("op_log table absent; skipping prune")
        return 0

    cols = column_names(conn, "op_log")
    if "id" not in cols:
        log("op_log has no id column; skipping prune")
        return 0

    days = int(cfg["op_log_retention_days"])
    max_rows = int(cfg["op_log_max_rows"])
    batch = int(cfg["op_log_batch_size"])

    # Hard row-cap boundary: keep at most max_rows newest rows.
    cap_row = conn.execute(
        "SELECT id FROM op_log ORDER BY id DESC LIMIT 1 OFFSET ?;",
        (max_rows,),
    ).fetchone()
    cap_id = cap_row[0] if cap_row else None

    has_created = "created_at" in cols

    # Build the predicate identifying rows eligible for deletion.
    # age-based OR hard-cap-based.
    where_parts = []
    params: list = []
    if has_created:
        where_parts.append("created_at < datetime('now', ?)")
        params.append(f"-{days} days")
    if cap_id is not None:
        where_parts.append("id < ?")
        params.append(cap_id)

    if not where_parts:
        log("op_log: nothing matches prune criteria")
        return 0

    where_clause = " OR ".join(where_parts)

    eligible = conn.execute(
        f"SELECT COUNT(*) FROM op_log WHERE {where_clause};", params
    ).fetchone()[0]

    if eligible == 0:
        log("op_log: 0 rows eligible for prune")
        return 0

    if not apply:
        log(f"[dry-run] would prune {eligible} op_log rows (batched {batch})")
        return eligible

    # Batched delete: select a window of ids, then delete by id.
    total_deleted = 0
    while True:
        ids = [
            r[0]
            for r in conn.execute(
                f"SELECT id FROM op_log WHERE {where_clause} LIMIT ?;",
                params + [batch],
            ).fetchall()
        ]
        if not ids:
            break
        placeholders = ",".join("?" * len(ids))
        with conn:  # one transaction per batch
            cur = conn.execute(
                f"DELETE FROM op_log WHERE id IN ({placeholders});", ids
            )
            total_deleted += cur.rowcount if cur.rowcount != -1 else len(ids)
        log(f"op_log: deleted batch of {len(ids)} (total {total_deleted})")

    # checkpoint WAL after the prune
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        log("op_log: wal_checkpoint(TRUNCATE) done")
    except sqlite3.Error as exc:
        log(f"wal_checkpoint failed: {exc}")

    return total_deleted


# --------------------------------------------------------------------------- #
# 3. journal.log rotation
# --------------------------------------------------------------------------- #

def materialized_turn_id(conn: sqlite3.Connection) -> int | None:
    if not table_exists(conn, "messages"):
        return None
    if "turn_id" not in column_names(conn, "messages"):
        return None
    row = conn.execute("SELECT MAX(turn_id) FROM messages;").fetchone()
    return row[0] if row and row[0] is not None else None


_JOURNAL_TURN_RE = re.compile(r'"turn_id"\s*:\s*(\d+)')


def _entry_turn_id(line: str) -> int | None:
    """Best-effort extraction of turn_id from a journal line (JSON or kv)."""
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
        if isinstance(obj, dict) and "turn_id" in obj:
            return int(obj["turn_id"])
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    m = _JOURNAL_TURN_RE.search(line)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def rotate_journal(
    conn: sqlite3.Connection, cfg: dict, apply: bool
) -> tuple[int, int]:
    """
    Returns (journal_bytes_before, rotations_performed).
    Only entries whose turn_id <= max materialized turn_id are eligible to be
    rotated out; unmaterialized tail entries are preserved in journal.log.
    """
    journal_path = cfg["journal_path"]
    max_bytes = int(cfg["journal_max_bytes"])
    keep = int(cfg["journal_keep_rotations"])

    before = file_size(journal_path)
    if before == 0:
        log("journal.log absent or empty; nothing to rotate")
        return 0, 0

    if before <= max_bytes:
        log(f"journal.log {mb(before)} MB <= threshold {mb(max_bytes)} MB; skip")
        return before, 0

    materialized = materialized_turn_id(conn)

    # Partition lines into "rotate" (materialized/no-id) and "keep" (tail).
    rotate_lines: list[str] = []
    keep_lines: list[str] = []
    started_keeping = False
    try:
        with open(journal_path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if started_keeping:
                    keep_lines.append(line)
                    continue
                tid = _entry_turn_id(line)
                if materialized is not None and tid is not None and tid > materialized:
                    # First unmaterialized entry; everything from here stays.
                    started_keeping = True
                    keep_lines.append(line)
                else:
                    rotate_lines.append(line)
    except OSError as exc:
        log(f"could not read journal {journal_path}: {exc}")
        return before, 0

    if not rotate_lines:
        log("journal: no materialized entries eligible to rotate")
        return before, 0

    ts = utcnow().strftime("%Y%m%d_%H%M%S")
    rotated_name = f"{journal_path}.{ts}.log"
    gz_name = rotated_name + ".gz"

    if not apply:
        log(
            f"[dry-run] would rotate {len(rotate_lines)} journal entries "
            f"-> {os.path.basename(gz_name)}, keep {len(keep_lines)} tail entries"
        )
        return before, 1

    # Write rotated content, then gzip it.
    with open(rotated_name, "w", encoding="utf-8") as out:
        out.writelines(rotate_lines)
        out.flush()
        os.fsync(out.fileno())

    with open(rotated_name, "rb") as f_in, gzip.open(gz_name, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    try:
        os.remove(rotated_name)
    except OSError:
        pass
    log(f"journal: wrote {os.path.basename(gz_name)} ({len(rotate_lines)} entries)")

    # Rewrite journal.log with only the preserved tail (atomic replace).
    tmp = journal_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as out:
        out.writelines(keep_lines)
        out.flush()
        os.fsync(out.fileno())
    os.replace(tmp, journal_path)
    # fsync the directory so the rename is durable
    try:
        dfd = os.open(os.path.dirname(journal_path) or ".", os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError:
        pass
    log(f"journal: truncated live log to {len(keep_lines)} tail entries")

    prune_journal_rotations(journal_path, keep, apply)
    return before, 1


def prune_journal_rotations(journal_path: str, keep: int, apply: bool) -> None:
    d = os.path.dirname(journal_path) or "."
    base = os.path.basename(journal_path)
    rot_re = re.compile(re.escape(base) + r"\.(\d{8}_\d{6})\.log\.gz$")
    rotations = []
    try:
        for name in os.listdir(d):
            m = rot_re.match(name)
            if m:
                rotations.append((os.path.join(d, name), m.group(1)))
    except OSError:
        return
    rotations.sort(key=lambda t: t[1], reverse=True)  # newest first
    for path, _ in rotations[keep:]:
        if not apply:
            log(f"[dry-run] would delete old rotation {os.path.basename(path)}")
            continue
        try:
            os.remove(path)
            log(f"deleted old journal rotation {os.path.basename(path)}")
        except OSError as exc:
            log(f"could not delete rotation {path}: {exc}")


# --------------------------------------------------------------------------- #
# 4. Archived/compacted session purge (FK-aware)
# --------------------------------------------------------------------------- #

# child tables that may reference sessions.session_id; only those present are checked
SESSION_REFERENCERS = ("decisions", "artifacts", "issues")


def purge_sessions(conn: sqlite3.Connection, cfg: dict, apply: bool) -> int:
    if not table_exists(conn, "sessions"):
        log("sessions table absent; skipping purge")
        return 0

    scols = column_names(conn, "sessions")
    if not {"session_id", "status", "ended_at"}.issubset(scols):
        log("sessions missing required columns; skipping purge")
        return 0

    days = int(cfg["session_purge_days"])

    candidates = [
        r[0]
        for r in conn.execute(
            """
            SELECT session_id FROM sessions
            WHERE status IN ('archived','compacted')
              AND ended_at IS NOT NULL
              AND ended_at < date('now', ?);
            """,
            (f"-{days} days",),
        ).fetchall()
    ]
    if not candidates:
        log("no archived/compacted sessions past the purge window")
        return 0

    # Determine which referencer tables actually exist and reference session_id.
    active_refs = []
    for tbl in SESSION_REFERENCERS:
        if table_exists(conn, tbl) and "session_id" in column_names(conn, tbl):
            active_refs.append(tbl)

    purgeable = []
    skipped = 0
    for sid in candidates:
        referenced = False
        for tbl in active_refs:
            row = conn.execute(
                f"SELECT 1 FROM {tbl} WHERE session_id = ? LIMIT 1;", (sid,)
            ).fetchone()
            if row:
                referenced = True
                break
        if referenced:
            skipped += 1
        else:
            purgeable.append(sid)

    log(
        f"sessions purge: {len(candidates)} candidates, "
        f"{len(purgeable)} purgeable, {skipped} skipped (live references)"
    )

    if not purgeable:
        return 0

    if not apply:
        log(f"[dry-run] would purge {len(purgeable)} sessions")
        return len(purgeable)

    deleted = 0
    batch = 500
    for i in range(0, len(purgeable), batch):
        chunk = purgeable[i : i + batch]
        placeholders = ",".join("?" * len(chunk))
        with conn:
            cur = conn.execute(
                f"DELETE FROM sessions WHERE session_id IN ({placeholders});", chunk
            )
            deleted += cur.rowcount if cur.rowcount != -1 else len(chunk)
    log(f"sessions purge: deleted {deleted}")
    return deleted


# --------------------------------------------------------------------------- #
# Metrics + issue records
# --------------------------------------------------------------------------- #

def insert_run(conn: sqlite3.Connection, metrics: dict, apply: bool) -> int | None:
    if not apply:
        log("[dry-run] would insert retention_runs row")
        return None
    ensure_retention_runs(conn)
    with conn:
        cur = conn.execute(
            """
            INSERT INTO retention_runs (
                started_at, ended_at, db_size_mb, wal_size_mb,
                op_log_rows_before, op_log_rows_deleted,
                journal_bytes_before, journal_rotations,
                backups_deleted, sessions_purged, status, error
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?);
            """,
            (
                metrics["started_at"],
                metrics["ended_at"],
                metrics["db_size_mb"],
                metrics["wal_size_mb"],
                metrics["op_log_rows_before"],
                metrics["op_log_rows_deleted"],
                metrics["journal_bytes_before"],
                metrics["journal_rotations"],
                metrics["backups_deleted"],
                metrics["sessions_purged"],
                metrics["status"],
                metrics["error"],
            ),
        )
        return cur.lastrowid


def insert_issue(
    conn: sqlite3.Connection, run_id: int | None, metrics: dict, apply: bool
) -> None:
    if not apply:
        log("[dry-run] would insert issues summary row")
        return
    if not table_exists(conn, "issues"):
        log("issues table absent; skipping issue record")
        return

    icols = column_names(conn, "issues")
    rid = run_id if run_id is not None else 0
    status = "fixed" if metrics["status"] == "ok" else "open"
    fix_json = json.dumps(
        {
            "run_id": rid,
            "op_log_rows_deleted": metrics["op_log_rows_deleted"],
            "journal_rotations": metrics["journal_rotations"],
            "backups_deleted": metrics["backups_deleted"],
            "sessions_purged": metrics["sessions_purged"],
            "db_size_mb": metrics["db_size_mb"],
            "status": metrics["status"],
        },
        separators=(",", ":"),
    )

    payload = {
        "session_id": "retention",
        "turn_id": 0,
        "title": f"RETENTION-{rid}",
        "symptom": "GC summary",
        "fix": fix_json,
        "status": status,
    }
    usable = {k: v for k, v in payload.items() if k in icols}
    cols = ",".join(usable.keys())
    placeholders = ",".join("?" * len(usable))
    with conn:
        conn.execute(
            f"INSERT INTO issues ({cols}) VALUES ({placeholders});",
            list(usable.values()),
        )
    log(f"issues: inserted RETENTION-{rid} ({status})")


# --------------------------------------------------------------------------- #
# Main orchestration
# --------------------------------------------------------------------------- #

def run(cfg: dict, apply: bool) -> int:
    db_path = cfg["db_path"]
    started = utcnow()

    metrics = {
        "started_at": iso(started),
        "ended_at": None,
        "db_size_mb": mb(file_size(db_path)),
        "wal_size_mb": mb(file_size(db_path + "-wal")),
        "op_log_rows_before": 0,
        "op_log_rows_deleted": 0,
        "journal_bytes_before": 0,
        "journal_rotations": 0,
        "backups_deleted": 0,
        "sessions_purged": 0,
        "status": "ok",
        "error": None,
    }

    if not os.path.exists(db_path):
        log(f"FATAL: database not found at {db_path}")
        return 2

    conn = connect(db_path)
    try:
        # (7) integrity gate
        if not quick_check(conn):
            log("FATAL: quick_check not ok; aborting before any mutation")
            metrics["status"] = "aborted"
            metrics["error"] = "quick_check_failed"
            metrics["ended_at"] = iso(utcnow())
            # record the aborted run if we can
            try:
                rid = insert_run(conn, metrics, apply)
                insert_issue(conn, rid, metrics, apply)
            except sqlite3.Error:
                pass
            return 3
        log("quick_check ok")

        metrics["op_log_rows_before"] = op_log_counts(conn)

        # (1) backup + verify, then GFS rotation
        created = make_backup(conn, cfg, apply)
        metrics["backups_deleted"] = rotate_backups(cfg, apply, created)

        # (2) op_log prune
        metrics["op_log_rows_deleted"] = prune_op_log(conn, cfg, apply)

        # (3) journal rotation
        jbefore, jrot = rotate_journal(conn, cfg, apply)
        metrics["journal_bytes_before"] = jbefore
        metrics["journal_rotations"] = jrot

        # (4) session purge
        metrics["sessions_purged"] = purge_sessions(conn, cfg, apply)

        # refresh size metrics after work
        metrics["db_size_mb"] = mb(file_size(db_path))
        metrics["wal_size_mb"] = mb(file_size(db_path + "-wal"))
        metrics["ended_at"] = iso(utcnow())

        rid = insert_run(conn, metrics, apply)
        insert_issue(conn, rid, metrics, apply)

        log(
            "DONE "
            + json.dumps(
                {
                    "apply": apply,
                    "backups_deleted": metrics["backups_deleted"],
                    "op_log_rows_deleted": metrics["op_log_rows_deleted"],
                    "journal_rotations": metrics["journal_rotations"],
                    "sessions_purged": metrics["sessions_purged"],
                    "status": metrics["status"],
                }
            )
        )
        return 0

    except Exception as exc:  # noqa: BLE001 - record then re-surface as exit code
        metrics["status"] = "error"
        metrics["error"] = f"{type(exc).__name__}: {exc}"
        metrics["ended_at"] = iso(utcnow())
        log("ERROR: " + metrics["error"])
        log(traceback.format_exc())
        try:
            rid = insert_run(conn, metrics, apply)
            insert_issue(conn, rid, metrics, apply)
        except sqlite3.Error:
            pass
        return 1
    finally:
        try:
            conn.close()
        except sqlite3.Error:
            pass


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Retention / GC toolkit for the Hermes SQLite memory store.",
    )
    p.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help=f"path to JSON config (default: {DEFAULT_CONFIG_PATH})",
    )
    p.add_argument("--db", help="override database path")
    p.add_argument("--backup-dir", help="override backup directory")
    p.add_argument("--journal", help="override journal.log path")
    g = p.add_mutually_exclusive_group()
    g.add_argument(
        "--apply",
        action="store_true",
        help="actually perform mutations (default is dry-run)",
    )
    g.add_argument(
        "--dry-run",
        action="store_true",
        help="explicit dry-run (this is the default behaviour)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config(args.config)
    if args.db:
        cfg["db_path"] = args.db
    if args.backup_dir:
        cfg["backup_dir"] = args.backup_dir
    if args.journal:
        cfg["journal_path"] = args.journal

    apply = bool(args.apply)  # dry-run is the default
    log(f"mode = {'APPLY' if apply else 'DRY-RUN'}")
    return run(cfg, apply)


if __name__ == "__main__":
    sys.exit(main())
