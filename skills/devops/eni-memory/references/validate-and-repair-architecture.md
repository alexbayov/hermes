# Validate & Repair Architecture (Viktor direct endpoint, 2025-06-08)

## Source
Design answers from Viktor (claude4_7_opus) via direct endpoint `127.0.0.1:8799/v1`,
compressed into atomic questions with "no prose, code only" constraint.

## Core algorithm (reverse JSONL replay)
1. **Open file seek(0, 2)**, then read backward chunk-by-chunk (8KB) to handle unbounded files.
2. **Parse lines newest-first** (reverse chronological order).
3. **Deduplicate by identity key** (composite key per entity type):
   - `messages`: `session_id + turn_id + role`
   - `decisions`: `session_id + turn_id + title`
   - `artifacts`: `session_id + turn_id + name`
   - `issues`: `session_id + turn_id + title`
   - Newest wins (last-seen in reverse read = newest in actual order)
4. **Build in-memory maps** (`missing_msgs`, `missing_decisions`, etc.) for rows not present in SQLite.
5. **Backfill idempotently** using `INSERT OR IGNORE` (messages) or `INSERT ... ON CONFLICT DO NOTHING` (decisions/artifacts/issues with UNIQUE indexes).
6. **Log a `REPAIR-{turn_id}` issue** per session with counts of backfilled entities.

## Why reverse read matters
- Forward read of a 100MB+ journal.log is O(n) with high memory if you want newest-wins dedup.
- Reverse read lets you stop early if you only need the last N sessions (or if a `--since` flag is added later).
- Natural fit for "repair most recent missing data first" use case.

## Identity keys (dict-format journal.log)
```json
{"type": "decision", "session_id": "...", "turn_id": 5, "payload": {"title": "DB choice", "choice": "SQLite", "rationale": "..."}}
```
The identity key is `(session_id, turn_id, payload['title'])`. This requires the
journal.log to store **full dict payloads**, not just string titles.

## Backward compatibility
Old journal.log entries with string payloads (e.g., `"DB choice"` instead of `{"title":"DB choice",...}`)
are parsed by type coercion:
- If `payload` is a string, use it as both `title` and `choice` (fallback).
- If `payload` is a dict, extract identity fields normally.

## SQLite idempotency requirements
- `messages`: no UNIQUE constraint on (session_id, turn_id, role), so use `INSERT OR IGNORE`.
- `decisions`/`artifacts`/`issues`: migration v4 adds `CREATE UNIQUE INDEX` on `(session_id, turn_id, title)` etc.
  This enables `ON CONFLICT DO NOTHING` / `ON CONFLICT DO UPDATE`.

## Session scoping
Always scope the "find missing" query to the target session:
```sql
SELECT turn_id FROM messages WHERE session_id = ? AND role = ?
```
Do NOT use global `MAX(turn_id)` — it will return the parent session's last turn.
