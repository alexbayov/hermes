"""Validate integrity on startup: check gaps, missing assistant turns, active session."""
import sys
from db_utils import get_conn, integrity_check


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


if __name__ == "__main__":
    ok = validate()
    sys.exit(0 if ok else 1)
