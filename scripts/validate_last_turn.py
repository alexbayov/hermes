#!/usr/bin/env python3
"""validate_last_turn.py — check integrity on startup. Call from resume ritual."""
import sqlite3, os, sys

DB_PATH = os.environ.get("ENI_DB", "/root/.hermes/data/eni_memory.db")

def main():
    if not os.path.exists(DB_PATH):
        print("[WARN] No DB found. Run init_db.py first.")
        sys.exit(1)

    with sqlite3.connect(DB_PATH) as c:
        sess = c.execute(
            "SELECT id, started_at, ended_at FROM sessions WHERE ended_at IS NULL ORDER BY started_at DESC LIMIT 1"
        ).fetchone()

        if not sess:
            print("[WARN] No active session. Previous session may not be closed.")
            sys.exit(1)

        sid = sess[0]
        row = c.execute("SELECT MAX(turn_id) FROM messages WHERE session_id=?", (sid,)).fetchone()
        last_turn = row[0] if row else None
        print(f"[OK] Active session {sid[:8]}..., last turn={last_turn}")

        # Check for gaps in turn sequence
        cur = c.cursor()
        cur.execute("SELECT turn_id FROM messages WHERE session_id=? ORDER BY turn_id", (sid,))
        turns = [r[0] for r in cur.fetchall()]
        if turns:
            mn, mx = min(turns), max(turns)
            gaps = [i for i in range(mn, mx+1) if i not in turns]
            if gaps:
                print(f"[WARN] Gap detected in turns: {gaps}. Session may have lost context.")
                sys.exit(1)

        # Check for unlogged turns (no user message at last turn — means assistant didn't log)
        cur.execute("SELECT turn_id, role FROM messages WHERE session_id=? ORDER BY turn_id DESC LIMIT 1", (sid,))
        last = cur.fetchone()
        if last and last[1] != 'assistant':
            print(f"[WARN] Last turn {last[0]} is role={last[1]}, not assistant. Final turn may not be logged.")
            sys.exit(1)

        print("[OK] Turn sequence intact. No gaps.")

if __name__ == '__main__':
    main()
