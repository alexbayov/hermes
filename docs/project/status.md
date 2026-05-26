# Hermes upgrade status

Last updated: 2026-05-14

## Executive summary

Hermes уже имеет чистый профиль, минимальный `profile/config.yaml`, базовые launchers и prompt-level правила.

Главный незакрытый риск: критические правила поведения пока в основном текстовые. Нужен code-enforced control layer:

1. hard-stop после tool result;
2. persistent task-state;
3. decision-log;
4. anti-carousel/progress detector;
5. behavior exams.

До закрытия этих пунктов WebBridge и registration/payment workflows считаются экспериментальными.

## Progress board

| ID | Priority | Track | Status | Owner role | Next action |
| --- | --- | --- | --- | --- | --- |
| HUP-00 | P0 | Repo hygiene | DONE | Repo Steward | Поддерживать `.gitignore`, не коммитить runtime/secrets |
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

## Implemented now

- Clean workspace rules documented in `AGENTS.md` and `CLAUDE.md`.
- Runtime paths documented in `profile/SOUL.md`.
- Minimal profile config exists at `profile/config.yaml`.
- `_config_lock: true` sentinel exists.
- `security.redact_secrets: true` exists.
- WebBridge test profile is isolated under `profiles/webbridge-test/`.
- `core/`, logs, runtime, env files and database files are ignored by git policy.

## Not implemented yet

- `_config_lock` is not enforced in code.
- `Approval hard stop` is not enforced after tool execution.
- No persistent task-state files.
- No decision-log.
- No anti-carousel runtime halt.
- No executable behavior exams in this repo.
- WebBridge test profile should not be treated as production-ready.

## Recommended next PR

Implement HUP-03 first:

> If a tool result contains `Command Approval Required`, `Command denied by user`, `BLOCKED`, `Do NOT retry this command` or approval timeout, Hermes must stop the current tool/model loop, summarize status, and wait for Alex.

This is the highest leverage fix because it turns the most important safety rule from prompt text into runtime behavior.
