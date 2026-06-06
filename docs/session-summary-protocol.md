# Session Summary Protocol (HUP-15)

## When to Write

At the end of every non-trivial task, write a short summary.

## Path

```
/home/alex/hermes/memory/tasks/<date>-<slug>.md
```

## Template

```markdown
---
date: YYYY-MM-DD
session_id: <id>
goal: <one sentence>
status: completed | blocked | cancelled
---

## Completed Steps

1. Step one
2. Step two

## Files Changed

- `path/to/file` — what changed

## Tests / Checks Run

- test_name — result

## Blockers

- <if any>

## Next Safe Step

- <what the next agent should do>

## Approvals Needed

- <if any>

## Links

- Commit/PR: <url>
- Decision log: <ref>
- Logs: <session_id>
```

## Rules

- No secrets in summaries
- One file per task (append if continuing)
- Link back to decision-log and task-state
- Include session_id for traceability
