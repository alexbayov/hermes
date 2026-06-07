# Diagnostic Scripts

Created during memory-system stress-testing session (June 2026).

## memory_health.py

Per-session integrity check plus global stats.

```bash
python3 /root/.hermes/scripts/memory_health.py
```

Reports:
- DB size (KB)
- Sessions count with parent links
- Messages per session, turn range, gaps (critical — missing turn IDs)
- Orphan decisions / artifacts / issues (should be 0)
- Content stats (total chars, avg per message)
- Decisions & issues grouped by status
- Recommendations (e.g., DB > 10MB → compaction needed)

## memory_query.py

Keyword search across all tables.

```bash
# stats only
python3 /root/.hermes/scripts/memory_query.py --stats

# search messages for keyword
python3 /root/.hermes/scripts/memory_query.py SQLite

# search decisions
python3 /root/.hermes/scripts/memory_query.py -t decisions memory

# limit results, filter by session
python3 /root/.hermes/scripts/memory_query.py -n 5 -s <session_id> proxy
```

Tables: `messages` (content), `decisions` (title), `artifacts` (name), `issues` (title).
