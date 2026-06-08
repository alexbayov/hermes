# Parent Chain & Session Lifecycle

Session restarts (reboot, compaction, long Telegram thread) create NEW sessions in the DB. Without linkage, context is lost.

## Architecture

`sessions` table has `parent_session_id`. When a session ends, `session_end_start.py --end --start` closes it and creates a new one with the old ID as parent.

`resume_context.py` traverses the parent chain if the current session has zero messages. It pulls the last 3 messages from the most recent ancestor that has data, plus a synthetic `[... context from parent session ...]` marker. Decisions, issues, and artifacts are also inherited from the parent.

## Why this matters

Hermes compacts / reboots the Telegram thread frequently. If the new session starts empty, the agent would have no memory of what was just decided. The parent chain makes context survive across reboots without inflating the active session row count.

## Pitfall discovered

`validate_last_turn.py` originally used `SELECT MAX(turn_id) FROM messages` globally. This reported `last_turn=6` for a brand-new session that only had turns 0-1, because the closed parent session had turn 6. Fixed by scoping MAX to `WHERE session_id=?`.

## Script locations

- `/root/.hermes/scripts/session_end_start.py` — end current session, start new with parent link
- `/root/.hermes/scripts/resume_context.py` — restore context, traverses parent chain
- `/root/.hermes/scripts/validate_last_turn.py` — per-session gap detection + last role check
