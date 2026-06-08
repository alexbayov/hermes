"""Unified turn logging with SQLite + JSONL dual-write."""
import json
import os
import sys
import argparse
from datetime import datetime
from db_utils import tx, get_conn, DB_PATH, retry_on_lock

JOURNAL_PATH = "/root/.hermes/data/journal.log"


def _journal(data: dict):
    with open(JOURNAL_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, default=str) + "\n")
        f.flush()
        os.fsync(f.fileno())


def persist(
    session: str,
    turn: int,
    role: str,
    content: str,
    token_count: int = None,
    tool_name: str = None,
    tool_result: str = None,
    decision_title: str = None,
    decision: str = None,
    rationale: str = None,
    rejected: str = None,
    artifact_name: str = None,
    artifact_path: str = None,
    artifact_type: str = None,
    artifact_status: str = None,
    artifact_desc: str = None,
    issue_title: str = None,
    symptom: str = None,
    root_cause: str = None,
    fix: str = None,
    issue_status: str = None,
):
    @retry_on_lock()
    def _insert():
        with tx(write=True) as conn:
            # Insert message
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
                (session, turn, role, content, token_count, tool_name, tool_result),
            )

            # Increment message_count on session
            conn.execute(
                "UPDATE sessions SET message_count = message_count + 1 WHERE id = ?",
                (session,),
            )

            # Insert decision if present
            if decision_title:
                conn.execute(
                    """
                    INSERT INTO decisions (session_id, turn_id, title, choice, rationale, rejected)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (session, turn, decision_title, decision, rationale, rejected),
                )

            # Insert artifact if present
            if artifact_name:
                conn.execute(
                    """
                    INSERT INTO artifacts (session_id, turn_id, name, path, type, status, description)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (session, turn, artifact_name, artifact_path, artifact_type, artifact_status, artifact_desc),
                )

            # Insert issue if present
            if issue_title:
                conn.execute(
                    """
                    INSERT INTO issues (session_id, turn_id, title, symptom, root_cause, fix, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (session, turn, issue_title, symptom, root_cause, fix, issue_status),
                )

    _insert()

    # JSONL journal (always append, never update)
    journal_entry = {
        "ts": datetime.utcnow().isoformat(),
        "session_id": session,
        "turn_id": turn,
        "role": role,
        "content": content,
        "token_count": token_count,
        "tool_name": tool_name,
        "tool_result": tool_result,
    }
    if decision_title:
        journal_entry["decision"] = {
            "title": decision_title,
            "choice": decision,
            "rationale": rationale,
            "rejected": rejected,
        }
    if artifact_name:
        journal_entry["artifact"] = {
            "name": artifact_name,
            "path": artifact_path,
            "type": artifact_type,
            "status": artifact_status,
            "description": artifact_desc,
        }
    if issue_title:
        journal_entry["issue"] = {
            "title": issue_title,
            "symptom": symptom,
            "root_cause": root_cause,
            "fix": fix,
            "status": issue_status,
        }
    _journal({k: v for k, v in journal_entry.items() if v is not None})

    print(f"Persisted turn {turn} for session {session}")


@retry_on_lock()
def repair_all():
    """Replay entire journal.log into SQLite (deduplicated)."""
    if not os.path.exists(JOURNAL_PATH):
        print("INFO: journal.log not found, nothing to repair")
        return True

    with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()

    entries = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if not entries:
        print("INFO: journal.log empty, nothing to repair")
        return True

    # Deduplicate by (session_id, turn_id, role)
    seen = set()
    deduped = []
    for entry in entries:
        key = (entry.get("session_id"), entry.get("turn_id"), entry.get("role"))
        if key not in seen and all(k is not None for k in key):
            seen.add(key)
            deduped.append(entry)

    print(f"REPAIR: replaying {len(deduped)} unique journal entries")

    with tx(write=True) as conn:
        for entry in deduped:
            session = entry.get("session_id")
            turn = entry.get("turn_id")
            role = entry.get("role")
            content = entry.get("content")
            if session is None or turn is None or role is None or content is None:
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
                (session, turn, role, content,
                 entry.get("token_count"), entry.get("tool_name"), entry.get("tool_result")),
            )

            # Upsert decision (new format: dict, old format: string fallback)
            dec = entry.get("decision")
            if dec:
                if isinstance(dec, dict):
                    conn.execute(
                        """
                        INSERT INTO decisions (session_id, turn_id, title, choice, rationale, rejected)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(session_id, turn_id) DO UPDATE SET
                            title = excluded.title,
                            choice = excluded.choice,
                            rationale = excluded.rationale,
                            rejected = excluded.rejected
                        """,
                        (session, turn, dec.get("title"), dec.get("choice"), dec.get("rationale"), dec.get("rejected")),
                    )
                else:
                    # Old format: just title string
                    conn.execute(
                        """
                        INSERT INTO decisions (session_id, turn_id, title)
                        VALUES (?, ?, ?)
                        ON CONFLICT(session_id, turn_id) DO UPDATE SET title = excluded.title
                        """,
                        (session, turn, dec),
                    )

            # Upsert artifact (new format: dict, old format: string fallback)
            art = entry.get("artifact")
            if art:
                if isinstance(art, dict):
                    conn.execute(
                        """
                        INSERT INTO artifacts (session_id, turn_id, name, path, type, status, description)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(session_id, turn_id) DO UPDATE SET
                            name = excluded.name,
                            path = excluded.path,
                            type = excluded.type,
                            status = excluded.status,
                            description = excluded.description
                        """,
                        (session, turn, art.get("name"), art.get("path"), art.get("type"), art.get("status"), art.get("description")),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO artifacts (session_id, turn_id, name)
                        VALUES (?, ?, ?)
                        ON CONFLICT(session_id, turn_id) DO UPDATE SET name = excluded.name
                        """,
                        (session, turn, art),
                    )

            # Upsert issue (new format: dict, old format: string fallback)
            iss = entry.get("issue")
            if iss:
                if isinstance(iss, dict):
                    conn.execute(
                        """
                        INSERT INTO issues (session_id, turn_id, title, symptom, root_cause, fix, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(session_id, turn_id) DO UPDATE SET
                            title = excluded.title,
                            symptom = excluded.symptom,
                            root_cause = excluded.root_cause,
                            fix = excluded.fix,
                            status = excluded.status
                        """,
                        (session, turn, iss.get("title"), iss.get("symptom"), iss.get("root_cause"), iss.get("fix"), iss.get("status")),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO issues (session_id, turn_id, title)
                        VALUES (?, ?, ?)
                        ON CONFLICT(session_id, turn_id) DO UPDATE SET title = excluded.title
                        """,
                        (session, turn, iss),
                    )

            # Update message_count
            conn.execute(
                """
                UPDATE sessions SET message_count = (
                    SELECT COUNT(*) FROM messages WHERE session_id = ?
                ) WHERE id = ?
                """,
                (session, session),
            )

    print(f"REPAIR: replayed {len(deduped)} entries")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repair", action="store_true", help="Replay full journal.log into SQLite")
    parser.add_argument("--session", required=False)
    parser.add_argument("--turn", type=int)
    parser.add_argument("--role", choices=["user", "assistant", "tool", "system"])
    parser.add_argument("--content")
    parser.add_argument("--token-count", type=int)
    parser.add_argument("--tool-name")
    parser.add_argument("--tool-result")
    parser.add_argument("--decision-title")
    parser.add_argument("--decision")
    parser.add_argument("--rationale")
    parser.add_argument("--rejected")
    parser.add_argument("--artifact-name")
    parser.add_argument("--artifact-path")
    parser.add_argument("--artifact-type")
    parser.add_argument("--artifact-status")
    parser.add_argument("--artifact-desc")
    parser.add_argument("--issue-title")
    parser.add_argument("--symptom")
    parser.add_argument("--root-cause")
    parser.add_argument("--fix")
    parser.add_argument("--issue-status")
    args = parser.parse_args()

    if args.repair:
        ok = repair_all()
        sys.exit(0 if ok else 1)
    else:
        if not args.session or args.turn is None or not args.role or not args.content:
            parser.error("--session, --turn, --role, --content are required (unless --repair)")
        persist(
            session=args.session,
            turn=args.turn,
            role=args.role,
            content=args.content,
            token_count=args.token_count,
            tool_name=args.tool_name,
            tool_result=args.tool_result,
            decision_title=args.decision_title,
            decision=args.decision,
            rationale=args.rationale,
            rejected=args.rejected,
            artifact_name=args.artifact_name,
            artifact_path=args.artifact_path,
            artifact_type=args.artifact_type,
            artifact_status=args.artifact_status,
            artifact_desc=args.artifact_desc,
            issue_title=args.issue_title,
            symptom=args.symptom,
            root_cause=args.root_cause,
            fix=args.fix,
            issue_status=args.issue_status,
        )
