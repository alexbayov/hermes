# Hermes local project rules

This repository is the clean local Hermes workspace for Alex.

Before doing any work, read `docs/project/status.md` and `docs/project/handoff.md`.

## Layout

- `/home/alex/hermes/core` — Hermes core. If it contains custom patches, it must be tracked or backed up before git operations.
- `/home/alex/hermes/profile` — clean Hermes profile (`HERMES_HOME`).
- `/home/alex/hermes/memory` — clean Hermes memory/vault.
- `/home/alex/hermes/bin` — local launcher and helper scripts.
- `/home/alex/hermes/docs` — setup and operations docs.
- `/home/alex/hermes/logs`, `/home/alex/hermes/runtime`, `/home/alex/hermes/backups` — local runtime data, not for git.

## Do not do

- Do not use `/home/alex/repos/hermes-agent` as the active runtime.
- Do not copy old Sonya/B17/AI News/editorial config into this clean profile.
- Do not commit secrets, `.env`, logs, sessions, sqlite/db files, browser profiles or caches.
- Do not run broad `git add .`; add files explicitly.
- Do not modify Hermes core casually. If core changes are needed, first explain why and confirm the core preservation strategy in `docs/project/backlog.md` HUP-00A.
- Do not delete or rename memory folders without explicit confirmation from Alex.

## Git hard stops

Do not run `git pull --rebase`, `git rebase`, `git reset`, `git clean`, broad checkout, or any destructive git operation until you have verified how `/home/alex/hermes/core` is protected.

If `core/` is ignored or untracked and contains custom work, stop and create a backup first:

```bash
mkdir -p /home/alex/hermes/backups
tar -czf /home/alex/hermes/backups/core-before-git-$(date +%Y%m%d-%H%M%S).tar.gz -C /home/alex/hermes core
git -C /home/alex/hermes status -sb
```

Never leave hard-stop, anti-carousel, task_state, decision_log, metrics, behavior exams, or custom toolsets only as ignored local files.

Preferred long-term model: keep custom core changes in a tracked core fork/branch or tracked `core/` subtree, then reference the commit from this workspace.

## Default runtime

Use:

```bash
hermes-clean
HERMES_HOME=/home/alex/hermes/profile
vault_path=/home/alex/hermes/memory
file, web, skills, memory, todo, terminal, clarify, session_search
```

## Current upgrade plan

Start here:

```text
docs/project/status.md
docs/project/backlog.md
docs/project/handoff.md
```

Current first priority: HUP-00A core preservation.
