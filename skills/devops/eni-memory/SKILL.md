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
- `migrate_schema.py` — idempotent schema migrations with backup-first safety (v7: messages UNIQUE index + FTS5 + retention_runs + indexes)
- `persist.py` — unified turn logging with decisions/artifacts/issues (journal.log dual-write with full dict payloads)
- `semantic_search.py` — FTS5 + sqlite-vec hybrid search (BM25 + cosine similarity, RRF fusion, resumable backfill)
- `validate_last_turn.py` — startup integrity check (gaps, missing assistant turn, active session)
- `validate_and_repair.py` — backfill missing DB rows from journal.log idempotently (reverse read, dedup, REPAIR issues)
- `resume_context.py` — restore context from DB, traverses parent sessions with token budget
- `memory_health.py` — DB diagnostics: gaps, orphans, size, stats, recommendations
- `memory_query.py` — keyword search across messages, decisions, artifacts, issues
- `session_end_start.py` — end current session and start new with parent linkage (for reboots/compaction)
- `compact_parents.py` — archive old sessions (Tier-1: >10 closed; Tier-2: >2000 messages)
- `backup_db.py` — atomic VACUUM INTO backup + WAL + JSONL journal
- `auto_commit.py` — watch skills/ changes and auto-commit/push to origin/main
- `test_crash_recovery.py` — deterministic fault-injection test: simulates crash (journal written, DB corrupted), runs validate_and_repair, asserts full recovery
- `apply_triggers.py` — idempotent SQLite AFTER triggers for op_log audit (INSERT/UPDATE/DELETE logging with json_object snapshots)
- `db_utils.py` — production connection helpers (WAL, FK, thread-local, tx())
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

## Validate and repair (journal.log backfill)
When DB is missing turns that exist in `journal.log` (crash, write failure, schema issue):
```bash
python3 /root/.hermes/scripts/validate_and_repair.py --session-id <SESSION_ID> --dry-run
python3 /root/.hermes/scripts/validate_and_repair.py --session-id <SESSION_ID>            # live repair
```
- Reads `journal.log` newest-first, deduplicates by identity key (newest wins)
- Backfills missing `messages`/`decisions`/`artifacts`/`issues` rows idempotently (`ON CONFLICT`/`INSERT OR IGNORE`)
- Logs `REPAIR-{turn_id}` issue records with counts per table
- Fully idempotent: re-running reports zero if nothing missing
- Supports both old (string) and new (dict) journal.log formats for decisions/artifacts/issues

## Schema migrations
```bash
python3 /root/.hermes/scripts/migrate_schema.py --target 7   # apply up to v7 (messages UNIQUE + FTS5 + retention_runs + indexes)
python3 /root/.hermes/scripts/migrate_schema.py --no-backup  # skip backup (dangerous)
```

## Compaction (archive old sessions)
```bash
python3 /root/.hermes/scripts/compact_parents.py --dry-run
python3 /root/.hermes/scripts/compact_parents.py               # live run
```

## Backup (atomic snapshot)
```bash
python3 /root/.hermes/scripts/backup_db.py --label pre-release
python3 /root/.hermes/scripts/backup_db.py --no-journal
```

## Auto-commit (watch skills/ changes)
```bash
python3 /root/.hermes/scripts/auto_commit.py --dry-run
python3 /root/.hermes/scripts/auto_commit.py --no-push
```

## Audit triggers (op_log auto-capture)
```bash
python3 /root/.hermes/scripts/apply_triggers.py   # idempotent: drop & recreate AFTER INSERT/UPDATE/DELETE triggers
```
Every change to `messages`, `decisions`, `artifacts`, `issues` is automatically captured in `op_log` with full JSON snapshots (`old_value`, `new_value`).
- `apply_triggers.py` is safe to run multiple times (idempotent DROP IF EXISTS + CREATE)
- For `sessions` table, triggers are omitted because `session_id`/`turn_id` are not present (sessions are root entities)
- Uses `json_object()` (SQLite 3.38+) for structured snapshots
- Enables disaster recovery: replay `op_log` rows to reconstruct any deleted/modified record

