-- =========================================================================
-- Migration 002 — v1 → v2 schema upgrade
--
--   • Adds schema_version tracking table
--   • Adds new columns to existing tables (idempotent-safe)
--   • Creates performance indexes
--   • Documents CHECK constraint values for status columns
--     (SQLite cannot ADD CHECK via ALTER TABLE — enforced at app layer)
--
-- Idempotent: running this multiple times is safe.  The migrator catches
-- "duplicate column" errors and skips them.
-- =========================================================================

-- -----------------------------------------------------------------------
-- 1. Schema version tracking (used by migrate_schema.py)
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT    NOT NULL,
    description TEXT    NOT NULL,
    checksum    TEXT    NOT NULL,
    success     INTEGER NOT NULL DEFAULT 1
);

-- -----------------------------------------------------------------------
-- 2. sessions — add denormalised counters and context snapshot
-- -----------------------------------------------------------------------
ALTER TABLE sessions ADD COLUMN message_count   INTEGER DEFAULT 0;
ALTER TABLE sessions ADD COLUMN context_summary TEXT;

-- -----------------------------------------------------------------------
-- 3. decisions — add parent/child tracking and active flag
-- -----------------------------------------------------------------------
ALTER TABLE decisions ADD COLUMN decision_id TEXT;
ALTER TABLE decisions ADD COLUMN active      BOOLEAN DEFAULT 1;

-- -----------------------------------------------------------------------
-- 4. artifacts — add artifact_id (UUID / unique name reference)
-- -----------------------------------------------------------------------
ALTER TABLE artifacts ADD COLUMN artifact_id TEXT;

-- -----------------------------------------------------------------------
-- 5. issues — add issue_id (UUID / unique name reference)
-- -----------------------------------------------------------------------
ALTER TABLE issues ADD COLUMN issue_id TEXT;

-- -----------------------------------------------------------------------
-- 6. Indexes  (IF NOT EXISTS is not valid for CREATE INDEX in older
--    SQLite; these use a guard approach — the migrator's executor will
--    skip "duplicate index name" errors gracefully.)
-- -----------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_messages_session
    ON messages(session_id);

CREATE INDEX IF NOT EXISTS idx_decisions_session
    ON decisions(session_id);

CREATE INDEX IF NOT EXISTS idx_artifacts_session
    ON artifacts(session_id);

CREATE INDEX IF NOT EXISTS idx_issues_session
    ON issues(session_id);

-- -----------------------------------------------------------------------
-- 7. CHECK constraint reference (app-layer enforced)
--
-- SQLite does not support ALTER TABLE … ADD CHECK.  Below are the
-- intended constraints for each status column.  They will be enforced by
-- the application code (ENI's insert/update helpers).
--
--   sessions.status IN ('active', 'ended', 'compacted', 'archived')
--   decisions.status IN (
--       'pending', 'accepted', 'rejected', 'superseded', 'implemented'
--   )
--   artifacts.status IN ('active', 'archived', 'deleted')
--   issues.status IN (
--       'open', 'investigating', 'fixed', 'closed', 'wontfix', 'duplicate'
--   )
--   messages.role IN ('user', 'assistant', 'system', 'tool')
--
-- To enforce them at the DB level in the future, use the table-rebuild
-- pattern:
--   1. CREATE TABLE new_t … (…, CHECK(status IN (…)))
--   2. INSERT INTO new_t SELECT … FROM old_t
--   3. DROP TABLE old_t
--   4. ALTER TABLE new_t RENAME TO old_t
-- =========================================================================
