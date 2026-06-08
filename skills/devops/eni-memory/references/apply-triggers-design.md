# apply_triggers.py Design Notes

## Origin
Designed by Victor (claude4_7_opus) via direct endpoint `127.0.0.1:8799/v1/chat/completions` on 2025-06-08.
Question: "How do I write SQLite AFTER INSERT/UPDATE/DELETE triggers that capture old/new row values into a generic audit_log table?"
Response time: 204.7 seconds.

## Architecture
- Idempotent: drops existing triggers (`_ai`, `_au`, `_ad` suffixes) before recreating
- Targets: `messages`, `decisions`, `artifacts`, `issues` (not `sessions` — no `session_id`/`turn_id` FK)
- Uses `json_object()` (SQLite 3.38+) for structured snapshots of all columns
- `op_log` table receives: `session_id`, `turn_id`, `op` (lowercase!), `table_name`, `row_id`, `old_value` (DELETE/UPDATE), `new_value` (INSERT/UPDATE)

## Key pitfall: lowercase `op` values
`op_log` has `CHECK (op IN ('insert', 'update', 'delete'))`. The trigger SQL MUST emit lowercase:
```sql
-- WRONG (causes IntegrityError)
VALUES ('INSERT', ...)

-- RIGHT
VALUES ('insert', ...)
```

## SQLite version requirement
`json_object()` requires SQLite 3.38.0+. Check:
```python
import sqlite3
print(sqlite3.sqlite_version)  # Must be >= 3.38.0
```

## Usage
```bash
python3 /root/.hermes/scripts/apply_triggers.py
```

## Testing
After running, verify triggers exist:
```sql
SELECT name FROM sqlite_master WHERE type='trigger';
```

Then insert a row into `messages` and check `op_log`:
```sql
SELECT op, table_name, row_id, new_value FROM op_log WHERE table_name = 'messages' ORDER BY id DESC LIMIT 1;
```

## Victor endpoint provenance
- Direct endpoint: `http://127.0.0.1:8799/v1/chat/completions`
- Model: `viktor` (claude4_7_opus)
- Auth: `Bearer viktor` (static)
- Response format: OpenAI-compatible (`choices[0].message.content`)
- No session persistence, no context between calls
- Suitable for single atomic questions (200-300s latency)
