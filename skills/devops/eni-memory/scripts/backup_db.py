"""Atomic backup: DB + WAL + JSONL journal."""
import os
import sys
import shutil
from datetime import datetime
from db_utils import DB_PATH, get_conn, integrity_check

JOURNAL_PATH = "/root/.hermes/data/journal.log"
BACKUP_DIR = "/root/.hermes/data/backup"


def backup(
    label: str = None,
    include_journal: bool = True,
    include_wal: bool = True,
) -> str:
    if not integrity_check():
        print("ERROR: integrity_check failed, aborting", file=sys.stderr)
        sys.exit(1)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    name = f"{ts}_{label}" if label else ts
    dst_dir = os.path.join(BACKUP_DIR, name)
    os.makedirs(dst_dir, exist_ok=True)

    dst_db = os.path.join(dst_dir, "eni_memory.db")

    # Atomic DB snapshot via VACUUM INTO (does not include WAL automatically)
    conn = get_conn()
    conn.execute(f"VACUUM INTO '{dst_db}';")
    conn.close()

    # Copy WAL + SHM if present and requested
    if include_wal:
        for ext in ("-wal", "-shm"):
            src = DB_PATH + ext
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(dst_dir, os.path.basename(src)))

    # Copy JSONL journal
    if include_journal and os.path.exists(JOURNAL_PATH):
        shutil.copy2(JOURNAL_PATH, os.path.join(dst_dir, "journal.log"))

    # Integrity check on backup copy
    import sqlite3
    check = sqlite3.connect(dst_db).execute("PRAGMA integrity_check;").fetchone()[0]
    if check != "ok":
        print(f"ERROR: backup integrity failed: {check}", file=sys.stderr)
        sys.exit(1)

    print(f"Backup saved: {dst_dir}")
    return dst_dir


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default=None)
    parser.add_argument("--no-journal", action="store_true")
    parser.add_argument("--no-wal", action="store_true")
    args = parser.parse_args()
    backup(
        label=args.label,
        include_journal=not args.no_journal,
        include_wal=not args.no_wal,
    )
