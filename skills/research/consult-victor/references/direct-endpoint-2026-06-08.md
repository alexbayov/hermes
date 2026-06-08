# Session lessons: direct endpoint Victor calls (2026-06-08)

## What changed since last update

**Odysseus bridge is completely broken for Viktor (2026-06-08).** Every attempt via `localhost:7000/api/chat` returns `{"response":"[proxy error: Slack chat.postMessage error: not_authed]"}`. Session creation (`POST /api/session`) also fails with `endpoint_url is required` regardless of payload format. **Viktor ONLY works through the direct endpoint** (`127.0.0.1:8799/v1/chat/completions` or `172.17.0.1:8799/v1/chat/completions`).

## Proven pattern: direct endpoint atomic question

```bash
# 1. Write payload to file (AVOIDS bash JSON quoting hell)
cat > /tmp/viktor_payload.json << 'EOF'
{
  "model": "viktor",
  "messages": [
    {"role": "system", "content": "You are a senior SQLite architect."},
    {"role": "user", "content": "How to add FTS5 to a SQLite messages table?"}
  ],
  "max_tokens": 8000,
  "temperature": 0.1
}
EOF

# 2. curl with timeout=600 (terminal tool, NOT execute_code)
curl -s http://127.0.0.1:8799/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d @/tmp/viktor_payload.json \
  -o /tmp/viktor_response.json

# 3. Extract response (OpenAI format: choices[0].message.content)
python3 -c "import json; d=json.load(open('/tmp/viktor_response.json')); print(d['choices'][0]['message']['content'])"
```

**Why this works:**
- `write_file` + `curl -d @file` avoids ALL bash escaping issues (50% of previous failures were shell quoting)
- `terminal` with `timeout=600` allows Viktor's 200-500s responses (execute_code dies at ~30s and system-blocks re-runs)
- OpenAI-compatible format (`model`, `messages`, `max_tokens`) — direct endpoint understands this natively
- `max_tokens=8000` tested and works for large code responses (5722 chars in 60s for FTS5 + sqlite-vec)

## Proven success: FTS5 + sqlite-vec hybrid search

- **Question**: "I have a SQLite table messages... Need to replace LIKE %%search%% with two systems: 1. FTS5 virtual table... 2. sqlite-vec extension..."
- **Response**: 5722 chars, full architecture (FTS5 external-content + triggers, sqlite-vec vec0 schema, serialize_f32, RRF hybrid fusion, batch backfill, gotchas)
- **Framing**: "standalone journaling system" (no ENI/Hermes context)
- **Quality**: Production-ready, complete — NOT stubs this time. Viktor delivered full implementation.
- **Time**: ~60 seconds (direct endpoint, OpenAI format, max_tokens=8000)
- **Key insight**: Viktor's "stubs vs full code" depends on question specificity. A very specific technical question with clear schema gets full code. A broad architectural request gets skeleton.

## What to NEVER do

- **Never use `execute_code` for Viktor calls** — kills at ~30s, then system-blocks until user says "давай"
- **Never inline JSON in bash curl** — shell breaks on `"` inside `'...'` or vice versa, even with heredocs
- **Never try Odysseus for Viktor** — completely broken as of 2026-06-08, wastes 5+ minutes per attempt
- **Never use `python3 -c "..."` with JSON payload** — same quoting hell, plus execute_code timeout

## Tool selection matrix for Viktor calls

| Approach | Works? | Timeout | Quoting risk | Best for |
|---|---|---|---|---|
| `write_file` payload + `curl -d @` + `terminal` | ✅ YES | 600s | ZERO | All Viktor calls |
| `execute_code` with `urllib.request` | ❌ NO | ~30s | Low | Fast probes only (<10s) |
| Inline bash curl with JSON string | ❌ NO | 600s | HIGH | Never for complex JSON |
| Odysseus `POST /api/session` | ❌ NO | 30s | Medium | Never for Viktor |
