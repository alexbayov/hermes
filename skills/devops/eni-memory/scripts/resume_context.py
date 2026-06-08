"""Resume context by traversing parent sessions with token budget."""
import sys
import json
from db_utils import get_conn

MAX_MESSAGES = 100
TOKEN_BUDGET = 8000


def resume_context(session_id: str = None, token_budget: int = TOKEN_BUDGET, max_messages: int = MAX_MESSAGES):
    conn = get_conn()

    if not session_id:
        active = conn.execute(
            "SELECT id FROM sessions WHERE status = 'active' ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if not active:
            print("No active session found")
            return []
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
    total_tokens = 0
    for sess in chain:
        rows = conn.execute(
            "SELECT role, content, tool_name, created_at, token_count FROM messages WHERE session_id = ? ORDER BY turn_id DESC",
            (sess['id'],)
        ).fetchall()
        for r in rows:
            if len(messages) >= max_messages:
                break
            tok = r['token_count'] or 0
            if total_tokens + tok > token_budget:
                print(f"  Token budget reached ({total_tokens}/{token_budget})")
                break
            total_tokens += tok
            messages.append(dict(r))
        if len(messages) >= max_messages or total_tokens >= token_budget:
            break

    messages.reverse()

    print(f"\nParent chain: {' -> '.join(s['id'][:8] for s in chain)}")
    print(f"Messages loaded: {len(messages)} (tokens: {total_tokens})")
    for m in messages[-5:]:
        prefix = f"[{m['role']}]"
        if m['tool_name']:
            prefix += f" ({m['tool_name']})"
        print(f"  {prefix}: {m['content'][:100]}")

    return messages


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", default=None)
    parser.add_argument("--token-budget", type=int, default=TOKEN_BUDGET)
    parser.add_argument("--max-messages", type=int, default=MAX_MESSAGES)
    args = parser.parse_args()
    resume_context(args.session, args.token_budget, args.max_messages)
