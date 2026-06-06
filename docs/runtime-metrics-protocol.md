# Runtime Metrics Protocol (HUP-08)

## Purpose

Make Hermes behavior inspectable without reading huge logs.

## Metrics Collected

| Metric | Source | Where Written |
|--------|--------|---------------|
| api_calls_total | session | logs/session_<id>.json |
| hard_stop_encounters | guardrail | logs/session_<id>.json |
| task_state_transitions | task-state | profile/task-state/*.yaml |
| repeated_failures_by_tool | guardrail | logs/session_<id>.json |
| config_write_attempts | config_lock | logs/agent.log (warning) |
| browser_approval_gates | browser tool | logs/session_<id>.json |
| tokens_prompt / tokens_completion / tokens_total | API response | logs/session_<id>.json |
| estimated_cost_usd | usage pricing | logs/session_<id>.json |

## Access

```bash
# Session summary (last 24h)
python3 -c "
import json, glob, sys
for f in sorted(glob.glob('/home/alex/hermes/logs/session_*.json'))[-5:]:
    d=json.load(open(f))
    print(f'{f}: calls={d.get(\"api_calls\",0)}, hard_stops={d.get(\"hard_stops\",0)}, cost={d.get(\"cost\",\"N/A\")}')
"

# Or via Hermes slash command
# /status  — shows current session metrics
```

## Design Principles

1. **No secrets in metrics** — token counts, not content.
2. **Append-only runtime logs** — not committed to git.
3. **Summary command** — one-liner health check, not log grepping.
4. **Per-session granularity** — aggregate across sessions for trends.

## Future Enhancements

- Prometheus-compatible endpoint for external dashboards
- SQLite summary table for fast querying
- Cron job to email weekly metrics digest
