#!/usr/bin/env python3
"""End current session and start a new one with parent linkage. Call on reboot / compaction."""
import sqlite3, uuid, datetime, argparse, sys, os

DB = os.environ.get("ENI_DB", "/root/.hermes/data/eni_memory.db")

def main():
    p = argparse.ArgumentParser(description="End current session and/or start new one")
    p.add_argument('--end', action='store_true', help='End current active session')
    p.add_argument('--start', action='store_true', help='Start new session with parent link')
    p.add_argument('--summary', help='Summary for ended session')
    p.add_argument('--new-summary', help='Summary for new session')
    args = p.parse_args()

    if not (args.end or args.start):
        p.print_help()
        sys.exit(1)

    conn = sqlite3.connect(DB)
    c = conn.cursor()

    parent_id = None
    if args.end:
        c.execute("SELECT id FROM sessions WHERE ended_at IS NULL ORDER BY started_at DESC LIMIT 1")
        row = c.fetchone()
        if row:
            parent_id = row[0]
            now = datetime.datetime.now().isoformat()
            c.execute("UPDATE sessions SET ended_at=?, summary=?, status='closed' WHERE id=?",
                      (now, args.summary or None, parent_id))
            conn.commit()
            print(f"[OK] Closed session {parent_id[:8]}...")
        else:
            print("[WARN] No active session to close.")

    if args.start:
        new_id = str(uuid.uuid4())
        now = datetime.datetime.now().isoformat()
        c.execute(
            "INSERT INTO sessions (id, started_at, status, parent_session_id, summary) VALUES (?, ?, ?, ?, ?)",
            (new_id, now, 'active', parent_id, args.new_summary or None)
        )
        conn.commit()
        print(f"[OK] Started new session {new_id[:8]}... (parent={parent_id[:8]+'...' if parent_id else 'None'})")

    conn.close()

if __name__ == '__main__':
    main()
