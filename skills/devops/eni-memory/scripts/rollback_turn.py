"""Undo last N turns: soft-delete decisions/artifacts, hard-delete messages."""
import sys
import argparse
from datetime import datetime
from db_utils import get_conn, tx, retry_on_lock


@retry_on_lock()
def rollback(session_id: str, turns: int = 1, dry_run: bool = False):
    conn = get_conn()

    # Identify last N turn_ids in this session
    rows = conn.execute(
        "SELECT DISTINCT turn_id FROM messages WHERE session_id = ? ORDER BY turn_id DESC LIMIT ?",
        (session_id, turns),
    ).fetchall()
    turn_ids = [r["turn_id"] for r in rows]

    if not turn_ids:
        print(f"No turns found for session {session_id}")
        return 0

    print(f"Rolling back {len(turn_ids)} turn(s) in session {session_id}: {turn_ids}")

    if dry_run:
        for tid in turn_ids:
            counts = {
                "messages": conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE session_id = ? AND turn_id = ?",
                    (session_id, tid),
                ).fetchone()[0],
                "decisions": conn.execute(
                    "SELECT COUNT(*) FROM decisions WHERE session_id = ? AND turn_id = ?",
                    (session_id, tid),
                ).fetchone()[0],
                "artifacts": conn.execute(
                    "SELECT COUNT(*) FROM artifacts WHERE session_id = ? AND turn_id = ?",
                    (session_id, tid),
                ).fetchone()[0],
                "issues": conn.execute(
                    "SELECT COUNT(*) FROM issues WHERE session_id = ? AND turn_id = ?",
                    (session_id, tid),
                ).fetchone()[0],
            }
            print(f"  turn {tid}: {counts}")
        return len(turn_ids)

    with tx(write=True) as conn:
        for tid in turn_ids:
            # Soft-delete decisions/artifacts (audit trail)
            conn.execute(
                "UPDATE decisions SET active = 0 WHERE session_id = ? AND turn_id = ?",
                (session_id, tid),
            )
            conn.execute(
                "UPDATE artifacts SET status = 'reverted' WHERE session_id = ? AND turn_id = ?",
                (session_id, tid),
            )
            # Hard-delete messages (actual content)
            conn.execute(
                "DELETE FROM messages WHERE session_id = ? AND turn_id = ?",
                (session_id, tid),
            )
            # Log rollback in op_log
            conn.execute(
                """
                INSERT INTO op_log (session_id, turn_id, op, table_name, row_id, old_value, new_value)
                VALUES (?, ?, 'delete', 'messages', ?, NULL, 'rolled_back')
                """,
                (session_id, tid, tid),
            )

        # Update message_count
        remaining = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id = ?",
            (session_id,),
        ).fetchone()[0]
        conn.execute(
            "UPDATE sessions SET message_count = ? WHERE id = ?",
            (remaining, session_id),
        )

    print(f"Rolled back {len(turn_ids)} turn(s). Messages remaining: {remaining}")
    return len(turn_ids)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", required=True, help="Session ID")
    parser.add_argument("--turns", type=int, default=1, help="Number of turns to roll back")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted")
    args = parser.parse_args()
    rollback(args.session, args.turns, args.dry_run)