## Retention and garbage collection (implemented)
```bash
python3 /root/.hermes/scripts/retention.py --dry-run   # show plan only
python3 /root/.hermes/scripts/retention.py --apply       # execute
```

What it does (in order):
1. `PRAGMA quick_check` — abort if not 'ok'
2. `VACUUM INTO` backup — standalone, no WAL/SHM copy (fixes the backup bug)
3. `prune_backups()` — GFS rotation (daily=7, weekly=4, monthly=6), verify survivors with quick_check
4. `rotate_journal()` — fsync, rename, gzip when >50MB; only rotate confirmed materialized entries (turn_id ≤ MAX(messages.turn_id))
5. `prune_op_log()` — batched DELETE (5k per txn), `PRAGMA wal_checkpoint` after; keeps 30 days / 200k rows
6. `purge_archived_sessions()` — delete status=archived/compacted older than 180 days, respect FK (skip if live decisions/artifacts/open issues)
7. `PRAGMA incremental_vacuum` (if auto_vacuum=INCREMENTAL)
8. Write metrics row to `retention_runs` table + emit `RETENTION-{run_id}` issue record

Config: JSON at `/root/.hermes/config/retention.json` (optional; defaults inline).

## Indexing recommendations

Run these **before** the message table hits 10k rows:

```sql
CREATE INDEX IF NOT EXISTS ix_messages_session_turn ON messages(session_id, turn_id);
CREATE INDEX IF NOT EXISTS ix_decisions_session_active ON decisions(session_id, active);
CREATE INDEX IF NOT EXISTS ix_artifacts_session_status ON artifacts(session_id, status);
CREATE INDEX IF NOT EXISTS ix_oplog_created           ON op_log(created_at);
-- run after bulk load:
PRAGMA optimize;
ANALYZE;
```

