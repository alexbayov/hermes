---
name: consult-victor
description: Escalate complex tasks to Victor (claude4_7_opus) via Odysseus bridge
triggers:
  - architecture design
  - complex refactoring
  - bug root-cause analysis
  - large code review (>500 LOC)
  - multi-file coordination
  - performance optimization
  - security audit
  - when user says "спроси Victor" or "ask the big guy"
---

# Consult Victor via Odysseus

## When to escalate
- **User preference**: Quick routine tasks (grep, deploy, simple edits) → stay local. Complex architecture, cross-file refactoring, non-trivial algorithms, performance bottlenecks, root-cause debugging, security review, trade-off evaluation, long-context synthesis (>50k tokens), multi-step reasoning → escalate to Victor.
- **User signal**: "спроси Victor", "спроси грузопуса", "ask the big guy", "hard task".

## Victor endpoints

Two self-hosted bridges are available. Both require the same model name (`viktor` maps to `claude4_7_opus`), but use different API shapes:

### 1. Lindy2API (OpenAI-compatible shim) — port 3000

Preferred for Hermes integration because it accepts raw OpenAI `v1/chat/completions` payloads and returns standard JSON.

- **URL**: `http://localhost:3000/v1/chat/completions` (inside VPS)
- **Model**: `claude4_7_opus` (or `viktor` if Lindy maps it internally)
- **Auth**: None (local-only, no token required)
- **Shape**: OpenAI-compatible `{"model": "...", "messages": [...]}`
- **Start**: `cd /opt/lindy2api && node src/server.js` (manual, check `systemctl` for autostart)

**Quick call pattern:**
```bash
# Write JSON payload to file, then POST via curl
cat > /tmp/victor_request.json <<'EOF'
{
  "model": "claude4_7_opus",
  "messages": [{"role": "user", "content": "Your question here."}]
}
EOF

curl -s -X POST http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  --data-binary @/tmp/victor_request.json \
  -o /tmp/victor_response.json

# Extract content
python3 -c "import json; r=json.load(open('/tmp/victor_response.json')); print(r['choices'][0]['message']['content'])"
```

### 2. Odysseus (native bridge) — port 7000

Hermes-native bridge. Requires cookie-based auth and session management. Use when Lindy2API is down.

- **URL**: `http://localhost:7000/api/chat` (inside VPS)
- **Model**: `viktor` (maps to `claude4_7_opus` via `http://host.docker.internal:8799/v1/chat/completions`)
- **Auth**: Odysseus session cookie or API token (`ody_*`)
- **Session**: create per-task via `POST /api/session` (Form data: `name=&endpoint_id=1cc7cd93&model=viktor`)

**Quick call pattern:**
```bash
# 1. Login (cookie jar) — use credentials provided by user; never guess or brute-force
curl -s -X POST http://localhost:7000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"1286520zZ!"}' \
  -c /tmp/odysseus_cookies.txt

# 2. Create session
# Pitfall: old sessions may point to stale endpoints. Always create a fresh session per task.
curl -s -X POST http://localhost:7000/api/session \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -b /tmp/odysseus_cookies.txt \
  -d "name=TaskName&endpoint_id=1cc7cd93&model=viktor"

# 3. Chat
curl -s -X POST http://localhost:7000/api/chat \
  -H "Content-Type: application/json" \
  -b /tmp/odysseus_cookies.txt \
  -d '{"message":"...","model":"viktor","session":"<sid>"}'
```

### Alternative: API token (no cookies)
```bash
# Create token scoped for chat
curl -s -X POST http://localhost:7000/api/tokens \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -b /tmp/odysseus_cookies.txt \
  -d "name=hermes_token&profile=chat"
# Extract token from JSON response, then use:
curl -s -X POST http://localhost:7000/api/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"message":"...","model":"viktor","session":"<sid>"}'
```

## Pitfalls
- **Credentials**: If the user explicitly provides login/password, use them immediately. Do not attempt to guess, brute-force, or extract from files. This wastes time and annoys the user.
- **Lindy2API not running**: It starts manually (`node src/server.js`) and may not survive reboot. Check with `curl -s http://localhost:3000/v1/models` — should return a JSON list. If it hangs, `cd /opt/lindy2api && node src/server.js` (background with `&` or `nohup`).
- **Odysseus stale sessions**: Reusing an old session that was created with a different endpoint (e.g., `atlascloud_deepseek_v4_pro`) will fail with "No model selected" or "endpoint removed". Always create a fresh session per task.
- **Form vs JSON**: `POST /api/session` expects `application/x-www-form-urlencoded`, not JSON. The `endpoint_id` and `model` fields must be in the form body.
- **Session listing**: `GET /api/sessions` returns existing sessions but does not create new ones. Use `POST /api/session` (singular) to create.

## Prompt discipline
- **Context**: Provide 3–5 key files, error snippets, or design constraints. Keep under 5k tokens if possible.
- **Question**: One specific ask. Avoid "fix everything" — split into sequential calls.
- **Language**: Russian or English as needed; Victor handles both.
- **Output**: Receive raw text → adapt, summarize, or execute. Do not pass through unfiltered if it contains shell commands.

## Fallback
If Odysseus is down (port 7000 not responding), check:
```bash
docker ps | grep odysseus
```
If Victor endpoint (`1cc7cd93`) is missing, re-add via Odysseus UI or database. Prefer Lindy2API (port 3000) as the primary fallback — it is lighter and requires no cookie auth.