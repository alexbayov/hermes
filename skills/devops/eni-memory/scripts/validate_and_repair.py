#!/usr/bin/env python3
"""Validate DB against journal.log and backfill missing turns idempotently.

Reads journal.log newest-first, deduplicates by identity key, checks DB existence,
backfills missing rows, logs REPAIR-{turn_id} issues. Supports both old (string)
and new (dict) journal formats for decisions/artifacts/issues.
"""
import argparse
import json
import os
import sqlite3
import sys
from collections import OrderedDict
from datetime import datetime

from db_utils import get_conn, DB_PATH, retry_on_lock, tx

JOURNAL_PATH = "/root/.hermes/data/journal.log"

# Identity keys per action: (table, unique_columns, db_columns)
ACTIONS = {
    "message": {
        "table": "messages",
        "identity": ["session_id", "turn_id", "role"],
        "db_cols": ["session_id", "turn_id", "role", "content", "token_count", "tool_name", "tool_result", "created_at"],
    },
    "decision": {
        "table": "decisions",
        "identity": ["session_id", "turn_id", "title"],
        "db_cols": ["session_id", "turn_id", "title", "choice", "rationale", "rejected", "active", "created_at"],
    },
    "artifact": {
        "table": "artifacts",
        "identity": ["session_id", "turn_id", "name"],
        "db_cols": ["session_id", "turn_id", "name", "path", "type", "status", "description", "created_at"],
    },
    "issue": {
        "table": "issues",
        "identity": ["session_id", "turn_id", "title"],
        "db_cols": ["session_id", "turn_id", "title", "symptom", "root_cause", "fix", "status", "created_at"],
    },
}


