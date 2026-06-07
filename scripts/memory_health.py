#!/usr/bin/env python3
"""Memory health diagnostic: gaps, orphans, size, stats."""
import sqlite3, os, json, sys
from pathlib import Path

DB = Path('/root/.hermes/data/eni_memory.db')

def main():
    if not DB.exists():
        print("FAIL: DB not found")
        sys.exit(1)
    size = DB.stat().st_size
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    print(f"DB size: {size/1024:.1f} KB")
    print(f"DB path: {DB}")
    print()

    # sessions
    c.execute("SELECT id, started_at, status, parent_session_id FROM sessions ORDER BY started_at")
    sessions = {r['id']: dict(r) for r in c.fetchall()}
    print(f"Sessions: {len(sessions)}")
    for sid, s in sessions.items():
        print(f"  {sid[:8]}... | {s['status']} | started={s['started_at']} | parent={s['parent_session_id'][:8]+'...' if s['parent_session_id'] else 'None'}")
    print()

    # messages per session
    for sid in sessions:
        c.execute("SELECT COUNT(*), MIN(turn_id), MAX(turn_id) FROM messages WHERE session_id=?", (sid,))
        cnt, mn, mx = c.fetchone()
        c.execute("SELECT turn_id FROM messages WHERE session_id=? ORDER BY turn_id", (sid,))
        turns = [r[0] for r in c.fetchall()]
        gaps = [i for i in range(mn, mx+1) if i not in turns] if cnt else []
        print(f"Session {sid[:8]}... messages: {cnt}, turn range {mn}-{mx}, gaps: {gaps if gaps else 'None'}")
    print()

    # orphan checks
    for table in ('decisions', 'artifacts', 'issues'):
        c.execute(f"SELECT COUNT(*) FROM {table} WHERE session_id NOT IN (SELECT id FROM sessions)")
        orphans = c.fetchone()[0]
        print(f"Orphan {table}: {orphans}")
    print()

    # content stats
    c.execute("SELECT COUNT(*), SUM(LENGTH(content)), AVG(LENGTH(content)) FROM messages")
    cnt, total_len, avg_len = c.fetchone()
    print(f"Messages total: {cnt}")
    print(f"Total content: {total_len or 0} chars")
    print(f"Avg content: {avg_len:.0f} chars" if avg_len else "Avg content: 0")
    print()

    # decisions status
    c.execute("SELECT status, COUNT(*) FROM decisions GROUP BY status")
    for row in c.fetchall():
        print(f"Decisions {row[0]}: {row[1]}")
    print()

    # issues status
    c.execute("SELECT status, COUNT(*) FROM issues GROUP BY status")
    rows = c.fetchall()
    if rows:
        for row in rows:
            print(f"Issues {row[0]}: {row[1]}")
    else:
        print("Issues: None")
    print()

    # recommendations
    recs = []
    if any(gaps for sid in sessions for g in [[]]):
        # actually check gaps properly
        for sid in sessions:
            c.execute("SELECT turn_id FROM messages WHERE session_id=? ORDER BY turn_id", (sid,))
            turns = [r[0] for r in c.fetchall()]
            if turns:
                mn, mx = min(turns), max(turns)
                gaps = [i for i in range(mn, mx+1) if i not in turns]
                if gaps:
                    recs.append(f"Gap in turns for session {sid[:8]}...: {gaps}")
    if size > 10*1024*1024:
        recs.append("DB > 10MB, consider compaction")
    if not recs:
        recs.append("All checks passed")
    print("Recommendations:")
    for r in recs:
        print(f"  • {r}")
    print("\n✅ Health check complete")

if __name__ == '__main__':
    main()
