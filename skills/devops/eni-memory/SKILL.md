---
name: eni-memory
description: SQLite-based persistent memory for agent context across Hermes session restarts. Logs context, decisions, artifacts, issues to disk.
version: 1.2
---

# eni-memory

**DB path:** `/root/.hermes/data/eni_memory.db`
**Scripts:** `/root/.hermes/scripts/`

## When to use
- **ON STARTUP (always first):** run `validate_last_turn.py`, then `resume_context.py`
- **AFTER EVERY RESPONSE:** run `persist.py` to log the turn
- **After key decisions / file creation / bugs:** run `persist.py` with --decision-title / --artifact-name / --issue-title
- **To check integrity:** `memory_health.py` (gaps, orphans, size)
- **To search memory:** `memory_query.py <keyword>` (messages, decisions, artifacts)
- **On session reboot / compaction:** `session_end_start.py --end --start` (links parent)

## Schema
- `sessions` — session metadata (uuid, started_at, ended_at, summary, status)
- `messages` — chat history (user/assistant/tool/system, token_count)
- `decisions` — architectural choices with rationale and rejected alternatives
- `artifacts` — created files, services, configs with status
- `issues` — bugs, symptoms, fixes, status

## Scripts
- `init_db.py` — initialize schema (run once)
- `persist.py` — unified turn logging with decisions/artifacts/issues
- `validate_last_turn.py` — startup integrity check (gaps, missing assistant turn, active session)
- `resume_context.py` — restore context from DB, traverses parent sessions
- `memory_health.py` — DB diagnostics: gaps, orphans, size, stats, recommendations
- `memory_query.py` — keyword search across messages, decisions, artifacts, issues
- `session_end_start.py` — end current session and start new with parent linkage (for reboots/compaction)

## Session start (REQUIRED, FIRST COMMAND)
```bash
python3 /root/.hermes/scripts/validate_last_turn.py
python3 /root/.hermes/scripts/resume_context.py
```
If `validate_last_turn.py` warns about missing log, **do not proceed** — log the previous turn first.

## After every turn (MANDATORY END-OF-TURN RITUAL)
After completing any assistant turn, log it with a **concise summary** (200-500 chars):
```bash
python3 /root/.hermes/scripts/persist.py \
  --session <SESSION_ID> \
  --turn <TURN_ID> \
  --role assistant \
  --content "<SUMMARY_OF_WHAT_I_DID>"
```

For tool results:
```bash
python3 /root/.hermes/scripts/persist.py \
  --session <SESSION_ID> \
  --turn <TURN_ID> \
  --role tool \
  --content "<RESULT_SUMMARY>" \
  --tool-name <TOOL_NAME> \
  --tool-result '<JSON_RESULT>'
```

## After key decisions
Log the decision so we never revisit rejected alternatives:
```bash
python3 /root/.hermes/scripts/persist.py \
  --session <SESSION_ID> \
  --turn <TURN_ID> \
  --role assistant \
  --content "Chose SQLite over Postgres for zero-dependency deploy" \
  --decision-title "DB engine choice" \
  --decision "SQLite" \
  --rationale "built-in, zero deps, file-based" \
  --rejected "Postgres, Redis"
```

## After creating artifacts
```bash
python3 /root/.hermes/scripts/persist.py \
  --session <SESSION_ID> \
  --turn <TURN_ID> \
  --role assistant \
  --content "Created systemd service for Qwen proxy" \
  --artifact-name "freeqwen-api.service" \
  --artifact-path "/etc/systemd/system/" \
  --artifact-type file \
  --artifact-status created \
  --artifact-desc "systemd service for Qwen proxy"
```

## After discovering issues
```bash
python3 /root/.hermes/scripts/persist.py \
  --session <SESSION_ID> \
  --turn <TURN_ID> \
  --role assistant \
  --content "Fixed uvicorn path in systemd service" \
  --issue-title "uvicorn not found in PATH" \
  --symptom "systemd service fails with 203/EXEC" \
  --root-cause "uvicorn installed in venv, not /usr/bin" \
  --fix "use /usr/bin/python3 -m uvicorn" \
  --issue-status fixed
```

## Session end / reboot (compaction)
When a session ends (reboot, compaction, long pause), close it and start a new one with parent linkage:
```bash
python3 /root/.hermes/scripts/session_end_start.py --end --summary "Phase X done" --start --new-summary "Phase Y"
```
`resume_context.py` will automatically pull last messages from the parent session if the new one is empty.

## Health checks (diagnostics)
```bash
python3 /root/.hermes/scripts/memory_health.py   # gaps, orphans, size, stats
python3 /root/.hermes/scripts/memory_query.py --stats
python3 /root/.hermes/scripts/memory_query.py SQLite   # search messages for 'SQLite'
python3 /root/.hermes/scripts/memory_query.py -t decisions memory   # search decisions
```

## Pitfalls
- **Never skip the end-of-turn ritual.** If you don't log, the next session will not know what happened. validate_last_turn.py will catch it.
- Content should be **concise summaries** (200-500 chars), not full tool output. Use `--tool-result` for full JSON if needed.
- If `turn_id` conflicts, ON CONFLICT will update the existing row. This is safe.
- Keep `memory.md` to only the DB path pointer and current session ID. Everything else lives in SQLite.
- `token_count` is optional but useful for context-length analysis.
- **SQLite cursor vs connection bug:** When using `with sqlite3.connect(...) as c:`, the variable `c` is the *Connection*, not a Cursor. Calling `c.execute(...)` works for one-off statements, but `c.fetchall()` raises `AttributeError`. Always create a cursor: `cur = c.cursor(); cur.execute(...); rows = cur.fetchall()`. See `references/sqlite-common-bugs.md`.
- **Global vs per-session MAX(turn_id):** `SELECT MAX(turn_id) FROM messages` is global across all sessions. For a new session with only 2 turns, this will report the parent's last turn number. Always scope to `WHERE session_id=?`. See `references/parent-chain-session-lifecycle.md`.
- **Victor/Opus integration limits:** Odysseus bridge at localhost:7000 has no hard token limit, but keep requests under ~10KB for reliability. Summarize context first. Larger specs must be split into multiple calls or saved as reference files. See `references/external-ai-consultation.md` for current endpoint details and ethical boundary.

## Rule
This is the single source of truth for process context. If it's not in the DB, it didn't happen.

## References
- `references/external-ai-consultation.md` — when and how to escalate to Victor/Opus for architecture review
- `references/parent-chain-session-lifecycle.md` — how session linkage survives reboots, and the per-session gap-detection fix
- `references/diagnostic-scripts.md` — `memory_health.py` and `memory_query.py` usage
- `references/sqlite-common-bugs.md` — cursor vs connection, global aggregates, WAL mode, FK pragmas
- `references/victor-p0-spec.md` — condensed P0 implementation: `db_utils.py`, `migrate_schema.py`, retry decorators, WAL
- `references/victor-v2-spec.md` — condensed full architecture: compaction tiers, memory.md budget, event sourcing, edge cases
- Full P0 implementation: `/root/.hermes/plans/victor-p0-implementation.md` (30KB)
- Full v2 architecture: `/root/.hermes/plans/eni-memory-v2-spec.md` (61KB)
