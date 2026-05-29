# Decision Log Protocol

## Location

```
/home/alex/hermes/profile/decision-log/<session_id>.jsonl
```

## Format

Append-only JSON Lines (JSONL), one decision per line.

## Fields

| Field | Type | Description |
|---|---|---|
| ts | ISO timestamp | When decision was made |
| decision | string | What was decided |
| reason | string | Why this decision was made |
| alternatives | array | Other options considered |
| risk | enum | low, medium, high |
| approved_by | string | alex, not_required, auto |
| context | object | Optional: task_id, tool_name, etc. |

## When to Log

- Changing profile/config/launcher
- Enabling browser/WebBridge/payment workflows
- Bypassing a documented default
- Entering blocked state
- Selecting provider/model defaults
- Any risky or irreversible action

## Example

```jsonl
{"ts":"2026-05-29T17:00:00Z","decision":"Switch provider from openrouter to openai-api","reason":"OpenRouter key exhausted (401), Fireworks key is active","alternatives":["Buy OpenRouter credits","Use Google Gemini free tier","Use local Ollama"],"risk":"low","approved_by":"alex","context":{"task":"HUP-00 migration","file":"config.yaml"}}
{"ts":"2026-05-29T17:05:00Z","decision":"Set default model to accounts/fireworks/models/kimi-k2p6","reason":"Best performance/price ratio for Alex's workload","alternatives":["kimi-k2p5","glm-5p1","gpt-4.1"],"risk":"low","approved_by":"not_required","context":{"task":"HUP-00 migration"}}
```

## Rules

- Append only — never edit existing lines
- No secrets in logs (reference variable names, not values)
- One file per session or one file per day (decide based on volume)
