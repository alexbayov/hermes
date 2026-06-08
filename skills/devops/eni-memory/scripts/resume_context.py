"""Resume context by traversing parent sessions."""
import sys
import json
from db_utils import get_conn

MAX_MESSAGES = 100


def resume_context(session_id: str = None):
    conn = get_conn()

    if not session_id:
        active = conn.execute(
            "SELECT id FROM sessions WHERE status = 'active' ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if not active:
            print("No active session found")
            return
        session_id = active['id']

    print(f"Resuming session: {session_id}")

    chain = []
    sid = session_id
    while sid:
        sess = conn.execute(
            "SELECT id, parent_id, context_summary, status FROM sessions WHERE id = ?",
            (sid,)
        ).fetchone()
        if not sess:
            break
        chain.append(sess)
        sid = sess['parent_id']

    messages = []
    for sess in chain:
        rows = conn.execute(
            "SELECT role, content, tool_name, created_at FROM messages WHERE session_id = ? ORDER BY turn_id DESC",
            (sess['id'],)
        ).fetchall()
        for r in rows:
            if len(messages) >= MAX_MESSAGES:
                break
            messages.append(dict(r))
        if len(messages) >= MAX_MESSAGES:
            break

    messages.reverse()

    print(f"\nParent chain: {' -> '.join(s['id'][:8] for s in chain)}")
    print(f"Messages loaded: {len(messages)}")
    for m in messages[-5:]:
        prefix = f"[{m['role']}]"
        if m['tool_name']:
            prefix += f" ({m['tool_name']})"
        print(f"  {prefix}: {m['content'][:100]}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", default=None)
    args = parser.parse_args()
    resume_context(args.session)
