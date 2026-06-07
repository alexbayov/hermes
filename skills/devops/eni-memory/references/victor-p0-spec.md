# Victor P0 Implementation Spec — Condensed Reference

Full spec: `/root/.hermes/plans/victor-p0-implementation.md` (30KB)

P0 = highest priority block. Covers: retry decorator, WAL mode, schema migration, and db_utils refactor.

## Key Deliverables

| File | Purpose | Pattern |
|------|---------|---------|
| `db_utils.py` | Connection factory + decorators | `get_db_connection()`, `@retry_on_lock`, `@transaction` |
| `migrate_schema.py` | Versioned migrations | SHA256 checksums, `schema_version` table, dry-run, idempotent |
| `002_add_foreign_keys_and_wal.sql` | v1→v2 migration | `ALTER TABLE ADD COLUMN`, indexes, CHECK docs |
| `init_db.py` (updated) | Boot-time DB setup | Uses `db_utils.get_db_connection`, checks pending migrations |

## db_utils.py Patterns

```python
from db_utils import get_db_connection, retry_on_lock, transaction

# Connection with WAL, FK, busy_timeout
conn = get_db_connection('/root/.hermes/data/eni_memory.db')

# Retry on locked/busy (3 retries, 100ms/200ms/400ms backoff)
@retry_on_lock(max_retries=3, backoff_ms=100)
@transaction
def my_writer(conn, ...):
    conn.execute("INSERT INTO ...")
```

**Stacking order:** `@retry_on_lock` (outer) → `@transaction` (inner). This retries the entire transaction on lock contention.

## migrate_schema.py CLI

```bash
python3 migrate_schema.py --status          # list applied vs pending
python3 migrate_schema.py --dry-run         # print SQL without executing
python3 migrate_schema.py --target 002      # stop at version 002
python3 migrate_schema.py                   # apply all pending
```

Exit codes: 0=success, 1=apply failure, 2=checksum mismatch, 3=no pending migrations.

## Migration SQL Idempotency

Use `ALTER TABLE ... ADD COLUMN` (SQLite allows this, skips if exists). For `CREATE INDEX`, use `IF NOT EXISTS`. For `CREATE TABLE`, use `IF NOT EXISTS`. The migrator catches `OperationalError: duplicate column` and skips it.

## Checksum Mismatch Protection

Each migration file gets a SHA256 on first apply. If the file is modified later, `migrate_schema.py` refuses to re-apply (exit 2). This prevents silent schema drift.

## Pitfall: ALTER TABLE + CHECK Constraints

SQLite does **not** support `ALTER TABLE ... ADD CHECK`. CHECK constraints must be added via table rebuild (`CREATE new_t` → `INSERT` → `DROP` → `ALTER RENAME`). The P0 migration documents intended CHECK values as comments instead, enforcing at the app layer.
