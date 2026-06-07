#!/usr/bin/env python3
"""persist.py — unified logging for ENI turns, decisions, artifacts, issues."""
import sqlite3, os, argparse, json, datetime, uuid

DB_PATH = os.environ.get("ENI_DB", "/root/.hermes/data/eni_memory.db")

def _conn():
    return sqlite3.connect(DB_PATH)

def log_turn(session_id, turn_id, role, content, tool_name=None, tool_result=None, token_count=None):
    with _conn() as c:
        c.execute(
            """INSERT INTO messages (session_id, turn_id, role, content, tool_name, tool_result, token_count)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(session_id, turn_id) DO UPDATE SET
               content=excluded.content, tool_name=excluded.tool_name,
               tool_result=excluded.tool_result, token_count=excluded.token_count""",
            (session_id, turn_id, role, content, tool_name, tool_result, token_count)
        )

def log_decision(session_id, turn_id, title, decision, rationale=None, rejected=None):
    with _conn() as c:
        c.execute(
            "INSERT INTO decisions (session_id, turn_id, title, decision, rationale, rejected) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, turn_id, title, decision, rationale, rejected)
        )

def log_artifact(session_id, turn_id, name, path, type_, status="draft", description=None):
    with _conn() as c:
        c.execute(
            """INSERT INTO artifacts (session_id, turn_id, name, path, type, status, description)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (session_id, turn_id, name, path, type_, status, description)
        )

def log_issue(session_id, turn_id, title, symptom, root_cause=None, fix=None, status="open"):
    with _conn() as c:
        c.execute(
            """INSERT INTO issues (session_id, turn_id, title, symptom, root_cause, fix, status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (session_id, turn_id, title, symptom, root_cause, fix, status)
        )

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--session", required=True)
    p.add_argument("--turn", type=int, required=True)
    p.add_argument("--role", choices=["user","assistant","tool","system"])
    p.add_argument("--content")
    p.add_argument("--tool-name")
    p.add_argument("--tool-result")
    p.add_argument("--token-count", type=int)
    p.add_argument("--decision-title")
    p.add_argument("--decision")
    p.add_argument("--rationale")
    p.add_argument("--rejected")
    p.add_argument("--artifact-name")
    p.add_argument("--artifact-path")
    p.add_argument("--artifact-type", default="file")
    p.add_argument("--artifact-status", default="draft")
    p.add_argument("--artifact-desc")
    p.add_argument("--issue-title")
    p.add_argument("--symptom")
    p.add_argument("--root-cause")
    p.add_argument("--fix")
    p.add_argument("--issue-status", default="open")
    args = p.parse_args()

    if args.role and args.content is not None:
        log_turn(args.session, args.turn, args.role, args.content, args.tool_name, args.tool_result, args.token_count)
        print(f"OK turn={args.turn} role={args.role}")
    if args.decision_title:
        log_decision(args.session, args.turn, args.decision_title, args.decision or "", args.rationale, args.rejected)
        print(f"OK decision={args.decision_title}")
    if args.artifact_name:
        log_artifact(args.session, args.turn, args.artifact_name, args.artifact_path or "", args.artifact_type, args.artifact_status, args.artifact_desc)
        print(f"OK artifact={args.artifact_name}")
    if args.issue_title:
        log_issue(args.session, args.turn, args.issue_title, args.symptom or "", args.root_cause, args.fix, args.issue_status)
        print(f"OK issue={args.issue_title}")
