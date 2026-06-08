# retention.py Roadmap and Design Sketch

*Source:* Viktor (claude-sonnet-4-20250514) architecture review, 2026-06-08
*Status:* design complete, implementation pending

## Why retention.py is the next priority

Viktor ranked this as **#1** because it simultaneously:
- Fixes the `VACUUM INTO` + WAL/SHM backup bug (silent data corruption risk)
- Kills 3 unbounded growth vectors: backups, op_log, journal.log
- Low risk, high value, no external dependencies

## Design Sketch (Viktor)

### Config (YAML or JSON)
```yaml
backups:   keep_daily=7, keep_weekly=4, keep_monthly=6  # GFS rotation
op_log:    keep_days=30 OR keep_rows=200_000
journal:   rotate_at_mb=50, keep_rotations=10, gzip old
archived_sessions: purge_after_days=180 (status=archived/compacted only)
```

### Run order (each idempotent, guarded, --dry-run default)
1. `PRAGMA quick_check` — abort if not 'ok'
2. `prune_backups()` — GFS bucket, verify survivors open + quick_check
3. `rotate_journal()` — fsync, rename, gzip; only rotate confirmed materialized entries
4. `prune_op_log()` — batched DELETE (5k), PRAGMA wal_checkpoint after
5. `purge_archived_sessions()` — respect FK, refuse if live references exist
6. `PRAGMA incremental_vacuum` (if auto_vacuum=INCREMENTAL)
7. Write metrics row (db_size, wal_size, op_log_rows, journal_bytes, deleted_counts)

### Safety rails
- `--dry-run` default: print plan + counts, change nothing
- `--apply` required to mutate; refuse if quick_check != ok
- Hard floor: never let any keep-count go below documented minimum
- Emit `RETENTION-{run_id}` issue record with action summary

## Backup Bug Fix

`VACUUM INTO` produces a standalone DB with no WAL/SHM. Do NOT copy live WAL/SHM on top — creates stale frames / orphan sidecars.
**Fix:** VACUUM INTO alone, OR `wal_checkpoint(TRUNCATE)` + cold copy. Never mix.
Verify: open backup read-only + `PRAGMA quick_check`.

## Key Decisions (to log when implementing)

1. **GFS vs simple rotation:** GFS is simple enough for one-machine backups; no need for complex tiering.
2. **Journal rotation gate:** Only rotate entries already confirmed materialized in DB (e.g., all entries with turn_id <= DB MAX). This prevents data loss if crash happens between journal write and DB commit.
3. **op_log as audit trail, not recovery source:** Pruning op_log by age is fine because validate_and_repair replays from journal.log, not op_log. If op_log needs to be source-of-truth, prune more conservatively.
4. **One-way sync only:** Bidirectional log↔DB sync is anti-pattern. Keep journal = append-only WAL, DB = materialized state.

## Implementation Checklist

- [ ] Create `retention.py` with argparse (`--dry-run`, `--apply`, `--config`)
- [ ] Add `retention_runs` table to schema (v5 migration)
- [ ] Fix `backup_db.py` to use VACUUM INTO alone (no WAL/SHM copy)
- [ ] Add `PRAGMA busy_timeout=5000` and `wal_autocheckpoint=1000` to `db_utils.py`
- [ ] Add `os.fsync()` after journal.log append in `persist.py` (write-ahead ordering)
- [ ] Create indexes: `ix_messages_session_turn`, `ix_messages_parent`, `ix_decisions_session_status`, `ix_artifacts_session_status`, `ix_oplog_created`
- [ ] Run `ANALYZE` after index creation
- [ ] Smoke test: `kill -9` mid-persist → validate_and_repair → assert DB == expected
