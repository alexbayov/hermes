# P1 Implementation Plan — Agent Memory System

Based on Victor's atomic responses (01-sqlite-production, 03-log-compaction, 04-undo-operations, 05-backup-strategies).

## Phase 1: SQLite Production Foundation
**Files:** `scripts/init_db.py`, `scripts/db_utils.py` (new)
**Changes:**
- Add WAL mode, FK, busy_timeout, cache_size pragmas (per Victor's 01)
- Add `schema_version` table with singleton row
- Create connection helper with thread-local + contextmanager tx()
- Use `BEGIN IMMEDIATE` for writes, `BEGIN` for reads
- Add `PRAGMA integrity_check` on startup

## Phase 2: Schema Migrations
**Files:** `scripts/migrate_schema.py` (new)
**Changes:**
- Read current schema_version, apply sequential migrations
- Migration v1→v2: add `status` to sessions, `token_count` to messages, `entry_count` to sessions, `context_summary` to sessions
- Migration v2→v3: add FK constraints (ON DELETE CASCADE)
- All migrations as idempotent SQL scripts

## Phase 3: Compaction & Lifecycle
**Files:** `scripts/compact_parents.py` (new), `scripts/session_end_start.py` (update)
**Changes:**
- Add `status` enum: active, closed, compacted, archived
- Tier-1: every 10 sessions, summarize oldest into compacted session
- Tier-2: if total messages > 2000, keep only recent 3-5 sessions with full messages, summarize rest into `context_summary`
- Use `VACUUM INTO` for compacted archive (per Victor's 03)

## Phase 4: Undo / Rollback
**Files:** `scripts/rollback_turn.py` (new)
**Changes:**
- Use SAVEPOINT for within-session undo (per Victor's 04)
- For persistent undo: trigger-based `undolog` table or event sourcing `op_log` table
- Rollback last message + associated decisions/artifacts/issues

## Phase 5: Backup
**Files:** `scripts/backup_db.py` (new)
**Changes:**
- `VACUUM INTO` for atomic DB backup (per Victor's 05)
- JSONL rotation inside `BEGIN IMMEDIATE` transaction
- Timestamped archives: `backup/YYYY-MM-DD_HH-MM-SS/`
- Integrity check after backup
- Optional: filesystem snapshot (ZFS/btrfs) if available

## Phase 6: Auto-commit Pipeline
**Files:** `scripts/auto_commit.py` (new), cron job or watcher
**Changes:**
- Watch skills/ directory for changes (inotify or git diff)
- Auto-commit with message: `auto: skill <name> updated`
- Push to origin/main via credential store
- Exclude runtime noise (logs, locks, state.db)

## Phase 7: Token Counting & Memory.md Optimization
**Files:** `scripts/persist.py` (update), `scripts/session_end_start.py` (update)
**Changes:**
- Add `token_count` to messages, `entry_count` to sessions
- Persist.py increments entry_count per insert
- Resume_context.py stops traversal if cumulative tokens > threshold
- Memory.md stores only: session IDs, last turn, active decision/issue IDs (comma-sep), 1-line summary, file paths
- Max 2200 chars, ID-based references instead of full text

## PR Strategy
- Branch: `feat/p1-<phase-name>` for each phase
- Commit: `feat(p1): <description>`
- Merge to main after each phase passes health_check.py
- Order: 1 → 2 → 3 → 4 → 5 → 6 → 7

## Risk Mitigation
- Each phase: run `memory_health.py` before and after
- Phase 2: backup DB before migration (migrate_schema.py --backup-first)
- Phase 3: test compaction on copy, not live DB
- Phase 4: test rollback on test session
- Phase 5: verify backup integrity before deleting old files
- Phase 6: dry-run mode first (git commit without push)

---

## Victor's Key Patterns (from atomic responses)

### SQLite Production (01)
```python
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;  # NOT persistent, set on every connect
PRAGMA busy_timeout = 5000;
PRAGMA cache_size = -65536;  # 64 MiB
PRAGMA mmap_size = 268435456;  # 256 MiB
PRAGMA wal_autocheckpoint = 1000;
```
- `BEGIN IMMEDIATE` for writers (avoids SQLITE_BUS mid-tx)
- Thread-local connection per thread
- `executemany` for bulk inserts inside transaction
- `integrity_check` on startup
- `backup()` API or `VACUUM INTO` for hot backups

### Compaction (03)
- Hot/warm/cold via ATTACH DATABASE
- Rolling window + batch move (10-50k rows per batch)
- Partial index `WHERE archived_at IS NULL`
- `VACUUM INTO 'main_compact.db'` for defragmentation
- `auto_vacuum=INCREMENTAL` must be set at DB creation
- Rollup tables for aggregates (hourly, daily)

### Undo (04)
- SAVEPOINT for within-session undo
- Trigger-based `undolog` table for persistent undo
- SQLite session extension / changesets (`apsw` library)
- Application-level `op_log` with inverse operations

### Backup (05)
- Filesystem snapshot (ZFS/btrfs) = atomic DB+JSONL
- `BEGIN IMMEDIATE` + JSONL rotation + `.backup` or `VACUUM INTO`
- `litestream` for continuous WAL replication
- Never `cp` live DB without checkpoint
- Always include `.db-wal` and `.db-shm` in file-level backups
