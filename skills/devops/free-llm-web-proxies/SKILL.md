---
title: Deploy Free LLM Web API Proxies
name: free-llm-web-proxies
description: Deploy and manage reverse-engineered free web-chat LLM proxies (FreeQwenApi, FreeDeepseekApi, etc.) that expose OpenAI-compatible APIs via browser session authentication.
version: 1.0.0
tags: [llm, proxy, reverse-engineered, web-api, free, nodejs, systemd, hermes]
---

# Free LLM Web API Proxies

Class of task: deploying reverse-engineered free web-chat LLM proxies that expose an OpenAI-compatible API endpoint from a free web UI (e.g. FreeQwenApi, FreeDeepseekApi). These proxies run locally as Node.js services and authenticate via browser cookies/session tokens extracted from the web chat UI.

## When to use

- The user wants to add a free LLM provider alongside existing paid ones
- A new reverse-engineered proxy repo (e.g. ForgetMeAI/FreeDeepseekApi, FreeQwenApi) has been identified
- The user asks to "deploy next to X" or "add a proxy for Y"
- The existing proxy is down or broken and a replacement is needed

## General pattern

All known proxies in this class follow the same lifecycle:

1. **Clone** the repo into `/opt/<repo-name>` (or `/opt/<service-name>`)
2. **Understand auth** — these proxies require a live web session; they are NOT key-based
3. **Extract/auth** — obtain cookie/token JSON from the browser (usually `*-auth.json`)
4. **Install** — typically `npm install` or zero-dep (Node.js 18+)
5. **Configure** — env vars or JSON auth file
6. **Test** — curl `/v1/models` or `/health`
7. **Systemd-ify** — create a persistent service with `Restart=always`
8. **Hermes config** — add `providers.<name>` pointing to `http://localhost:<port>/v1`

## Auth strategies (ranked by reliability)

### 1. Chrome extension export (most reliable)

Many repos ship a `chrome-extension/` directory. Load it as unpacked extension in Chrome while logged into the web chat, click "Collect", copy/download the JSON.

### 2. `npm run auth` (interactive, needs GUI or X11)

- Opens a Chrome/Chromium window via CDP (Chrome DevTools Protocol)
- User logs in manually, sends a message (e.g. "ok")
- Script extracts cookies + localStorage + wasm tokens
- Saves to `*-auth.json`
- **Pitfall**: on headless VPS this fails unless Xvfb + VNC or X11 forwarding is available
- **Pitfall**: Chromium snap package (`/snap/bin/chromium`) sometimes breaks CDP or sandbox; prefer binary Chrome if auth fails

### 3. Cookie copy from existing browser (manual)

- Export cookies from an already logged-in browser session (e.g. via `document.cookie` in DevTools Console or browser extension)
- Format into the expected JSON schema (token, cookie string, hif_dliq/hif_leim for DeepSeek, etc.)
- Import via `npm run auth:import -- --input ./cookies.json`

**Pitfall — `document.cookie` is incomplete**: `document.cookie` in DevTools Console **does NOT include HttpOnly cookies** (e.g. `ds_session_id` on DeepSeek). Use one of these instead:
- **Network tab** → send a message in chat → right-click the `chat`/`api` request → **Copy → Copy as cURL (bash)** → extract the full `cookie:` header string
- **Application → Cookies** → double-click the `Value` cell → `Ctrl+A` → `Ctrl+C` to copy the full value even if visually truncated
- Console: `copy(document.cookie)` copies the visible subset — good for non-HttpOnly cookies only

**For the token**: `localStorage.getItem('userToken')` or `localStorage.getItem('access_token')` in Console. Or copy the `Authorization` header from Network tab (strip `Bearer ` prefix).

### 4. Auth file migration (VPS flow)

- Do `npm run auth` on a local machine with GUI
- SCP the resulting `*-auth.json` to the VPS
- Import with `npm run auth:import` or just place in repo root
- Run with `NON_INTERACTIVE=1` or `SKIP_ACCOUNT_MENU=1`

