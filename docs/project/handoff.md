# Handoff for future Devin sessions

Use this file when Alex asks to continue Hermes upgrade work.

## First 10 minutes

1. Read:
   - `AGENTS.md`;
   - `profile/SOUL.md`;
   - `docs/project/status.md`;
   - the relevant card in `docs/project/backlog.md`.
2. Check repo state:

```bash
git status --short
git log --oneline -10
```

3. Do not assume live core is committed here. This repo may intentionally ignore `core/`.
4. If the task needs core changes, inspect `/home/alex/hermes/core` on Alex's machine or the provided export.

## Choose next work

Default order:

1. First unfinished `P0`.
2. Then `P1`.
3. Only then `P2`.
4. Do not start `P3` browser/WebBridge work until P1 control layer is done.

If Alex asks for WebBridge before P1 is done, explain briefly:

```text
WebBridge is blocked by control-layer safety. Recommended next step: hard-stop enforcement first.
```

## PR rules

- One card = one PR.
- Small diff.
- Update `docs/project/status.md` and `docs/project/backlog.md` in the same PR when status changes.
- Include tests/verification in PR body.
- Do not claim a card is `DONE` without acceptance criteria.

## Safety rules

Never commit:

- `.env`;
- real API keys/tokens;
- `profile/state.db`;
- `kanban.db`;
- runtime logs/sessions;
- browser profiles/caches;
- generated local reports with secrets.

If Hermes creates API keys during registration, store them only in local secret store or `.env`. Markdown may mention only variable names, not values.

## Live runtime facts

Authoritative clean profile:

```text
Core: /home/alex/hermes/core
HERMES_HOME: /home/alex/hermes/profile
Vault: /home/alex/hermes/memory
Launcher: /home/alex/hermes/bin/hermes-clean
```

Do not use:

```text
/home/alex/repos/hermes-agent
~/.hermes as active clean profile
old Sonya/B17/AI News/editorial memory
```

## Definition of done for upgrade tasks

A card is done only when:

- implementation exists;
- acceptance criteria are satisfied;
- relevant tests/exams pass or are documented as unavailable;
- project docs status is updated;
- Alex can understand the new state from `docs/project/status.md`.
