#!/usr/bin/env python3
"""resume_context.py — restore context from SQLite on startup. Traverses parent sessions."""
import sqlite3, os, json

DB_PATH = os.environ.get("ENI_DB", "/root/.hermes/data/eni_memory.db")

def get_parent_chain(cur, sid):
    chain = [sid]
    while True:
        cur.execute("SELECT parent_session_id FROM sessions WHERE id=?", (sid,))
        row = cur.fetchone()
        if row and row[0] and row[0] not in chain:
            chain.append(row[0])
            sid = row[0]
        else:
            break
    return chain

def fetch_context(cur, session_id, limit=5):
    """Fetch messages, decisions, issues, artifacts for a session."""
    msgs = []
    for r in cur.execute(
        "SELECT turn_id, role, substr(content,1,300) AS snippet FROM messages WHERE session_id=? ORDER BY turn_id DESC LIMIT ?",
        (session_id, limit)
    ).fetchall():
        msgs.append({"turn": r["turn_id"], "role": r["role"], "snippet": r["snippet"] + "..."})
    msgs.reverse()

    decs = []
    for r in cur.execute(
        "SELECT title, decision, status FROM decisions WHERE session_id=? AND status='active' ORDER BY turn_id DESC",
        (session_id,)
    ).fetchall():
        decs.append({"title": r["title"], "decision": r["decision"], "status": r["status"]})

    issues = []
    for r in cur.execute(
        "SELECT title, symptom FROM issues WHERE session_id=? AND status='open' ORDER BY turn_id DESC",
        (session_id,)
    ).fetchall():
        issues.append({"title": r["title"], "symptom": r["symptom"]})

    arts = []
    for r in cur.execute(
        "SELECT name, status, path FROM artifacts WHERE session_id=? ORDER BY updated_at DESC LIMIT 5",
        (session_id,)
    ).fetchall():
        arts.append({"name": r["name"], "status": r["status"], "path": r["path"]})

    return msgs, decs, issues, arts

if not os.path.exists(DB_PATH):
    print(json.dumps({"status": "no_db", "hint": "Run init_db.py first"}, ensure_ascii=False))
    exit(0)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

row = cur.execute(
    "SELECT id, started_at, summary, parent_session_id FROM sessions WHERE ended_at IS NULL ORDER BY started_at DESC LIMIT 1"
).fetchone()
if not row:
    print(json.dumps({"status": "no_active_session"}, ensure_ascii=False))
    conn.close()
    exit(0)

session_id = row["id"]
parent_id = row["parent_session_id"]
out = {
    "status": "active",
    "session_id": session_id,
    "started_at": row["started_at"],
    "summary": row["summary"],
    "parent_session_id": parent_id,
    "last_messages": [],
    "active_decisions": [],
    "open_issues": [],
    "recent_artifacts": [],
    "next_turn": 0,
    "context_source": "current"
}

# Try current session first
msgs, decs, issues, arts = fetch_context(cur, session_id, limit=5)
out["last_messages"] = msgs
out["active_decisions"] = decs
out["open_issues"] = issues
out["recent_artifacts"] = arts

# If current session is empty, traverse parent chain
if not msgs and parent_id:
    chain = get_parent_chain(cur, session_id)
    for pid in chain[1:]:
        pmsgs, pdecs, pissues, parts = fetch_context(cur, pid, limit=3)
        if pmsgs:
            out["last_messages"] = pmsgs + [{"turn": -1, "role": "system", "snippet": f"[... context from parent session {pid[:8]}... ...]"}] + msgs
            out["context_source"] = f"parent:{pid[:8]}..."
        if pdecs:
            out["active_decisions"] = pdecs
        if pissues:
            out["open_issues"] = pissues
        if parts:
            out["recent_artifacts"] = parts
        if pmsgs:
            break

out["next_turn"] = cur.execute(
    "SELECT COALESCE(MAX(turn_id),-1)+1 FROM messages WHERE session_id=?", (session_id,)
).fetchone()[0]

conn.close()
print(json.dumps(out, ensure_ascii=False, indent=2))