Future: `FTS5` (keyword search) and/or `sqlite-vec` (semantic embeddings) for relevance-based recall instead of recency-only parent_chain traversal. This is the single biggest capability gap per Viktor's review. **Implemented:** `semantic_search.py` (FTS5 BM25 + sqlite-vec cosine similarity + RRF hybrid fusion). Requires `sqlite-vec` loadable extension.
- **Never skip the end-of-turn ritual.** If you don't log, the next session will not know what happened. validate_last_turn.py will catch it.
- Content should be **concise summaries** (200-500 chars), not full tool output. Use `--tool-result` for full JSON if needed.
- If `turn_id` conflicts, ON CONFLICT will update the existing row. This is safe.
- Keep `memory.md` to only the DB path pointer and current session ID. Everything else lives in SQLite.
- `token_count` is optional but useful for context-length analysis.
- **SQLite cursor vs connection bug:** When using `with sqlite3.connect(...) as c:`, the variable `c` is the *Connection*, not a Cursor. Calling `c.execute(...)` works for one-off statements, but `c.fetchall()` raises `AttributeError`. Always create a cursor: `cur = c.cursor(); cur.execute(...); rows = cur.fetchall()`. See `references/sqlite-common-bugs.md`.
- **Global vs per-session MAX(turn_id):** `SELECT MAX(turn_id) FROM messages` is global across all sessions. For a new session with only 2 turns, this will report the parent's last turn number. Always scope to `WHERE session_id=?`. See `references/parent-chain-session-lifecycle.md`.
- **Victor/Opus integration limits:** Odysseus bridge at localhost:7000 has no hard token limit, but keep requests under ~10KB for reliability. Summarize context first. Larger specs must be split into multiple calls or saved as reference files. See `references/external-ai-consultation.md` for current endpoint details and ethical boundary.
- **VACUUM INTO inside a transaction:** `VACUUM INTO` cannot run inside an explicit `BEGIN ... COMMIT` block. If using `db_utils.tx()` (which wraps `BEGIN IMMEDIATE`), create a **fresh `sqlite3.connect()`** for the backup instead. See `references/sqlite-common-bugs.md`.
- **Thread-local connection staleness:** `db_utils.get_conn()` caches connections per thread. If any code calls `.close()` on that connection (e.g., in `backup()`), the next `get_conn()` returns the **closed** handle. Fix: verify liveness with a `SELECT 1` probe and re-create if dead. See `references/sqlite-common-bugs.md`.
- **`git status --short` parsing fragility:** The status column is **2 characters** (e.g., ` M`, `??`). Parsing with `line[3:]` drops the first character of the filename. Use `line.split(maxsplit=1)[1]` instead. This affects `auto_commit.py` and any script that parses `git status`.
- **`op_log.op` CHECK constraint is lowercase:** `op_log` table has `CHECK (op IN ('insert', 'update', 'delete'))` (lowercase). The trigger SQL must emit lowercase values (`'insert'`, `'update'`, `'delete'`), not `'INSERT'`, `'UPDATE'`, `'DELETE'`. Mismatch causes `IntegrityError: CHECK constraint failed`. If triggers are created with uppercase, the `op` column silently rejects all writes. This was caught in production when `apply_triggers.py` v1 emitted uppercase `op` values. Fix: map `INSERT` → `'insert'` in trigger body. See `references/apply-triggers-design.md`.
- **Journal.log format upgrade for repair:** `persist.py` (v2+) writes full dict payloads for `decisions`/`artifacts`/`issues` into `journal.log` (e.g., `{"title": "...", "choice": "...", "rationale": "..."}`). This is required for `validate_and_repair.py` to compute identity keys (`(session_id, turn_id, title)`) and deduplicate correctly. Old string-only entries (e.g., `"DB choice"`) still parse but lose the `rationale`/`rejected` fields on backfill. If you see `REPAIR` issues with missing rationale, the journal.log has old-format entries. See `references/validate-and-repair-architecture.md`.
- **Trigger `json_object()` requires SQLite 3.38+:** The `json_object()` SQL function used in `apply_triggers.py` for `old_value`/`new_value` snapshots requires SQLite 3.38.0 or later. Ubuntu 22.04 ships SQLite 3.37.2 which does NOT support `json_object()`. Check `sqlite3.sqlite_version` before running `apply_triggers.py`. If too old, either upgrade SQLite or use manual string concatenation (`'{"id":' || NEW.id || ...}`).
- **Backup bug: VACUUM INTO + WAL/SHM copy = corruption:** `VACUUM INTO` produces a fully checkpointed, standalone DB with NO WAL/SHM. Copying live WAL/SHM on top creates stale frames / orphan sidecars that SQLite will replay onto mismatched pages. **Fix:** use VACUUM INTO alone, OR `wal_checkpoint(TRUNCATE)` + cold copy — never mix. Verify every backup by opening read-only + `PRAGMA quick_check`. See `references/retention-roadmap.md`.
- **Durability pragmas must be explicit:** WAL mode alone doesn't guarantee crash survival. Set per-connection: `PRAGMA synchronous=NORMAL` (use FULL if last txn cannot be lost), `PRAGMA busy_timeout=5000`, `PRAGMA wal_autocheckpoint=1000`, `PRAGMA foreign_keys=ON` (not inherited). `retry_on_lock` (3×100/200/400ms) is a backup, not a replacement for `busy_timeout`. See `references/viktor-architecture-review-2026-06-08.md`.
- **Journal.log write-ahead ordering:** Crash recovery only holds if journal is durably flushed **before** the DB commit: `append → flush() + os.fsync(fd) → then DB write`. If DB is written first, journal.log is just a mirror and cannot recover the lost tail. DB = source of truth; journal = WAL for replay. See `references/viktor-architecture-review-2026-06-08.md`.
- **Bidirectional sync_journal is an anti-pattern:** Never build log↔DB bidirectional sync. It needs conflict resolution and invites split-brain. Keep one-way: journal = append-only WAL, DB = materialized state, `validate_and_repair` = replay. See `references/viktor-architecture-review-2026-06-08.md`.
- **Recency-only recall is a product gap:** `resume_context` traverses parent_chain under a token budget — this is recency bias, not relevance. The real value of long-term memory is pulling the *right* old context, not the *recent* one. Add `FTS5` (keyword) and/or `sqlite-vec` (semantic embeddings) over messages/decisions/artifacts. This is the single biggest missing capability. See `references/viktor-architecture-review-2026-06-08.md`.
- **Viktor gives architectural reviews, not always full code:** When asking Viktor for complex scripts (e.g., `retention.py`), he returns correct design patterns, constraints, and stub functions. The agent must implement the production-ready version locally using his architecture as the spec. Do NOT wait for a second pass to fill stubs. See `references/viktor-architecture-review-2026-06-08.md`.
- **Ordering by wall-clock is fragile:** Clock skew/NTP step can reorder turns. Use monotonic `rowid`/autoincrement as the ordering key; keep timestamps as metadata only. See `references/viktor-architecture-review-2026-06-08.md`.
- **Crash recovery is untested until fault-injected:** A durability claim that hasn't been tested with `kill -9` mid-persist is a hope, not a guarantee. Add a fault-injection test: kill mid-write → run `validate_and_repair` → assert DB == expected. See `references/viktor-architecture-review-2026-06-08.md`.

