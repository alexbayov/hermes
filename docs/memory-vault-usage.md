# Memory Vault Usage (HUP-17)

## Directory Structure

```
/home/alex/hermes/memory/
├── projects/          # Long-running project plans (active)
│   └── hermes-hup-upgrade.md
├── tasks/            # Task summaries and resume points
│   └── 2026-05-29-hup-batch.md
├── skills/           # Stable reusable procedures
│   └── linux-dev-workflow/SKILL.md
├── workflows/        # Proven recipes (tested patterns)
│   └── fireworks-api-migration.md
├── inbox/            # Unsorted input — review weekly
├── archive/          # Old/disabled context
│   └── sonya-v1-skills/
├── people/           # Contacts, preferences, relationships
└── journal/          # Daily notes, observations, ideas
```

## Rules

1. **Projects** — one file per active project, updated weekly
2. **Tasks** — one file per task, written at completion (see Session Summary Protocol)
3. **Skills** — must have `SKILL.md` with frontmatter, versioned
4. **Workflows** — proven only: must have worked ≥3 times before promoting
5. **Inbox** — temporary landing zone, review and file or delete weekly
6. **Archive** — never loaded unless Alex explicitly asks
7. **No secrets** — reference variable names, never values

## Legacy Cleanup

```bash
# Identify unclassified legacy files
find /home/alex/hermes/memory -type f -not -path "*/archive/*" | grep -v "\.md$"

# Move old Sonya/B17/temp-mail skills to archive
mv /home/alex/hermes/memory/skills/sonya-* /home/alex/hermes/memory/archive/
```

## Loading Behavior

- Hermes loads `skills/` and `workflows/` automatically on startup
- `projects/` loaded when referenced in task context
- `tasks/` loaded when resuming a specific task
- `archive/` excluded from automatic loading
