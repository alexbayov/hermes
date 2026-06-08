"""Compaction: archive old sessions to keep DB fast and small."""
import os
import sys
import argparse
from datetime import datetime
from db_utils import get_conn, tx, DB_PATH, integrity_check

TIER1_SESSION_COUNT = 10
TIER2_MESSAGE_COUNT = 2000
TIER2_KEEP_SESSIONS = 5
ARCHIVE_DIR = "/root/.hermes/data/archive"


def _summarize_session(conn, session_id: str) -> str:
    """Build a concise context_summary from session messages."""
    rows = conn.execute(
        "SELECT role, SUBSTR(content, 1, 200) AS snippet FROM messages WHERE session_id = ? ORDER BY turn_id",
        (session_id,),
    ).fetchall()
    if not rows:
        return ""
    parts = [f"{r['role']}: {r['snippet']}" for r in rows]
    return "\n".join(parts[:50])  # cap at 50 turns


def compact(
    tier1_sessions: int = TIER1_SESSION_COUNT,
    tier2_messages: int = TIER2_MESSAGE_COUNT,
    tier2_keep: int = TIER2_KEEP_SESSIONS,
    dry_run: bool = False,
):
    conn = get_conn()

    # --- Pre-checks ---
    if not integrity_check():
        print("ERROR: integrity_check failed", file=sys.stderr)
        sys.exit(1)

    total_messages = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    total_sessions = conn.execute("SELECT COUNT(*) FROM sessions WHERE status = 'closed'").fetchone()[0]
    print(f"Stats: {total_sessions} closed sessions, {total_messages} messages")

    if total_sessions <= tier1_sessions and total_messages <= tier2_messages:
        print("No compaction needed")
        return

    # --- Tier-1: if too many closed sessions, compact oldest ---
    compacted_ids = []
    if total_sessions > tier1_sessions:
        to_compact = conn.execute(
            """
            SELECT id FROM sessions
            WHERE status = 'closed'
            ORDER BY started_at DESC
            LIMIT -1 OFFSET ?
            """,
            (tier1_sessions,),
        ).fetchall()
        compacted_ids = [r["id"] for r in to_compact]
        print(f"Tier-1: compacting {len(compacted_ids)} sessions")

    # --- Tier-2: if too many messages, archive oldest beyond keep window ---
    archived_ids = []
    if total_messages > tier2_messages:
        keep_ids = [
            r["id"]
            for r in conn.execute(
                """
                SELECT id FROM sessions
                WHERE status IN ('active', 'closed')
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (tier2_keep,),
            ).fetchall()
        ]
        to_archive = conn.execute(
            """
            SELECT id FROM sessions
            WHERE status = 'closed' AND id NOT IN ({placeholders})
            ORDER BY started_at ASC
            """.format(placeholders=",".join(["?"] * len(keep_ids))),
            keep_ids,
        ).fetchall()
        archived_ids = [r["id"] for r in to_archive]
        print(f"Tier-2: archiving {len(archived_ids)} sessions (keep {tier2_keep})")

    if not compacted_ids and not archived_ids:
        print("Nothing to do")
        return

    if dry_run:
        print(f"DRY-RUN: would compact {compacted_ids}, archive {archived_ids}")
        return

    # --- Run compaction inside transaction ---
    with tx(write=True) as conn:
        run_id = conn.execute(
            """
            INSERT INTO compaction_runs (started_at, status)
            VALUES (datetime('now'), 'running')
            RETURNING id
            """
        ).fetchone()["id"]

        for sid in compacted_ids:
            summary = _summarize_session(conn, sid)
            conn.execute(
                "UPDATE sessions SET status = 'compacted', context_summary = ? WHERE id = ?",
                (summary, sid),
            )
            # Optionally archive messages to JSONL before deletion
            # For now, we keep decisions/artifacts/issues but drop messages
            conn.execute("DELETE FROM messages WHERE session_id = ?", (sid,))

        for sid in archived_ids:
            summary = _summarize_session(conn, sid)
            conn.execute(
                "UPDATE sessions SET status = 'archived', context_summary = ? WHERE id = ?",
                (summary, sid),
            )
            conn.execute("DELETE FROM messages WHERE session_id = ?", (sid,))

        # Finalize run
        conn.execute(
            """
            UPDATE compaction_runs
            SET ended_at = datetime('now'),
                sessions_compacted = ?,
                messages_archived = ?,
                status = 'success'
            WHERE id = ?
            """,
            (len(compacted_ids) + len(archived_ids), 0, run_id),  # messages_archived not tracked per row
        )

    print(f"Compaction complete: {len(compacted_ids)} compacted, {len(archived_ids)} archived")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier1-sessions", type=int, default=TIER1_SESSION_COUNT)
    parser.add_argument("--tier2-messages", type=int, default=TIER2_MESSAGE_COUNT)
    parser.add_argument("--tier2-keep", type=int, default=TIER2_KEEP_SESSIONS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    compact(
        tier1_sessions=args.tier1_sessions,
        tier2_messages=args.tier2_messages,
        tier2_keep=args.tier2_keep,
        dry_run=args.dry_run,
    )
