# Direct Endpoint Usage Log (2025-06-08)

## Endpoint details
- **URL**: `http://127.0.0.1:8799/v1/chat/completions`
- **Model**: `viktor` (claude4_7_opus)
- **Auth**: `Authorization: Bearer *** (static, no dynamic token)
- **Format**: OpenAI-compatible (`choices[0].message.content`)
- **Latency**: ~200 seconds for atomic questions (SQLite triggers, ~500 tokens response)
- **Reliability**: 100% success rate for single atomic questions (1/1 tested)

## Usage pattern
```python
import json, urllib.request

body = json.dumps({
    "model": "viktor",
    "messages": [{"role": "user", "content": "How do I write SQLite triggers for audit logging?"}],
    "max_tokens": 1500
}).encode()

req = urllib.request.Request(
    "http://127.0.0.1:8799/v1/chat/completions",
    data=body,
    headers={"Content-Type": "application/json", "Authorization": "Bearer viktor"},
    method="POST"
)
with urllib.request.urlopen(req, timeout=300) as resp:
    data = json.loads(resp.read().decode())
    print(data["choices"][0]["message"]["content"])
```

## Key differences from Odysseus bridge

| Aspect | Direct endpoint | Odysseus bridge |
|--------|--------------|-----------------|
| URL | `127.0.0.1:8799/v1/chat/completions` | `localhost:7000/api/chat` |
| Auth | `Bearer viktor` (static) | `Bearer ody_*` (dynamic token) |
| Response format | OpenAI `choices[0].message.content` | Plain `{"response":"..."}` |
| Session creation | Not needed (stateless) | Required (`POST /api/session`) |
| Context persistence | None (each call independent) | Yes (session-scoped) |
| Multi-turn | No | Yes |
| Timeout | ~200s | ~200s |
| Best for | Single atomic questions | Multi-turn conversations |

## When to use direct endpoint
- Odysseus is down or slow
- Single atomic question (no need for session persistence)
- Want to avoid session creation boilerplate
- Avoiding Odysseus session poisoning issues

## When to use Odysseus
- Multi-turn conversation needed
- Need session context/history between calls
- Want to use Odysseus UI features (RAG, documents, etc.)

## Proven success (2025-06-08)
- Question: "How do I write SQLite AFTER INSERT/UPDATE/DELETE triggers for audit logging?"
- Response: Full CREATE TRIGGER SQL with `json_object()` snapshots, `NEW.*` / `OLD.*` references, `WHEN` clauses for UPDATE deduplication
- Quality: Production-ready, concise, well-structured
- Time: 204.7 seconds

- Question (compact, max_tokens=1500): "Design compact Python validate_and_repair: reverse JSONL read, identity keys, dedup, idempotent backfill. No explanations, code only."
- Response: 4353 chars, architecturally correct (reverse iteration, dedup, INSERT/UPDATE idempotency, dry-run flag)
- Quality: Good structure, minor truncation at end (payload.get() incomplete) — enough for skeleton
- Time: 238 seconds

## Limitations discovered
- No `temperature` or `top_p` parameters tested (may not support)
- No streaming tested (may not support)
- No tool use tested
- No context between calls (stateless)
- **execute_code is UNSAFE for Viktor**: `execute_code` tool kills the script at ~30s and then **system-blocks re-runs until user explicitly says "давай"**. Always use `terminal` with `timeout=300` (or `background=true`).
