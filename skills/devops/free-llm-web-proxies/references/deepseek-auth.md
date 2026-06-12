# DeepSeek Auth Format (FreeDeepseekAPI)

Source repo: `ForgetMeAI/FreeDeepseekAPI`

## Required auth JSON (`deepseek-auth.json`)

```json
{
  "token": "<bearer-token-from-cookie>",
  "hif_dliq": "<x-hif-dliq-header-or-empty>",
  "hif_leim": "<x-hif-leim-header-or-empty>",
  "cookie": "ds_session_id=<...>; aws-waf-token=<...>; smidV2=<...>; .thumbcache_<...>=<...>; ...",
  "wasmUrl": "https://fe-static.deepseek.com/chat/static/sha3_wasm_bg.7b9ca65ddd.wasm"
}
```

## Field sources

| Field | Source | How to obtain |
|-------|--------|---------------|
| `token` | `Authorization` header or `localStorage.userToken` | Strip `Bearer ` prefix from Network tab header |
| `cookie` | `Request Headers → cookie:` from Network tab | Full semicolon-separated string; includes HttpOnly cookies |
| `hif_dliq` | `x-hif-dliq` request header | Anti-bot fingerprint; optional but recommended |
| `hif_leim` | `x-hif-leim` request header | Same as above |
| `wasmUrl` | Static (default) | Only needed for WASM challenge; hardcoded default works |

## Chrome extension flow (most reliable)

Many repos ship a `chrome-extension/` directory. Load it as unpacked extension in Chrome while logged into the web chat, click "Collect", copy/download the JSON.

## Cookie-only fallback (manual DevTools extraction)

When the Chrome extension is unavailable, extract auth manually from an already logged-in browser session. **Do not rely on `document.cookie` alone — it omits HttpOnly cookies like `ds_session_id`.**

### Reliable extraction method

1. Open DevTools → **Network** tab.
2. Send any message in the DeepSeek chat.
3. Click the `chat` / `api/chat` / `completion` request.
4. In **Request Headers**, copy the full `cookie:` string — this includes all cookies (HttpOnly + visible).
5. Also copy the `Authorization:` header value and strip `Bearer ` to get the `token`.
6. Look for `x-hif-dliq` and `x-hif-leim` headers — copy them too if present.

### Token from localStorage (fallback)

In DevTools Console:
```js
copy(localStorage.getItem('userToken'))
// or
copy(localStorage.getItem('access_token'))
// or dump everything:
copy(JSON.stringify(localStorage, null, 2))
```

### Constructing the JSON manually

```bash
jq -n \
  --arg token "YOUR_TOKEN" \
  --arg hif_dliq "YOUR_HIF_DLIQ_OR_EMPTY" \
  --arg hif_leim "YOUR_HIF_LEIM_OR_EMPTY" \
  --arg cookie "ds_session_id=YOUR_ID; aws-waf-token=YOUR_WAF; smidV2=YOUR_V2; .thumbcache_...=..." \
  '{token: $token, hif_dliq: $hif_dliq, hif_leim: $hif_leim, cookie: $cookie, wasmUrl: "https://fe-static.deepseek.com/chat/static/sha3_wasm_bg.7b9ca65ddd.wasm"}' \
  > deepseek-auth.json
```

The `cookie` field must be a **single semicolon-separated string** (`name=value; name2=value2`), not an array. The `auth:import` script normalizes this format.

### Common cookie fields seen in the wild

- `ds_session_id` — HttpOnly, session-bound, **most critical**
- `aws-waf-token` — WAF challenge, expires in minutes to hours
- `smidV2` — device fingerprint
- `.thumbcache_*` — blob cache, may be required for some endpoints
- `ds_cookie_preference` — consent, usually optional
- `__cf_bm`, `cf_clearance` — Cloudflare, IP-bound

## Auth expiry and session lifecycle

**Cookies are NOT eternal.** Expect re-auth every few hours to days depending on the field:

| Cookie / Token | Typical TTL | Symptoms when expired |
|---|---|---|
| `ds_session_id` | Session (1–2 hours idle) | `401 Unauthorized`, `403 Forbidden` |
| `aws-waf-token` | 10–30 minutes | `403` with WAF block page |
| `__cf_bm` / `cf_clearance` | Minutes to hours, IP-bound | Cloudflare challenge loop |
| `hif_dliq` / `hif_leim` | Tied to session | Same as session expiry |

**The server does NOT auto-reload auth.** `server.js` reads `deepseek-auth.json` **once at startup**. After auth expires:
1. The proxy will return `401/403/429`.
2. The account enters a **10-minute cooldown** (`DEFAULT_ACCOUNT_COOLDOWN_MS = 10 * 60 * 1000`).
3. After cooldown it retries; if still failing, it cools down again.
4. **No automatic re-auth.** You must manually re-run `npm run auth:import` with fresh cookies and restart the service, OR implement a cron/watcher that does this.

### Reload without restart

The current FreeDeepseekAPI does not hot-reload auth. To force a reload, restart the service:

```bash
systemctl restart deepseek-api.service
```

## Import command

```bash
cd /opt/FreeDeepseekAPI
npm run auth:import -- --input ./deepseek-auth.json
```

**Critical:** `npm run auth:import` must run from the repo root (where `package.json` exists). Running from `~` or another directory will fail with `npm error code ENOENT` because npm cannot find `package.json`.

Or simply place `deepseek-auth.json` in the repo root; the server reads it automatically on startup.

## Headless VPS flow

1. On local machine with GUI: run `npm run auth`, save JSON, or extract cookies manually via Network tab.
2. `scp deepseek-auth.json root@vps:/opt/FreeDeepseekAPI/`
3. On VPS: `chmod 600 deepseek-auth.json`
4. Import: `cd /opt/FreeDeepseekAPI && npm run auth:import -- --input ./deepseek-auth.json`
5. Start: `systemctl daemon-reload && systemctl enable --now deepseek-api.service`

## Pitfall: snap Chromium

If `npm run auth` fails with CDP connection errors on Ubuntu, check if Chrome is a snap package. Set `CHROME_PATH` to a non-snap binary:

```bash
export CHROME_PATH=/usr/bin/google-chrome-stable
# or download Chrome for Testing via Puppeteer
```
