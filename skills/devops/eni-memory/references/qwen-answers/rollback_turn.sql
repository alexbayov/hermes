-- SQLite soft-delete / rollback pattern from Qwen (qwen-coder)
-- Mark rows status='reverted' instead of hard-deleting, while hard-deleting related content rows by turn_id

-- Example schema for demonstration
CREATE TABLE IF NOT EXISTS operations_log (
    id INTEGER PRIMARY KEY,
    operation_type TEXT NOT NULL, -- 'INSERT', 'UPDATE', 'DELETE'
    table_name TEXT NOT NULL,
    record_id INTEGER,
    turn_id INTEGER NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    data_snapshot TEXT, -- JSON snapshot of original data
    status TEXT DEFAULT 'active' -- 'active', 'reverted'
);

CREATE TABLE IF NOT EXISTS content_items (
    id INTEGER PRIMARY KEY,
    name TEXT,
    value TEXT,
    turn_id INTEGER NOT NULL,
    status TEXT DEFAULT 'active' -- 'active', 'deleted', 'reverted'
);

CREATE TABLE IF NOT EXISTS related_content (
    id INTEGER PRIMARY KEY,
    content_id INTEGER,
    data TEXT,
    turn_id INTEGER NOT NULL
);

-- Rollback procedure: Revert last N operations by turn_id
-- Mark main content as 'reverted' but hard delete related content

BEGIN IMMEDIATE;

-- Step 1: Identify the turn_ids of the last N operations to revert
WITH OperationsToRevert AS (
    SELECT DISTINCT turn_id
    FROM operations_log
    WHERE status = 'active'
    ORDER BY timestamp DESC
    LIMIT ? -- Parameter: number of operations to revert (N)
),
-- Step 2: Mark operations in log as reverted
UpdatedLog AS (
    UPDATE operations_log
    SET status = 'reverted'
    WHERE turn_id IN (SELECT turn_id FROM OperationsToRevert)
    RETURNING *
)

-- Step 3: Soft-delete main content items by marking status
UPDATE content_items
SET status = 'reverted'
WHERE turn_id IN (SELECT turn_id FROM OperationsToRevert)
AND status = 'active';

-- Step 4: Hard-delete related content rows
DELETE FROM related_content
WHERE turn_id IN (SELECT turn_id FROM OperationsToRevert);

-- Optional: Cleanup old reverted operations after some time
-- DELETE FROM operations_log WHERE status = 'reverted' AND timestamp < datetime('now', '-30 days');

COMMIT;
