# External AI Consultation Workflow — ENI Memory System

## When to Use
When facing architectural decisions, complex schema design, or system-wide refactoring that exceeds local reasoning capacity. Do not improvise architecture alone — escalate to Victor (claude4_7_opus via Odysseus proxy).

## User Preference
"Спрашивай, если сложно, спрашивай грузопус" — ask if difficult, ask the big guy.

## Steps

### 1. Gather Diagnostic Data
```python
import sqlite3, json, os

DB = '/root/.hermes/data/eni_memory.db'
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

data = {
    "db_size_kb": os.path.getsize(DB) / 1024,
    "sessions": [...],  # count, avg messages, active session
    "messages": [...],  # total, last 10
    "decisions": [...],
    "artifacts": [...],
    "issues": [...],
}
```

### 2. Send to Victor via Lindy2API
```bash
curl -s -X POST http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  --data-binary @/tmp/victor_request.json \
  -o /tmp/victor_response.json
```

### 3. Parse Response
- Victor returns markdown with code blocks
- Extract using regex: `r'```(?:python|sql)\n(.*?)```'`
- Write to files, verify, commit

### 4. Save Response
Always save Victor's full response to `/root/.hermes/plans/victor-<topic>-spec.md` for future reference.

## Size Limits
- Lindy2API has a 4096 token limit per request
- Compress large payloads by summarizing or sampling
- For very large DBs, send only statistics (counts, sizes) not full rows

## Example Prompt Template
```json
{
  "model": "claude4_7_opus",
  "messages": [
    {
      "role": "system",
      "content": "You are a senior software architect reviewing..."
    },
    {
      "role": "user",
      "content": "Review this SQLite schema and scripts. Identify issues, suggest improvements, prioritize by impact.\n\nSCHEMA:\n{{schema_sql}}\n\nSCRIPTS:\n{{scripts_summary}}\n\nCURRENT ISSUES:\n{{known_issues}}"
    }
  ]
}
```
