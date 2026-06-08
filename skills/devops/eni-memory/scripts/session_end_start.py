"""End current session and start new with parent linkage."""
import uuid
import argparse
from datetime import datetime
from db_utils import tx, get_conn


def session_end_start(end_summary: str = None, start_summary: str = None):
    conn = get_conn()

    active = conn.execute(
        "SELECT id FROM sessions WHERE status = 'active' ORDER BY started_at DESC LIMIT 1"
    ).fetchone()

    with tx(write=True) as conn:
        if active:
            conn.execute(
                "UPDATE sessions SET status = 'closed', ended_at = ?, summary = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), end_summary, active['id']),
            )
            print(f"Closed session: {active['id']}")
            parent_id = active['id']
        else:
            print("No active session to close")
            parent_id = None

        new_id = str(uuid.uuid4())[:8]
        conn.execute(
            """
            INSERT INTO sessions (id, parent_id, started_at, summary, status)
            VALUES (?, ?, ?, ?, 'active')
            """,
            (new_id, parent_id, datetime.utcnow().isoformat(), start_summary),
        )
        print(f"Started session: {new_id} (parent: {parent_id[:8] if parent_id else 'none'})")
        return new_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--end", action="store_true", help="Close active session")
    parser.add_argument("--start", action="store_true", help="Start new session")
    parser.add_argument("--summary", default=None, help="Summary for closed session")
    parser.add_argument("--new-summary", default=None, help="Summary for new session")
    args = parser.parse_args()

    if args.end or args.start:
        session_end_start(args.summary, args.new_summary)
    else:
        print("Use --end, --start, or both")
