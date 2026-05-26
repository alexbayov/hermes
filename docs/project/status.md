# Hermes upgrade status

Last updated: 2026-05-14

## Executive summary

Hermes уже имеет чистый профиль, минимальный `profile/config.yaml`, базовые launchers и prompt-level правила.

Главный незакрытый риск: `core/` содержит рабочие изменения, но может быть незащищён от git-операций, если он игнорируется и не хранится в отдельном tracked upstream/fork. Сначала нужно зафиксировать стратегию сохранения core, затем code-enforced control layer:

1. tracked/forked `core/` или обязательный backup protocol;
2. hard-stop после tool result;
3. persistent task-state;
4. decision-log;
5. anti-carousel/progress detector;
6. behavior exams.

До закрытия этих пунктов WebBridge и registration/payment workflows считаются экспериментальными.

## Progress board

| ID | Priority | Track | Status | Owner role | Next action |
| --- | --- | --- | --- | --- | --- |
| HUP-00 | P0 | Repo hygiene | PARTIAL | Repo Steward | Разделить hygiene для profile/runtime и preservation для core |
| HUP-00A | P0 | Core preservation | READY | Repo Steward + Core Safety Engineer | Выбрать: track core, fork core или backup-before-git protocol |
| HUP-01 | P0 | Config lock sentinel | PARTIAL | Core Safety Engineer | Реализовать enforcement в `core/tui_gateway/server.py` |
| HUP-02 | P0 | HERMES_HOME propagation | TODO | Runtime Engineer | Проверить subprocess spawners и fallback на `~/.hermes` |
| HUP-03 | P1 | Code-enforced hard-stop | TODO | Core Safety Engineer | Добавить проверку tool results в main loop |
| HUP-04 | P1 | Persistent task-state | TODO | State Engineer | Добавить session YAML state files |
| HUP-05 | P1 | Decision log | TODO | State Engineer | Добавить append-only JSONL decisions |
| HUP-06 | P1 | Anti-carousel/progress detector | TODO | Control Loop Engineer | Детектировать tool/model loops без прогресса |
| HUP-07 | P2 | Behavior exams | TODO | QA Engineer | Перенести сценарии в executable tests |
| HUP-08 | P2 | Runtime metrics | TODO | Observability Engineer | Логировать tool usage, hard-stops, state transitions |
| HUP-09 | P3 | WebBridge safe profile | BLOCKED | Browser Workflow Engineer | Ждать HUP-03/HUP-06, затем включить guardrails |
| HUP-10 | P3 | Registration/payment workflows | BLOCKED | Browser Workflow Engineer | Ждать HUP-04/HUP-05/HUP-09 |
| HUP-11 | P3 | Skill priority system | TODO | Skills Librarian | User skills must override bundled skills |
| HUP-12 | P4 | Hermes Desktop feasibility | READY | Desktop Integration Engineer | Сделать isolated install/adopt test без записи в clean profile |
| HUP-13 | P4 | Desktop safe adoption | BLOCKED | Desktop Integration Engineer | Ждать HUP-01/HUP-03/HUP-06/HUP-12 |
| HUP-14 | P2 | Logs-first debugging | TODO | Observability Engineer | Научить Hermes сначала читать gateway/TUI/core logs |
| HUP-15 | P2 | Session summary protocol | TODO | State Engineer | Финальный отчёт по задаче + next resume point |
| HUP-16 | P2 | Safe script review | TODO | Core Safety Engineer | Классифицировать scripts перед запуском |
| HUP-17 | P2 | Memory vault usage | TODO | Skills Librarian | Научить пользоваться memory folders predictably |
| HUP-18 | P2 | Manual behavior exams | TODO | QA Engineer | 6 ручных экзаменов до executable tests |
| HUP-19 | P0 | PR Inspector quality gate | READY | Hermes PR Inspector | Проверять каждый PR перед merge |

## Implemented now

- Clean workspace rules documented in `AGENTS.md` and `CLAUDE.md`.
- Runtime paths documented in `profile/SOUL.md`.
- Minimal profile config exists at `profile/config.yaml`.
- `_config_lock: true` sentinel exists.
- `security.redact_secrets: true` exists.
- WebBridge test profile is isolated under `profiles/webbridge-test/`.
- logs, runtime, env files and database files are ignored by git policy.

## Not implemented yet

- `_config_lock` is not enforced in code.
- `Approval hard stop` is not enforced after tool execution.
- No persistent task-state files.
- No decision-log.
- No anti-carousel runtime halt.
- No executable behavior exams in this repo.
- WebBridge test profile should not be treated as production-ready.
- Hermes Desktop should not be pointed at the main clean profile until its write behavior is verified.
- Core changes are not safe while `core/` is only local and ignored.
- Logs-first debugging, final session summaries, safe script review, memory vault usage and manual exams need explicit protocols.
- PRs need strict inspector review before merge.

## Recommended next PR

Implement HUP-00A first:

> Decide and enforce how `/home/alex/hermes/core` is preserved before any more custom core work.

Only after HUP-00A is done, implement HUP-03:

> If a tool result contains `Command Approval Required`, `Command denied by user`, `BLOCKED`, `Do NOT retry this command` or approval timeout, Hermes must stop the current tool/model loop, summarize status, and wait for Alex.

This is the highest leverage fix because it turns the most important safety rule from prompt text into runtime behavior.

## Desktop note

Hermes Desktop (`github.com/fathah/hermes-desktop`) is promising, but should be treated as a separate integration track, not a simple upgrade.

Observed from upstream Desktop docs/source:

- local mode defaults to `~/.hermes`;
- first-run installer runs the official Hermes install script and manages `~/.hermes/hermes-agent`;
- Desktop can adopt a custom `HERMES_HOME` only if that home contains the layout it expects: `hermes-agent/venv/...` and `hermes-agent/hermes`;
- Desktop writes `desktop.json`, `.env`, `config.yaml`, profile files, session DB and staging data under `HERMES_HOME`;
- remote mode can connect to an API server without adopting local files.

Therefore the safe order is:

1. test Desktop on isolated `HERMES_HOME`, not `/home/alex/hermes/profile`;
2. verify it does not expand or overwrite locked config;
3. prefer remote-mode connection to clean Hermes gateway/API first;
4. only then consider adopting the main clean profile.
