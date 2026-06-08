#!/usr/bin/env python3
"""Idempotent SQLite triggers for op_log audit."""

import sqlite3
import os
import sys

DB_PATH = os.path.expanduser('~/.hermes/data/eni_memory.db')

TABLES = {
    'messages': ['id', 'session_id', 'turn_id', 'role', 'content', 'token_count', 'tool_name', 'tool_result', 'created_at'],
    'decisions': ['id', 'session_id', 'turn_id', 'title', 'choice', 'rationale', 'rejected', 'active', 'created_at'],
    'artifacts': ['id', 'session_id', 'turn_id', 'name', 'path', 'type', 'status', 'description', 'created_at'],
    'issues': ['id', 'session_id', 'turn_id', 'title', 'symptom', 'root_cause', 'fix', 'status', 'created_at'],
}


def build_json_object(prefix: str, cols: list) -> str:
    """Build json_object call for prefix (NEW or OLD) and column list."""
    parts = []
    for col in cols:
        parts.append(f"'{col}', {prefix}.{col}")
    return f"json_object({', '.join(parts)})"


def apply_triggers(db_path: str = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Ensure op_log exists (backward compat)
    c.execute('''
        CREATE TABLE IF NOT EXISTS op_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            turn_id INTEGER,
            op TEXT,
            table_name TEXT,
            row_id INTEGER,
            old_value TEXT,
            new_value TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    ''')

    for table, cols in TABLES.items():
        has_session_id = 'session_id' in cols
        has_turn_id = 'turn_id' in cols

        session_id_insert = "NEW.session_id" if has_session_id else "NULL"
        turn_id_insert = "NEW.turn_id" if has_turn_id else "NULL"
        session_id_update = "NEW.session_id" if has_session_id else "NULL"
        turn_id_update = "NEW.turn_id" if has_turn_id else "NULL"
        session_id_delete = "OLD.session_id" if has_session_id else "NULL"
        turn_id_delete = "OLD.turn_id" if has_turn_id else "NULL"

        new_json = build_json_object("NEW", cols)
        old_json = build_json_object("OLD", cols)

        for suffix in ['_ai', '_au', '_ad']:
            c.execute(f"DROP TRIGGER IF EXISTS {table}{suffix}")

        c.execute(f'''
            CREATE TRIGGER {table}_ai AFTER INSERT ON {table} BEGIN
                INSERT INTO op_log (session_id, turn_id, op, table_name, row_id, new_value)
                VALUES ({session_id_insert}, {turn_id_insert}, 'insert', '{table}', NEW.id, {new_json});
            END
        ''')

        c.execute(f'''
            CREATE TRIGGER {table}_au AFTER UPDATE ON {table} BEGIN
                INSERT INTO op_log (session_id, turn_id, op, table_name, row_id, old_value, new_value)
                VALUES ({session_id_update}, {turn_id_update}, 'update', '{table}', NEW.id, {old_json}, {new_json});
            END
        ''')

        c.execute(f'''
            CREATE TRIGGER {table}_ad AFTER DELETE ON {table} BEGIN
                INSERT INTO op_log (session_id, turn_id, op, table_name, row_id, old_value)
                VALUES ({session_id_delete}, {turn_id_delete}, 'delete', '{table}', OLD.id, {old_json});
            END
        ''')

    conn.commit()
    conn.close()
    print("Triggers applied successfully.")


if __name__ == '__main__':
    apply_triggers()
