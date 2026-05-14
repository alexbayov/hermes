# Hermes local project rules

This repository is the clean local Hermes workspace for Alex.

## Layout

- `/home/alex/hermes/core` — fresh upstream Hermes source clone. Treat as external upstream code.
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
- Do not modify upstream Hermes core casually. If core changes are needed, explain why first.
- Do not delete or rename memory folders without explicit confirmation from Alex.

## Default runtime

Use:

```bash
hermes-clean
HERMES_HOME=/home/alex/hermes/profile
vault_path=/home/alex/hermes/memory
file, web, skills, memory, todo, terminal, clarify, session_search

