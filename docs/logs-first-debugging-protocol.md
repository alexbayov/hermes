# Logs-First Debugging Protocol (HUP-14)

## Rule

For any gateway/TUI/core failure, start from logs before changing code or config.

## Where to Look

| Symptom | First Log | Second Log | Third Log |
|---------|-----------|------------|-----------|
| Agent loop hanging | `~/.hermes/logs/agent.log` | `~/.hermes/logs/gateway.log` | session JSON |
| Tool execution fails | `~/.hermes/logs/agent.log` | terminal output in session JSON | `errors.log` |
| Provider 401/429/500 | `agent.log` (API call line) | `errors.log` | retry backoff in session |
| Config expanded unexpectedly | `agent.log` | `config.yaml` diff | `errors.log` |
| Subagent timeout | `subagent-timeout-*.log` | `agent.log` | session JSON |
| Browser/WebBridge failure | `agent.log` | screenshot path in session | `errors.log` |

## Log Locations

```
~/.hermes/logs/agent.log       — INFO+, main agent loop
~/.hermes/logs/errors.log       — WARNING+, failures only
~/.hermes/logs/gateway.log      — gateway messages, Telegram/Discord events
~/.hermes/logs/session_*.json   — full conversation trajectory
~/.hermes/logs/subagent-*.log   — subagent timeout diagnostics
```

## Quick Commands

```bash
# Last 50 lines of agent log
hermes logs --level error -n 50

# Follow live logs
hermes logs --follow

# Specific session
grep -i "session_id=abc123" ~/.hermes/logs/agent.log | tail -20

# Errors only
tail -100 ~/.hermes/logs/errors.log
```

## Report Template

When filing a bug or asking for help, always include:
1. Log snippet (20 lines around the error)
2. Session ID
3. Provider + model
4. Steps to reproduce
5. Expected vs actual behavior

## No Secrets in Reports

- Scrub API keys, tokens, passwords before sharing logs
- Use `agent/redact.py:redact_sensitive_text(text, force=True)` if automating
