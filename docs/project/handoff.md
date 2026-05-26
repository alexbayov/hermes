# Handoff for future Devin sessions

Use this file when Alex asks to continue Hermes upgrade work.

## First 10 minutes

1. Read:
   - `AGENTS.md`;
   - `profile/SOUL.md`;
   - `docs/project/status.md`;
   - the relevant card in `docs/project/backlog.md`.
2. If working on Alex's machine, verify core preservation before any git operation:

```bash
git -C /home/alex/hermes status -sb
git -C /home/alex/hermes ls-files core | sed -n '1,20p'
git -C /home/alex/hermes check-ignore -v core 2>/dev/null || true
```

If `core/` is ignored/untracked and may contain custom work, stop and do HUP-00A first.
3. Check repo state:

```bash
git status --short
git log --oneline -10
```

4. Do not assume live core is committed here. This repo may intentionally ignore `core/`.
5. If the task needs core changes, inspect `/home/alex/hermes/core` on Alex's machine or the provided export.

## Choose next work

Default order:

1. First unfinished `P0`, especially HUP-00A if `core/` is not protected.
2. Then `P1`.
3. Only then `P2`.
4. Do not start `P3` browser/WebBridge work until P1 control layer is done.

If Alex asks for WebBridge before P1 is done, explain briefly:

```text
WebBridge is blocked by control-layer safety. Recommended next step: hard-stop enforcement first.
```

If Alex asks for Hermes Desktop, do not suggest direct migration first. Use HUP-12:

```text
Desktop is promising, but it writes config/env/state under HERMES_HOME and expects a different layout. Recommended next step: isolated Desktop lab or remote-mode test.
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

Never keep custom `core/` patches only as ignored local files. If a task changes `/home/alex/hermes/core`, the patch must be committed to a tracked core repo/branch or backed up before any git operation.

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

## Desktop integration warning

Hermes Desktop local mode defaults to `~/.hermes` and expects:

```text
<HERMES_HOME>/hermes-agent
<HERMES_HOME>/hermes-agent/venv
<HERMES_HOME>/config.yaml
<HERMES_HOME>/.env
<HERMES_HOME>/state.db
<HERMES_HOME>/profiles/
```

Alex's clean Hermes is split across `core/`, `profile/`, `memory/`, `bin/`.

Safe first test:

```text
HERMES_HOME=/home/alex/hermes-desktop-lab
```

or Desktop remote mode to a clean Hermes API/gateway.

## Definition of done for upgrade tasks

A card is done only when:

- implementation exists;
- acceptance criteria are satisfied;
- relevant tests/exams pass or are documented as unavailable;
- project docs status is updated;
- Alex can understand the new state from `docs/project/status.md`.

## If core files disappeared

Do not panic and do not immediately rewrite the implementation from memory.

First check:

```bash
git -C /home/alex/hermes reflog --date=iso | sed -n '1,80p'
git -C /home/alex/hermes log --all --oneline -- core | sed -n '1,80p'
find /home/alex/hermes/backups -maxdepth 4 -type f 2>/dev/null | sort | tail -80
```

Then recover candidate files into `/tmp` and diff them against current live core.