## Systemd service template

```ini
[Unit]
Description=<Service Name> proxy
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/<repo-dir>
Environment=NON_INTERACTIVE=1
# Add other env vars here if needed
ExecStart=/usr/bin/node server.js
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
```

Register and start:

```bash
systemctl daemon-reload
systemctl start <service>.service
systemctl enable <service>.service
```

## Hermes provider configuration

```yaml
providers:
  <proxy-name>:
    name: "<Display Name>"
    base_url: "http://localhost:<port>/v1"
    api_key: "no-auth"
    models:
      <model-alias>: {}
```

Apply with `hermes config set providers.<proxy-name>.base_url http://localhost:<port>/v1`.

## Pitfalls

- **No auth = no start**: These proxies are stateful session proxies; they WILL fatal-exit if auth is missing. Do not expect a graceful degraded mode.
- **Cookie expiry**: Web sessions expire (days to weeks). If the proxy suddenly starts returning 401/403, re-auth is needed. Consider a cron job or health check that alerts on failure.
- **Port conflicts**: Check `ss -tlnp` before assigning a port. Default ports vary by repo (FreeQwenApi 3264, FreeDeepseekApi 9655).
- **Snap Chromium**: On Ubuntu, `/snap/bin/chromium` can break CDP auth flows. Use `CHROME_PATH` env var to point to a non-snap binary if auth fails.
- **Node version**: Most require Node 18+. Check `node -v` before `npm install`.
- **Working directory matters**: `npm run auth:import` must run from the repo root (where `package.json` exists). If run from elsewhere, `npm` will fail with `ENOENT package.json`.
- **Systemd daemon-reload**: After editing or creating a systemd unit file, `systemctl daemon-reload` is required before `systemctl start` will see the new or updated unit. This is easy to forget after `systemctl edit --full` or manual file edits.
- **Service names and ports (confirmed)**:
  - `deepseek-api.service` on port 9655 (`/opt/FreeDeepseekAPI`)
  - `freeqwen-api.service` on port 3264 (`/opt/FreeQwenApi`)
  - `omnigate.service` on port 8888 (`/opt/omnigate`)
- **Hermes reload**: After editing `config.yaml`, Hermes may need a restart or gateway refresh to pick up the new provider.
- **Working directory matters**: `npm run auth:import` must run from the repo root (where `package.json` exists). If run from elsewhere, `npm` will fail with `ENOENT package.json`.
- **Systemd daemon-reload**: After editing or creating a systemd unit file, `systemctl daemon-reload` is required before `systemctl start` will see the new or updated unit.

## Testing local gateways (OmniGate, etc.)

When multiple proxies are aggregated behind a local gateway (e.g. OmniGate at `http://localhost:8888/v1`):

1. **List models**: `curl http://localhost:8888/v1/models` — should return JSON with `data[].id` for each upstream model.
2. **Basic chat**: `curl .../v1/chat/completions` with `"messages":[{"role":"user","content":"ping"}]` — should return a text response.
3. **Tool calling**: Pass `"tools": [...]` and `"tool_choice": "auto"`. The model should return `tool_calls` with `finish_reason: tool_calls`. Then feed the tool result back via `role: tool` and verify the model finalizes with `finish_reason: stop`.
4. **Context retention**: Include multi-turn history and verify the model references earlier turns.
5. **Image generation**: Most local text gateways do **NOT** support `/v1/images/generations`. If you get `{"detail": "Not Found"}`, image generation is not available through that gateway. Use a separate image-generation provider (e.g. FAL, OpenAI DALL-E, Stable Diffusion) instead.

## References

- `references/deepseek-auth.md` — DeepSeek-specific auth format (hif_dliq, hif_leim, wasmUrl)
- `references/systemd-service-template.md` — copy-pasteable systemd unit with env vars
- `references/hermes-provider-config.md` — complete Hermes `providers` block examples
- `references/omnigate-testing.md` — testing recipes for local gateway endpoints (models, chat, tools, images)