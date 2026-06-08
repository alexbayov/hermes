# Viktor Architecture Review — SQLite Persistence Toolkit

*Date:* 2026-06-08  
*Model:* claude-sonnet-4-20250514 via direct endpoint  
*Context:* generic SQLite persistence toolkit for conversational AI (no ENI/Hermes mentions)

---

## TL;DR
Strong design. Biggest remaining work: **retention.py** (fixes 3 unbounded growth vectors + backup bug), then **FTS5/sqlite-vec** for relevance-based recall instead of recency-only.

## Critical Fixes (do now)

### 1. Backup bug — VACUUM INTO + WAL/SHM copy = corruption risk
`VACUUM INTO` produces a fully checkpointed, standalone DB with NO WAL/SHM. Copying live WAL/SHM on top creates stale frames / orphan sidecars. **Fix:** use VACUUM INTO alone, OR `wal_checkpoint(TRUNCATE)` + cold file copy — never mix. Verify every backup by opening read-only + `PRAGMA quick_check`.

### 2. Durability pragmas unstated
Set explicitly per-connection:
```sql
PRAGMA journal_mode=WAL;         -- persistent (db-level)
PRAGMA synchronous=NORMAL;      -- WAL-safe; use FULL if last txn cannot be lost
PRAGMA busy_timeout=5000;         -- better than manual retry loop
PRAGMA foreign_keys=ON;           -- per-connection! not inherited
PRAGMA wal_autocheckpoint=1000;  -- bound WAL growth
```
Keep `retry_on_lock` only for `SQLITE_BUSY_SNAPSHOT` after timeout.

### 3. Write-ahead ordering of journal.log
Crash recovery holds only if journal is durably flushed **before** DB commit:
```python
append → flush() + os.fsync(fd) → then DB write
```
DB = source of truth on mismatch; journal = WAL for replay.

### 4. Unbounded growth in 3 places
- backups (keep all forever)
- op_log (trigger-driven, ~3-4× write amplification)
- journal.log (append-only)
All need retention/rotation.

### 5. Recall is recency-only
`resume_context` + parent_chain + token budget = recency bias. **Missing:** relevance-based recall.
**Solution:** `FTS5` (keyword) and/or `sqlite-vec` (semantic embeddings) over messages/decisions/artifacts. This is the single biggest capability gap.

### 6. Compaction vs referential integrity
Tier-2 archiving oldest messages: do `decisions`/`artifacts`/`parent_chain` still reference archived rows? Dangling parent_chain breaks `resume_context`. Fix: keep summary rows as FK targets, denormalize, or relax FKs on archive.

### 7. Ordering by wall-clock
Clock skew/NTP can reorder turns. Use monotonic `rowid`/autoincrement as ordering key; timestamps as metadata only.

### 8. sync_journal.py bidirectional = anti-pattern
Bidirectional log↔DB sync needs conflict resolution and invites split-brain. Keep one-way: journal = append-only WAL, DB = materialized state, validate_and_repair = replay. **Drop bidirectional sync entirely.**

### 9. Crash recovery untested
Add fault-injection test: `kill -9` mid-persist → run recovery → assert DB == expected.

---

## Recommended Roadmap

1. **`retention.py`** — unified GC (low risk, kills 3 growth bombs, fixes backup bug)
2. **Indexing pass** — before 10k rows bite (cheap, big read win)
3. **Retrieval: FTS5 then sqlite-vec** — the real product unlock; replaces tiered storage value
4. **Monitoring/health** — fold into retention's run
5. **Defer tiered storage** — highest complexity, lowest current ROI

## retention.py Design Sketch (Viktor)

Config-driven (`retention.yaml`):
```yaml
backups:   keep_daily=7, keep_weekly=4, keep_monthly=6  # GFS rotation
op_log:    keep_days=30 OR keep_rows=200_000
journal:   rotate_at_mb=50, keep_rotations=10, gzip old
archived_sessions: purge_after_days=180 (status=archived/compacted only)
```

Run order (idempotent, guarded, `--dry-run` default):
1. `PRAGMA quick_check` — abort if not 'ok'
2. `prune_backups()` — GFS bucket, verify survivors open + quick_check
3. `rotate_journal()` — fsync, rename, gzip; only rotate confirmed materialized entries
4. `prune_op_log()` — batched DELETE (5k), `PRAGMA wal_checkpoint` after
5. `purge_archived_sessions()` — respect FK, refuse if live references exist
6. `PRAGMA incremental_vacuum` (if auto_vacuum=INCREMENTAL)
7. Write metrics row (db_size, wal_size, op_log_rows, journal_bytes, deleted_counts)

Safety: `--dry-run` default; `--apply` required; hard floor on keep-counts; `RETENTION-{run_id}` issue record.

## Indexing Shortlist (Viktor)
```sql
CREATE INDEX ix_messages_session_turn ON messages(session_id, turn_id);
CREATE INDEX ix_messages_parent       ON messages(parent_id);
CREATE INDEX ix_decisions_session_status ON decisions(session_id, status);
CREATE INDEX ix_artifacts_session_status ON artifacts(session_id, status);
CREATE INDEX ix_oplog_created       ON op_log(created_at);
-- consider WITHOUT ROWID for narrow lookup tables; run ANALYZE after load
```

---

*Next ask to Viktor:* retention.py implementation against actual schema, or FTS5+sqlite-vec retrieval layer.