def read_journal_reversed(path: str):
    """Yield parsed JSON objects from journal.log newest-first."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def _identity_key(action: str, entry: dict) -> tuple:
    """Build identity tuple for deduplication."""
    ident = ACTIONS[action]["identity"]
    vals = [entry.get(k) for k in ident]
    return tuple(vals)


def _row_exists(conn, action: str, entry: dict) -> bool:
    """Check if a row with this identity already exists in the DB."""
    cfg = ACTIONS[action]
    table = cfg["table"]
    ident_cols = cfg["identity"]
    where = " AND ".join(f"{c} = ?" for c in ident_cols)
    vals = [entry.get(c) for c in ident_cols]
    cur = conn.execute(f"SELECT 1 FROM {table} WHERE {where} LIMIT 1", vals)
    return cur.fetchone() is not None


def _collect_missing(session_id: str, journal_path: str = JOURNAL_PATH):
    """Walk journal newest->oldest; collect missing entries per session."""
    seen_keys = set()
    to_insert = []
    conn = get_conn()
    for entry in read_journal_reversed(journal_path):
        if not isinstance(entry, dict):
            continue
        if entry.get("session_id") != session_id:
            continue

        # Determine action types (one journal entry may contain multiple actions)
        actions_found = []
        if entry.get("role"):
            actions_found.append("message")
        if entry.get("decision"):
            actions_found.append("decision")
        if entry.get("artifact"):
            actions_found.append("artifact")
        if entry.get("issue"):
            actions_found.append("issue")
        if not actions_found:
            continue

        for action in actions_found:
            if action not in ACTIONS:
                continue

            # Build flat entry for DB insertion
            flat = {
                "session_id": entry.get("session_id"),
                "turn_id": entry.get("turn_id"),
            }
            if action == "message":
                flat["role"] = entry.get("role")
                flat["content"] = entry.get("content")
                flat["token_count"] = entry.get("token_count")
                flat["tool_name"] = entry.get("tool_name")
                flat["tool_result"] = entry.get("tool_result")
                flat["created_at"] = entry.get("ts", datetime.utcnow().isoformat())
            elif action == "decision":
                dec = entry.get("decision")
                if isinstance(dec, dict):
                    flat["title"] = dec.get("title")
                    flat["choice"] = dec.get("choice")
                    flat["rationale"] = dec.get("rationale")
                    flat["rejected"] = dec.get("rejected")
                else:
                    flat["title"] = dec
                    flat["choice"] = flat["rationale"] = flat["rejected"] = None
                flat["active"] = 1
                flat["created_at"] = entry.get("ts", datetime.utcnow().isoformat())
            elif action == "artifact":
                art = entry.get("artifact")
                if isinstance(art, dict):
                    flat["name"] = art.get("name")
                    flat["path"] = art.get("path")
                    flat["type"] = art.get("type")
                    flat["status"] = art.get("status")
                    flat["description"] = art.get("description")
                else:
                    flat["name"] = art
                    flat["path"] = flat["type"] = flat["status"] = flat["description"] = None
                flat["created_at"] = entry.get("ts", datetime.utcnow().isoformat())
            elif action == "issue":
                iss = entry.get("issue")
                if isinstance(iss, dict):
                    flat["title"] = iss.get("title")
                    flat["symptom"] = iss.get("symptom")
                    flat["root_cause"] = iss.get("root_cause")
                    flat["fix"] = iss.get("fix")
                    flat["status"] = iss.get("status")
                else:
                    flat["title"] = iss
                    flat["symptom"] = flat["root_cause"] = flat["fix"] = flat["status"] = None
                flat["created_at"] = entry.get("ts", datetime.utcnow().isoformat())

            # Deduplicate by identity key (newest wins)
            key = (action, _identity_key(action, flat))
            if key in seen_keys:
                continue
            seen_keys.add(key)

            # Skip if already in DB
            if _row_exists(conn, action, flat):
                continue

            to_insert.append((action, flat))
    return to_insert


def _insert_row(conn, action: str, flat: dict, dry: bool) -> bool:
    """Insert one row idempotently. Returns True if inserted."""
    cfg = ACTIONS[action]
    table = cfg["table"]
    cols = cfg["db_cols"]
    data = {c: flat.get(c) for c in cols if c in flat}
    if not data:
        return False

    fields = ", ".join(data.keys())
    marks = ", ".join("?" for _ in data)
    # Build ON CONFLICT clause using identity columns
    ident = cfg["identity"]
    conflict_target = ", ".join(ident)
    updates = ", ".join(f"{c} = excluded.{c}" for c in data if c not in ident)
    if updates:
        sql = f"INSERT INTO {table} ({fields}) VALUES ({marks}) ON CONFLICT({conflict_target}) DO UPDATE SET {updates}"
    else:
        sql = f"INSERT INTO {table} ({fields}) VALUES ({marks}) ON CONFLICT({conflict_target}) DO NOTHING"

    if dry:
        return True
    cur = conn.execute(sql, tuple(data.values()))
    return cur.rowcount > 0


def _log_repair(conn, session_id: str, turn_id: int, counts: dict, dry: bool):
    """Insert a REPAIR-{turn_id} issue record."""
    summary = ", ".join(f"{n} {k}(s)" for k, n in counts.items() if n > 0)
    if not summary:
        summary = "no missing rows"
    row = {
        "session_id": session_id,
        "turn_id": turn_id,
        "title": f"REPAIR-{turn_id}",
        "symptom": "missing rows detected from journal.log",
        "root_cause": "journal had entries not present in DB",
        "fix": summary,
        "status": "fixed",
        "created_at": datetime.utcnow().isoformat(),
    }
    return _insert_row(conn, "issue", row, dry)


@retry_on_lock()
def repair(session_id: str, journal_path: str = JOURNAL_PATH, dry: bool = False) -> dict:
    """Backfill missing entries and log REPAIR issues. Returns counts."""
    to_insert = _collect_missing(session_id, journal_path)
    if not to_insert:
        print("INFO: no missing entries to repair")
        return {}

    # Insert oldest-first to preserve chronological order in DB
    to_insert.reverse()

    counts = {"message": 0, "decision": 0, "artifact": 0, "issue": 0}
    per_turn = OrderedDict()

    with tx(write=True) as conn:
        for action, flat in to_insert:
            if _insert_row(conn, action, flat, dry):
                counts[action] += 1
                turn = flat.get("turn_id")
                per_turn.setdefault(turn, {}).setdefault(action, 0)
                per_turn[turn][action] += 1

        # Log REPAIR issue per affected turn
        for turn_id, breakdown in per_turn.items():
            _log_repair(conn, session_id, turn_id, breakdown, dry)

    action = "Would repair" if dry else "Repaired"
    print(f"{action} for session '{session_id}':")
    print(f"  messages:  {counts['message']}")
    print(f"  decisions: {counts['decision']}")
    print(f"  artifacts: {counts['artifact']}")
    print(f"  issues:    {counts['issue']}")
    print(f"  REPAIR issues logged: {len(per_turn)}")
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-id", required=True, help="Session ID to validate/repair")
    parser.add_argument("--journal", default=JOURNAL_PATH, help="Path to journal.log")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be repaired without writing")
    args = parser.parse_args()

    repair(args.session_id, args.journal, dry=args.dry_run)
