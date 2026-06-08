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
