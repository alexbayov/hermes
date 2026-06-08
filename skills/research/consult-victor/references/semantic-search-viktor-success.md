# Proven success: FTS5 + sqlite-vec hybrid search (2026-06-08)

- **Question**: "I have a SQLite table messages... Need to replace LIKE %%search%% with two systems: 1. FTS5 virtual table... 2. sqlite-vec extension..."
- **Response**: 5722 chars, full architecture (FTS5 external-content + triggers, sqlite-vec vec0 schema, serialize_f32, RRF hybrid fusion, batch backfill, gotchas)
- **Framing**: "standalone journaling system" (no ENI/Hermes context)
- **Quality**: Production-ready, complete
- **Time**: ~60 seconds (direct endpoint, OpenAI format, max_tokens=8000)
- **Key technique**: `write_file` payload to `/tmp/payload.json`, then `curl -d @/tmp/payload.json -o /tmp/response.json` to avoid bash JSON quoting hell. `execute_code` is blocked for long calls (>30s); use `terminal` with `timeout=600`.

## Lesson: Bash JSON quoting hell
Never inline JSON with nested quotes in bash curl. The shell breaks on `"` inside `'...'` or vice versa. **Always** `write_file` the JSON payload to a temp file first, then `curl -d @/tmp/payload.json -o /tmp/response.json`. Python `urllib.request` from `execute_code` also fails for long calls (>30s). Use `terminal` with `timeout=600` for Viktor.

## Lesson: Odysseus Viktor is broken (2026-06-08)
Odysseus bridge (`localhost:7000/api/chat`) returns `not_authed` for `model: viktor`. Odysseus works for other models, but **Viktor only works through the direct endpoint** (`127.0.0.1:8799/v1`). Do not waste time on Odysseus for Viktor.
