# Qwen Auth Format (FreeQwenApi)

Source repo: `FreeQwenApi` (port 3264, service `freeqwen-api.service`)

## Architecture difference

Unlike FreeDeepseekAPI (which uses a single `deepseek-auth.json` with cookies), FreeQwenApi uses **Playwright** to open a headless browser, log into `chat.qwen.ai`, and extract **Bearer tokens** from the browser session. Tokens are stored in `session/tokens.json` and used via round-robin.

## Auth file: `session/tokens.json`

```json
[
  {
    "id": "qwen_1",
    "token": "Bearer <opaque-string>",
    "chatId": "<uuid>",
    "invalid": false,
    "resetAt": null
  }
]
```

## How auth is obtained

1. **Interactive (with GUI)**: `python main.py --auth` or similar — opens Playwright browser, user logs in, token saved.
2. **Headless (with credentials)**: Pass email/password env vars; Playwright fills the form and saves token.
3. **Manual**: Log in via regular browser, copy `Authorization` header or `localStorage` token, format into `tokens.json`.

## Token lifecycle

| Property | Behavior |
|---|---|
| `invalid` | Set to `true` when token fails (401/403). Skipped by round-robin. |
| `resetAt` | ISO timestamp. Token is ignored until this time (rate-limit cooldown). |
| Round-robin | `_pointer` cycles through valid tokens. |
| Cooldown | `mark_rate_limited(token_id, hours=24)` sets `resetAt` 24 hours ahead. |

## Auth expiry

Qwen tokens are **longer-lived** than DeepSeek cookies (days to weeks), but they do expire. There is **no automatic re-auth** in the current server — when all tokens are invalid or rate-limited, the proxy returns errors until manual re-auth.

## Pitfall: Chromium path

The service uses `CHROME_PATH=/usr/bin/chromium-browser` (set in systemd unit). If this binary is missing or is a snap package, Playwright may fail. Ensure Chromium is installed:

```bash
apt install chromium-browser
# or set CHROME_PATH to a working binary
```

## Systemd service

```ini
[Unit]
Description=FreeQwen API Proxy
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/FreeQwenApi
ExecStart=/opt/FreeQwenApi/.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 3264
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
Environment=CHROME_PATH=/usr/bin/chromium-browser

[Install]
WantedBy=multi-user.target
```

## Re-auth flow (manual)

1. Stop service: `systemctl stop freeqwen-api.service`
2. Delete or backup `session/tokens.json`
3. Re-run auth: `cd /opt/FreeQwenApi && python main.py --auth` (or whatever the repo provides)
4. Start service: `systemctl start freeqwen-api.service`

## OmniGate integration

OmniGate points to `http://127.0.0.1:3264/api` (note: `/api`, not `/v1`). The FreeQwenApi `main.py` exposes OpenAI-compatible endpoints under `/api/` rather than `/v1/`.
