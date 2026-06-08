"""Validate integrity on startup: check gaps, missing assistant turns, active session.
Optional --repair replays missing turns from journal.log."""
import json
import sys
import argparse
from typing import Optional
from db_utils import get_conn, integrity_check, retry_on_lock, tx

JOURNAL_PATH = "/root/.hermes/data/journal.log"


def validate():
    conn = get_conn()
    ok = True

    if not integrity_check():
        print("ERROR: integrity_check failed", file=sys.stderr)
        ok = False

    active = conn.execute(
        "SELECT id FROM sessions WHERE status = 'active'"
    ).fetchall()
    if len(active) > 1:
        print(f"WARNING: {len(active)} active sessions found", file=sys.stderr)
        ok = False
    elif len(active) == 1:
        print(f"OK: active session {active[0]['id']}")
    else:
        print("INFO: no active session")

    if active:
        sid = active[0]['id']
        last_turn = conn.execute(
            "SELECT MAX(turn_id) FROM messages WHERE session_id = ?", (sid,)
        ).fetchone()[0]
        if last_turn:
            has_assistant = conn.execute(
                "SELECT 1 FROM messages WHERE session_id = ? AND turn_id = ? AND role = 'assistant' LIMIT 1",
                (sid, last_turn)
            ).fetchone()
            if not has_assistant:
                print(f"WARNING: turn {last_turn} missing assistant response", file=sys.stderr)
                ok = False
            else:
                print(f"OK: turn {last_turn} complete")
        else:
            print("INFO: no messages in active session")

    return ok


def _read_journal():
    """Yield JSONL entries in reverse order (newest first)."""
    try:
        with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue
    except FileNotFoundError:
        return


@retry_on_lock()
def repair(session_id: Optional[str] = None):
    """Backfill missing turns from journal.log into SQLite."""
    conn = get_conn()
    if not session_id:
        active = conn.execute(
            "SELECT id FROM sessions WHERE status = 'active' LIMIT 1"
        ).fetchone()
        if not active:
            print("ERROR: no active session and --session not provided", file=sys.stderr)
            return False
        session_id = active['id']

    # Find existing turns for this session
    existing = set(
        row[0] for row in
        conn.execute("SELECT turn_id FROM messages WHERE session_id = ?", (session_id,)).fetchall()
    )

    # Find missing turns from journal
    missing = []
    for entry in _read_journal():
        if entry.get("session_id") != session_id:
            continue
        turn = entry.get("turn_id")
        if turn is not None and turn not in existing:
            missing.append(entry)
            existing.add(turn)

    if not missing:
        print("INFO: no missing turns to repair")
        return True

    # Replay in chronological order
    missing.sort(key=lambda e: e.get("turn_id", 0))
    print(f"REPAIR: replaying {len(missing)} missing turns from journal.log")

    with tx(write=True) as conn:
        for entry in missing:
            turn = entry.get("turn_id")
            role = entry.get("role")
            content = entry.get("content")
            if turn is None or role is None or content is None:
                continue
            conn.execute(
                """
                INSERT INTO messages (session_id, turn_id, role, content, token_count, tool_name, tool_result)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, turn_id, role) DO UPDATE SET
                    content = excluded.content,
                    token_count = excluded.token_count,
                    tool_name = excluded.tool_name,
                    tool_result = excluded.tool_result
                """,
                (session_id, turn, role, content,
                 entry.get("token_count"), entry.get("tool_name"), entry.get("tool_result")),
            )
            conn.execute(
                "UPDATE sessions SET message_count = message_count + 1 WHERE id = ?",
                (session_id,),
            )

    print(f"REPAIR: replayed {len(missing)} turns")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repair", action="store_true", help="Replay missing turns from journal.log")
    parser.add_argument("--session", default=None, help="Session ID to repair (default: active session)")
    args = parser.parse_args()

    if args.repair:
        ok = repair(args.session)
        sys.exit(0 if ok else 1)
    else:
        ok = validate()
        sys.exit(0 if ok else 1)
