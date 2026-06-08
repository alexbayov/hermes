# Victor V2 Full Architecture Spec — Condensed Reference

Full spec: `/root/.hermes/plans/eni-memory-v2-spec.md` (61KB)

Victor (claude4_7_opus via Lindy proxy) reviewed the memory system architecture and delivered a comprehensive v2 spec covering 8 sections.

## Spec Structure

| Section | Topic | Key Output |
|---------|-------|------------|
| 1 | Schema Evolution | `migrate_schema.py`, `schema_version` table, WAL, FK + CASCADE |
| 2 | Session Lifecycle | `session_end_start.py`, `compact_parents.py` (soft/hard tiers) |
| 3 | Data Integrity | `rollback_turn.py`, `backup_db.py`, retry loops, auto-repair |
| 4 | Context Optimization | `resume_context.py` with `message_count` fast-path, memory.md format |
| 5 | Event Sourcing | `journal.log` as write-ahead log, `persist.py --repair` |
| 6 | Edge Cases | 12-item table: DB locked, WAL growth, truncation, chain overflow |
| 7 | Implementation Order | P0→P4 ranked table with dependencies and effort estimates |
| 8 | Acceptance Criteria | Pass/fail gates for every deliverable |

## Key Architectural Decisions

### Two-Tier Compaction
- **Soft:** Every 10 closed sessions → summarize into `context_summary` on parent, mark as `compacted`
- **Hard:** If >2000 messages total → keep last 5 sessions full, delete older messages, preserve decisions/artifacts in summary

### Memory.md Optimized Format (2200 char budget)
- Session + parent IDs (~60 chars)
- Last turn + token count (~30 chars)
- Active decision IDs comma-separated (~100 chars) — NOT full text
- Open issue IDs (~60 chars)
- 1-line context summary (~150 chars)
- Recent artifacts (~200 chars)
- Key paths (~300 chars)
- **Buffer: ~1300 chars free-form**

### Event Sourcing Pattern (optional)
- `journal.log` = append-only write-ahead log (written BEFORE SQLite)
- SQLite = derived read-optimized view
- Crash recovery = replay `journal.log` into SQLite via `persist.py --repair`
- Deduplication: `session_id + turn_id + action` uniqueness check

### Lindy/Opus Proxy Limit
- Payloads > ~12KB timeout on `localhost:3000`
- Keep single requests under ~5KB
- Split large specs into multiple calls or save as local files
