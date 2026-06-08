# Victor P1 Atomic Responses

Collected via atomic questioning technique (see `../atomic-questioning-technique.md` in consult-victor skill).

## 01-sqlite-production.txt
SQLite production configuration: WAL pragmas, thread-safe connection helper, transaction discipline (`BEGIN IMMEDIATE` vs `BEGIN`), crash recovery, `VACUUM INTO` / `backup()` API, integrity checks.

## 03-log-compaction.txt
Time-series compaction in SQLite: hot/warm/cold via ATTACH DATABASE, rolling window + batch DELETE, partial index `WHERE archived_at IS NULL`, VACUUM INTO, auto_vacuum=INCREMENTAL, rollup tables.

## 04-undo-operations.txt
Undo patterns in SQLite: SAVEPOINT (session-level), trigger-based `undolog` table (persistent), SQLite session extension / changesets via `apsw`, application-level event sourcing `op_log` with inverse operations.

## 05-backup-strategies.txt
Backup strategies: filesystem snapshots (ZFS/btrfs), `BEGIN IMMEDIATE` + JSONL rotation + `VACUUM INTO`, Litestream continuous WAL replication, `restic`/`borg` for offsite, integrity verification post-backup.

## 02-schema-migrations-REFUSED.txt
Victor refused schema migrations question — detected as 5th parallel thread in 13 minutes. Need to implement schema versioning autonomously or ask after cooldown.
