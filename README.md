# Hermes Workspace Index

Workspace: `/home/alex/hermes/` | Profile: `profile/` | Upstream: `~/.hermes/hermes-agent`

---

## 1. Protocols → `docs/`

| Protocol | File |
|---|---|
| Behavior exams (auto) | `docs/behavior-exams.md` |
| Behavior exams (manual) | `docs/manual-behavior-exams.md` |
| Decision log | `docs/decision-log-protocol.md` |
| Logs-first debugging | `docs/logs-first-debugging-protocol.md` |
| Memory vault usage | `docs/memory-vault-usage.md` |
| PR quality gate | `docs/project/pr-quality-gate.md` |
| Progress detector | `docs/progress-detector-protocol.md` |
| Runtime metrics | `docs/runtime-metrics-protocol.md` |
| Safe script review | `docs/safe-script-review-protocol.md` |
| Session summary | `docs/session-summary-protocol.md` |
| Skill priority system | `docs/skill-priority-system.md` |
| Task state | `docs/task-state-protocol.md` |

## 2. Active Decisions → `profile/decision-log/`

Latest: `profile/decision-log/2026-05-29.jsonl`

- HUP-00A: Clean workspace structure
- HUP-01: `_config_lock` enforced in 3 write paths
- HUP-02: `HERMES_HOME` propagation verified
- HUP-03: Hard-stop guardrails enabled
- HUP-06: `progress_detector` as plugin
- HUP-07/18: Behavior exams implemented
- HUP-12: Desktop declared not feasible
- HUP-19: PR quality gate created

## 3. Current Config → `profile/config.yaml`

Key settings:
- Provider: `openai-api` via Fireworks (`kimi-k2p6`)
- Terminal backend: `local`, timeout 180s
- Memory: enabled, 2200 char limit, flush after 6 turns
- Session reset: both idle (24h) + at 04:00
- Tool loop guardrails: warnings + hard-stop enabled

## 4. Skills → `memory/skills/`

- `memory/skills/` — workspace skill store (empty; populated on demand)
- Built-in skills live in upstream `~/.hermes/hermes-agent/skills/`

## 5. How to run Hermes

### CLI (primary)
```bash
/home/alex/hermes/bin/hermes-clean
```

### Web Dashboard
```bash
cd ~/.hermes/hermes-agent && source venv/bin/activate
hermes dashboard --tui --no-open
# Then open http://127.0.0.1:9119/ in browser
```

### Desktop App
```bash
hermes-desktop --no-sandbox --ozone-platform=wayland
# Or for X11: hermes-desktop --no-sandbox
```

Launcher `bin/hermes-clean` sets `HERMES_HOME=/home/alex/hermes/profile`, sources `.env`, aliases `FIREWORKS_API_KEY` → `OPENAI_API_KEY`, then execs `hermes`.