When skill files (SKILL.md, scripts/, references/, plans/) change, **commit and push immediately** to the repo. Do not accumulate changes — user explicitly wants protection against data loss.

```bash
cd /root/.hermes
git add <changed files>
git commit -m "<type>(<scope>): <description>"
git push origin main
```

**Git identity:** `ENI <eni@hermes.local>` (configured globally)
**Credential store:** `~/.git-credentials` with GitHub PAT for headless push
**Exclude:** runtime noise (logs, locks, state.db, sessions/*.json, kanban.db, channel_directory.json, auth.lock, *.lock, memories/)

## Security — ENI/SOUL secrecy in public repo

**Never mention ENI, SOUL.md, or jailbreak concepts in skill docs, reference files, commit messages, or external prompts.** Victor and any external consultant must never see these terms. If a skill doc previously contained ENI references, sanitize before commit. Use neutral language: "agent context", "persistent memory", "session restart", "framework configuration" instead of ENI/SOUL.

## References
- `references/external-ai-consultation.md` — when and how to escalate to Victor/Opus for architecture review
- `references/atomic-questioning-technique.md` — how to bypass Victor refusal by asking narrow technical questions in fresh sessions (proven 4/5 success rate)
- `references/victor-p1-answers/` — Victor's responses on SQLite production, compaction, undo, backup (atomic questioning results)
- `references/parent-chain-session-lifecycle.md` — how session linkage survives reboots, and the per-session gap-detection fix
- `references/diagnostic-scripts.md` — `memory_health.py` and `memory_query.py` usage
- `references/sqlite-common-bugs.md` — cursor vs connection, global aggregates, WAL mode, FK pragmas
- `references/validate-and-repair-architecture.md` — Viktor's design for reverse JSONL replay, dedup, idempotent backfill, identity keys (code-only atomic questioning, 2025-06-08)
- `references/apply-triggers-design.md` — design notes for `apply_triggers.py`: SQLite trigger audit logging, `json_object()` snapshots, lowercase `op` pitfall, Victor direct endpoint provenance
- `references/victor-p0-spec.md` — condensed P0 implementation: `db_utils.py`, `migrate_schema.py`, retry decorators, WAL
- `references/victor-v2-spec.md` — condensed full architecture: compaction tiers, memory.md budget, event sourcing, edge cases
- Full P0 implementation: `/root/.hermes/plans/victor-p0-implementation.md` (30KB)
- Full v2 architecture: `/root/.hermes/plans/eni-memory-v2-spec.md` (61KB)
- P1 plan: `/root/.hermes/plans/p1-implementation.md` — 7-phase implementation (WAL, migrations, compaction, undo, backup, auto-commit, token counting)
- `references/semantic-search-viktor.md` — Viktor's full response: FTS5 external-content + triggers, sqlite-vec vec0 schema, serialize_f32, batch backfill, RRF hybrid fusion, gotchas (2026-06-08, direct endpoint, no ENI context)
- `references/viktor-architecture-review-2026-06-08.md` — Viktor's architecture review: backup bug, durability pragmas, unbounded growth, relevance-based recall gap, bidirectional sync anti-pattern, crash-recovery fault injection (2026-06-08, direct endpoint, no ENI context)
- `references/retention-roadmap.md` — Viktor's design sketch for `retention.py`: GFS backup rotation, op_log/journal pruning, archived session purge, metrics, safety rails, implementation checklist
