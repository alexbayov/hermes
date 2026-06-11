---
name: web-form-automation
description: Automating web form submission, multi-account onboarding, and automated workflow stacks. Patterns for React Hook Form, Next.js Server Actions, email automation, Playwright techniques, and bot detection evasion.
trigger: |
  When automating web form submission, multi-account onboarding, or automated workflow stack creation.
  When encountering React Hook Form, Next.js Server Actions, or other modern JS form frameworks.
  When setting up email automation for multi-account registration.
---

# Web Form Automation & Multi-Account Onboarding

## Architecture

```
scripts/
├── email_generator.py      # Pattern: a.bayov@domain.com, b.bayov@domain.com
├── email_tracker.json      # Tracks: used_addresses, next_letter, service_map
├── service_automator.py    # Per-service automation script
└── gmail_monitor.py        # Polls Gmail for verification codes/links
```

## Captcha Solving

When a form is blocked by an image/text CAPTCHA and manual interaction is not viable, use a captcha-solving service API. **CapMonster** is the preferred provider for this user.

> **User preference — PRIMARY approach:** Always try the captcha service **first**. Do **not** waste time on DIY OCR (tesseract, easyocr, paddleocr, custom shape matching) when a service with available balance exists. If the service fails or the key is dead, fall back to local OCR only after confirming unavailability.
>
> Frustration signal: "Ты шо меня не слушаешь?:) может тебе капча сервис дать? А то мучаешься?"

## API-First SPA Bypass (Supabase / Firebase / Auth0)

**Golden rule:** Before launching a browser or writing a Playwright script, always check whether the SPA exposes its backend API directly. Modern SPAs (React/Vue/Svelte) often delegate auth to a BaaS like Supabase, Firebase, or Auth0. The UI-layer captcha, redirects, and form validation may be bypassed entirely by calling the backend API.

### When to use
- The target is a SPA with `<div id="root"></div>` and a heavy JS bundle.
- `browser_navigate` times out or headless detection blocks the page.
- You see references to `supabase`, `firebase`, `auth0`, or `createClient` in the JS bundle.

### Technique
1. Download the main JS bundle (`/assets/index-*.js`).
2. Search for:
   - `supabase.co` or `firebaseio.com` → extract `projectRef` / `databaseURL`.
   - `eyJ[a-zA-Z0-9_-]*` → the longest matches are usually JWT `anon` / `apiKey` tokens.
   - `auth/v1/signup`, `auth/v1/token`, `/dbconnections/signup` → backend endpoints.
3. Validate the key by calling the health or token endpoint.
4. Use `curl` or `requests` to register/login directly.

**See `references/kimchi-registration.md` for the Supabase API-first success path**, and **`references/kimchi-auth0-login-failures.md` for the Auth0 login failure post-mortem** — especially the multi-backend auth mismatch and captcha-state regeneration pitfalls.

**Reusable script:** `scripts/extract-supabase-key.py` — pass a JS bundle path, it scans for JWT tokens, decodes payloads, and writes the best candidate to `/tmp/supabase_best_key.txt`.

## Terminal Output Truncation Pitfall

Hermes' terminal tool truncates long output strings (replacing the middle with `...`). This is catastrophic when copying API keys, JWT tokens, or base64 strings from terminal stdout.

**Rule:** Always write long tokens to a file, never rely on terminal copy-paste:
```python
with open('/tmp/key.txt', 'w') as f:
    f.write(token)
```

**Verification:** After extraction, check file size (`wc -c /tmp/key.txt`) and head/tail chunks rather than trusting the full terminal output.

## Human-in-the-Loop Automation Preference

This user prefers **scripted, step-by-step automation** with **minimal unexplained delays**. Do not disappear into 10+ minute investigation loops without providing checkpoint updates.

**Pattern:**
1. Announce what you're about to do (one sentence).
2. Run the step.
3. Report the result immediately (success/failure + key data).
4. If blocked, state the blocker and ask for direction — don't spiral.

**Anti-pattern:** Long silent investigation → user gets "может конечно ты там хорошо разбиралась, но вот чото неэффективно".

### CapMonster Service Integration

**Requirements:**
- `clientKey` from CapMonster dashboard
- The CAPTCHA image as a PNG/JPG file or base64 string

**Credential Discovery:**
When the CapMonster key is not immediately available, check in this order:
1. Environment variables: `CAPMONSTER_KEY`, `CAPMONSTER_CLIENT_KEY`
2. Hermes profile `.env` files: `~/.hermes/profiles/<name>/.env`
3. `/tmp/` or `/root/.env` for temporary or project-specific keys
4. Session memory or previous conversation context

**Pitfall:** `requests.get()` cannot fetch `data:image/svg+xml;base64,...` URIs. Extract the base64 payload inline:
```python
src = await img.get_attribute("src")  # data:image/svg+xml;base64,PHN2Zy...
raw = src.split(',', 1)[1]
svg_bytes = base64.b64decode(raw)
```

**Pitfall:** If a vision API returns 401 (unconfigured/missing auth), do not attempt vision-based captcha solving. Switch immediately to CapMonster or another configured service.

**Key verification before use:**
Always test the key first to confirm it belongs to CapMonster (not Anti-Captcha or another provider). `getBalance` alone is not sufficient — a key can return a balance but still fail on `createTask` (e.g., trial keys that have expired). Send a minimal dummy `ImageToTextTask` to verify real usability:
```python
# Step 1: balance check
bal = requests.post("https://api.capmonster.cloud/getBalance", json={"clientKey": key}).json()
# Expected: {"balance": N.N, "errorId": 0}

# Step 2: dummy task check (tiny base64 PNG)
dummy_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
test = requests.post("https://api.capmonster.cloud/createTask", json={
    "clientKey": key,
    "task": {"type": "ImageToTextTask", "body": dummy_b64, "minLength": 1, "maxLength": 3}
}).json()
# Must contain "taskId" (errorId==0). If it returns ERROR_KEY_DOES_NOT_EXIST, the key is dead.
```

**If the key fails:** Ask the user for another key or switch to a different provider. Do **not** invent free trials, demo accounts, or unverified workarounds without explicit user confirmation.

**SVG Captcha from data:image <img> element:**
Some services render the captcha as an inline `<img>` with `src="data:image/svg+xml;base64,..."`.
Extraction workflow:
```python
img = await page.query_selector("div.captcha-challenge img")
src = await img.get_attribute("src")
# src is data:image/svg+xml;base64,PHN2Zy4u.
raw = src.split(',', 1)[1]
svg_bytes = base64.b64decode(raw)
# Convert to PNG via cairosvg for CapMonster
import cairosvg
cairosvg.svg2png(bytestring=svg_bytes, write_to="/tmp/captcha.png",
                   output_width=400, output_height=150, background_color="white")
with open("/tmp/captcha.png", "rb") as f:
    b64 = base64.b64encode(f.read()).decode()
```
See `references/kimchi-registration.md` for a full example of this flow.

**Workflow:**
1. Capture the CAPTCHA image from the page (`screenshot` of element, or extract `src`/`data:image`).
2. Convert to base64 if needed.
3. `POST https://api.capmonster.cloud/createTask`
4. Poll `POST https://api.capmonster.cloud/getTaskResult` until `status == "ready"`.
5. Extract `solution.text` and submit it into the form.

**Quick Python integration:**
```python
import requests, time

def solve_captcha(image_path: str, client_key: str) -> str:
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    create = requests.post("https://api.capmonster.cloud/createTask", json={
        "clientKey": client_key,
        "task": {
            "type": "ImageToTextTask",
            "body": b64
        }
    }).json()
    task_id = create["taskId"]

    for _ in range(30):
        result = requests.post("https://api.capmonster.cloud/getTaskResult", json={
            "clientKey": client_key,
            "taskId": task_id
        }).json()
        if result.get("status") == "ready":
            return result["solution"]["text"]
        time.sleep(2)
    raise RuntimeError("Captcha solve timeout")
```

**Balance check:**
```python
requests.post("https://api.capmonster.cloud/getBalance", json={"clientKey": key}).json()
# → {"balance": 1.0, "errorId": 0}
```

**Other supported task types** (require sitekey/action params instead of image):
- `RecaptchaV2Task`, `RecaptchaV3Task`
- `HCaptchaTask`, `FunCaptchaTask`
- `GeeTestTask`

See `references/captcha-solving-guide.md` for full endpoint reference and rate-limit notes.

## Sequential Email Pattern

**Generator logic:**
- Start with `a.user@example.com`
- Increment letter: `next_letter` starts at 97 ('a')
- Track in JSON: `{used_addresses: {a.user: service_name}, next_letter: 98}`
- All emails route to same inbox (catch-all domain)

**Key fields in tracker:**
```json
{
  "used_addresses": {"a.bayov": "ecomagent"},
  "next_letter": 98,
  "service_map": {"example_org": "a.user@example.com"}
}
```

**Verification extraction:**
- Poll Gmail via Himalaya CLI or IMAP
- Search subjects: `verify`, `confirm`, `welcome`
- Extract links with regex: `https?://[^\\s\"<>]+`

## Modern JS Form Pitfalls

### React Hook Form (RHF)
**Problem:** `page.fill()` sets DOM value but RHF doesn't register it.
- RHF uses `register()` which wires `onChange` → React state
- Without firing React synthetic events, `formData` stays empty
- `form.checkValidity()` may return true (HTML5 valid) but RHF internal validation fails

**Detection:**
```javascript
// Page.evaluate to detect RHF
const isRHF = !!document.querySelector('form');
// Check for react props on button
const btn = document.querySelector('button[type="submit"]');
const hasReactProps = Object.keys(btn).some(k => k.startsWith('__react'));
```

**Workaround:**
```python
# Trigger React synthetic events after fill
page.fill('input[name="x"]', 'value')
page.evaluate('''
    const el = document.querySelector('input[name="x"]');
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
''')
```

### Next.js Server Actions
**Problem:** Submit doesn't produce traditional POST/XHR.
- Form action is React Server Action reference
- Submission goes through Next.js runtime, not direct fetch
- Requires cookie acceptance first (AWS cookie consent blocks form)

**Detection:**
- `form.getAttribute('action')` is null or same-page URL
- No traditional POST requests in network log
- `__reactProps` / `__reactFiber` keys on elements

**Workaround:**
1. Accept cookies first (click Accept button)
2. Use headed browser (headless=False) via xvfb-run
3. Human-like interaction: focus → type (not fill) → blur
4. Trigger via React fiber onClick/onSubmit if accessible

### Cookie Consent Traps
**AWS sites:** Form won't submit until cookie preferences set.
```python
# Always handle cookie consent BEFORE form interaction
accept_btn = page.locator('button').filter(has_text='Accept').first
if accept_btn.is_visible():
    accept_btn.click()
    time.sleep(2)
```

### Conditional Required Fields
**Problem:** A required field exists in RHF's internal registry but is hidden from
the DOM until a toggle/parent field is set. RHF validates the hidden field
silently, producing no visible error and leaving `isSubmitting: False`.

**Common trigger:** Checkbox or radio that controls visibility of child inputs.
Examples: `isDiscordMember=yes` reveals `discordUsername`; `hasReferral=yes`
reveals `referralCode`.

**Detection:**
```python
# Look for parent toggles BEFORE filling other fields
toggles = page.locator('input[type="radio"], input[type="checkbox"]').all()
for t in toggles:
    if t.is_visible() and not t.is_checked():
        # Set toggle to reveal hidden children, then inspect
        t.check()
        time.sleep(0.5)
        # Count newly-visible inputs
```

**Workaround:**
1. Always set parent toggles to their "yes"/truthy state first
2. Fill any newly-revealed required fields immediately
3. If form still stalls, extract RHF internal state (see below) to identify
   exactly which hidden field is failing validation

## Playwright Debugging Techniques

### Sync vs Async for OAuth / redirect-heavy SPAs
**CRITICAL:** Chromium + async Playwright frequently crashes with `EPIPE` or "Execution context was destroyed" when `page.goto()` triggers an OAuth redirect (e.g., `app.example.com/auth/signup` → `login.example.com/login?state=...`).

Preferred fixes (try in order):
1. **Switch to sync API (`sync_playwright`)** — it handles the redirect race far more stably.
2. **Use JS-based navigation** — bypass Playwright's internal `goto` promise:
   ```python
   page.evaluate('window.location.href="https://app.example.com/auth/signup"')
   time.sleep(6)
   ```
3. **Firefox fallback** — if Chromium keeps crashing, run `playwright install firefox` and use `p.firefox.launch(headless=True)`.

### Hermes browser_navigate timeout on SPA redirects
Hermes' native `browser_navigate` tool has a 60-second timeout and waits for `load` event. On Auth0-style SPAs (`app.kimchi.dev/auth/signup` → `login.kimchi.dev/login?state=...`), the `load` event often never fires because the SPA shell loads continuously. **Always use `execute_code` + Playwright** instead of `browser_navigate` for these sites.

### SPA Redirect & Client-Side Tab Switching
Modern SPAs (especially those using Auth0 or similar OIDC) may redirect to a separate login domain (`login.example.com`) with client-side state tabs (login vs. signup) instead of separate routes.

**Detection:**
- URL changes to an auth subdomain after navigation
- Page contains both login and signup inputs in the DOM simultaneously
- A link/button toggles visibility between views (e.g., "Don't have an account? Sign up")
- `page.goto('/signup')` may redirect to `/login` with OAuth params

**Workflow:**
1. Navigate to the auth URL with `wait_until='networkidle'` (not `domcontentloaded` — the redirect destroys the execution context before selectors resolve)
2. Wait for JS to render (sleep 2-3s)
3. Extract visible text — if it shows "Welcome back" / "Sign in" instead of "Create an account"
4. Find and click the tab-switching link (e.g., `await link.click()` where `innerText == 'Sign up'`)
5. Wait for the signup view to render
6. Proceed with form filling

**Pitfall:** The link may be an `<a>` tag with `href="#"` and JS handler — `page.click('text=Sign up')` may not work, but `link.evaluate('el => el.click()')` or direct element handle click does.

### Multi-Backend Auth Mismatch

Some services use **two different auth backends** simultaneously:
- **Supabase/Firebase** for programmatic API registration and login
- **Auth0/Clerk** for the web dashboard OAuth login

**Failure mode:** An account created via the Supabase API is **unknown to Auth0**. Logging into the web dashboard via Auth0 always fails, even with correct credentials and a solved captcha, because the user does not exist in the Auth0 tenant.

**Detection:**
- The JS bundle references both `supabase.co` and `auth0.com`/`login.example.com`.
- API login succeeds, but web login fails with generic errors ("Invalid captcha", "Wrong credentials").
- The web login page redirects to an Auth0 subdomain (`login.example.com`).

**Rule:** Before attempting web login, verify which auth backend governs the web UI. If the account was created via a different backend, either:
1. Use the same backend to log in (Supabase API token instead of Auth0 web form).
2. Check if the service exposes a dashboard API that accepts the Supabase token.
3. Register a fresh account through the web UI (Auth0) if the service requires web access.

**See `references/kimchi-auth0-login-failures.md` for a full post-mortem** of this exact failure with Kimchi/Cast AI.

### Auth0 Captcha + State Regeneration

Auth0 Universal Login pages regenerate both the **captcha image** and the **OAuth `state` parameter** on every page load. This means:
- Extracting a captcha, then reloading the page (or letting a redirect happen) invalidates the extracted captcha.
- The captcha solve + form submit must happen in a **single page context** without any navigation.

**Workflow:**
1. Navigate to the Auth0 page once.
2. Extract the captcha image immediately.
3. Solve it (CapMonster or manual).
4. Fill the form and submit **without any page reload**.

**Pitfall:** Using `browser_navigate` twice, or letting Playwright follow a redirect between extraction and submission, silently invalidates the captcha.

### Anti-Bot Registration Flooding & Domain Blacklisting

Modern SaaS platforms (especially Auth0, Clerk, custom anti-bot stacks) **permanently blacklist** IPs and email domains that show rapid automated registration patterns. This is not a soft rate limit — once a domain is blocked, it stays blocked.

**Real-world failure (Kimchi / Cast AI):**
1. Automated signup with Playwright + dynamic SVG captcha + CapMonster.
2. Multiple attempts within minutes from the same datacenter IP.
3. Entire target domain blacklisted. All future registrations with that domain rejected.

**Why it happens:**
- Same IP → repeated captcha failures / partial submissions → bot score spikes.
- Same email domain repeated attempts → domain reputation drops to zero.
- Auth0's `state` + captcha regeneration means each failed attempt looks like a fresh bot session.
- Headless browser fingerprints (datacenter IP, missing plugins, uniform timing) compound the score.

**Prevention rules:**
1. **Max 1-2 registration attempts per IP per hour on an unknown target.** If it doesn't work on first try → stop, diagnose, don't hammer.
2. **Always prefer API-first registration** (Supabase, Firebase direct API) — it bypasses the web anti-bot layer completely.
3. If web is the only path:
   - Use residential/rotating proxy (not datacenter IP).
   - Extract captcha + fill + submit in a **single page context**.
   - Add human-like pauses (2-5s between actions).
   - If first attempt fails → **STOP. Switch to a different email domain or proxy.** Do not retry the same combo.
4. **Keep multiple clean email domains in reserve.** A blocked domain is dead for that service forever.

**Recovery:**
- Domain blocks are typically permanent and irreversible through normal channels.
- Faster to switch to a new domain than to appeal.
- If access is critical and the service allows it, use a mainstream email provider (Gmail directly) instead of a catch-all domain.

**Frustration signal:** "стоп, хуйня какая то, либо кимчи сбросил и детектнул меня, теперь наш домен в блоке"

### env.js Backend Discovery

Before reverse-engineering a multi-megabyte minified bundle, check for a lightweight `env.js` file:
```bash
curl -s https://app.example.com/assets/env.js
curl -s https://app.example.com/env.js
```

These files often contain plaintext config:
```javascript
window.ENV = {
  API_BASE: "https://api.cast.ai",
  AUTH0_DOMAIN: "login.kimchi.dev",
  SUPABASE_URL: "https://dipswfuzhdgwirixmeem.supabase.co"
};
```

This reveals the service's architecture (multiple backends, API endpoints, auth providers) in seconds, without parsing minified code.

**Rule:** Always probe for `env.js` before diving into the main JS bundle.

### Hidden Duplicate Inputs
SPA auth pages often keep multiple form states (login, signup, forgot-password) in the DOM simultaneously, with only one set visible. Querying `page.query_selector('input[type=email]')` may return a hidden element and `fill()` will time out with "element is not visible".

**Workaround:** Iterate all matches and filter for visibility:
```python
email_in = None
for h in await page.query_selector_all("input[type=email]"):
    if await h.is_visible():
        email_in = h
        break
# Repeat for password, captcha, etc.
```

### React Fiber Inspection
```javascript
// Extract component tree from DOM element
function inspectReactFiber(element) {
    const fiberKey = Object.keys(element).find(k => k.startsWith('__reactFiber$'));
    if (!fiberKey) return null;
    
    const fiber = element[fiberKey];
    let current = fiber;
    const tree = [];
    while (current && tree.length < 20) {
        tree.push({
            name: current.elementType?.name || String(current.elementType),
            props: Object.keys(current.memoizedProps || {})
        });
        current = current.return;
    }
    return tree;
}
```

### React Hook Form Internal State Extraction
When a React Hook Form stalls silently (no visible errors, submit does nothing),
extract its internal state directly from the React fiber.

```javascript
// Fast: stringified values stored on the DOM element itself
const values = JSON.parse(
    document.querySelector('form')._valueTracker.getValue()
);

// Deep: walk the fiber to reach the RHF control object
const formEl = document.querySelector('form');
const fiberKey = Object.keys(formEl).find(k => k.startsWith('__reactFiber$'));
const fiber = formEl[fiberKey];
const control = fiber.return.memoizedProps.control;

console.log(control._fields);              // full field registry (hidden + visible)
console.log(control._formState.fieldErrors);   // validation error map
console.log(control._fieldValues);         // current field values
console.log(control._formState.isSubmitting);
```

Use this to identify which hidden/conditional field is failing validation even
when no error is rendered in the UI.
for a real-world example.

### Submit Button Analysis
```python
buttons = page.locator('button').all()
for btn in buttons:
    text = btn.inner_text().strip()
    fiber_keys = btn.evaluate('el => Object.keys(el).filter(k => k.includes("react"))')
    print(f"{text}: {fiber_keys}")
```

### Network Request Capture
```python
requests = []
page.on('request', lambda req: requests.append(req))
# ... interaction ...
post_requests = [r for r in requests if r.method == 'POST']
```

## xvfb-run for Headed Browser

When headless detection blocks forms:
```bash
# Install xvfb if missing
apt-get install -y xvfb

# Run headed Playwright
xvfb-run -a python3 script.py

# In script:
browser = p.chromium.launch(headless=False)
```

## Decision Tree

When approaching a new web form automation task:
0. **Verify the target domain/URL from the current conversation context.**
   - Do NOT rely on stale session memory for domains.
   - If the user provided or corrected a URL, use that.
0b. **Check for exposed backend API.** Download the main JS bundle and search for:
    - BaaS URLs (`.supabase.co`, `.firebaseio.com`, `auth0.com`)
    - JWT-style keys (`eyJ...`) longer than 150 chars
    - Direct signup/token endpoints (`/auth/v1/signup`, `/dbconnections/signup`)
    - If found, **attempt API-first registration** before touching the browser.
    - **End-to-end example:** `scripts/kimchi_register.py` performs Supabase signup, polls Gmail via `himalaya`, follows a `lovable.cloud` confirmation redirect, and extracts the access token — all in ~9 seconds. See `references/kimchi-registration.md` for the full walkthrough.
0c. **Probe for `env.js`** before reverse-engineering the main bundle:
    - `curl -s https://app.example.com/assets/env.js`
    - This reveals API endpoints, auth providers, and multi-backend architecture instantly.

When form submit doesn't work:
1. **Check URL change?** No → continue debugging
2. **Network POST?** No → React form or blocked
3. **Cookie consent active?** Yes → accept first
4. **SPA redirect to auth subdomain?** Yes → look for client-side tab toggle ("Sign up" link)
5. **Multi-backend auth mismatch?** Yes → the account may exist in Supabase but not Auth0. Try API login or register fresh via the web UI's backend.
6. **Auth0 captcha regenerated?** Yes → ensure extraction + submission happens in a single page context without reloads.
7. **Conditional required fields hidden?** Yes → set parent toggle to reveal them
8. **React fiber on element?** Yes → use fiber inspection
9. **Headed browser helps?** Yes → use xvfb-run
10. **Direct API POST possible?** Test with requests/curl
11. **Still fails?** → Extract RHF internal state for hidden validation errors
12. **Still fails?** → Service uses advanced bot detection (renege)

## Anti-Patterns

❌ Don't use `page.fill()` alone for React controlled forms
❌ Don't submit forms without cookie acceptance on AWS sites
❌ Don't assume `type="submit"` button uses native submit
❌ Don't retry identical approaches without inspecting fiber tree
❌ Don't leave conditional required fields hidden/unfilled — RHF validates them silently
❌ **Don't go on long silent investigation loops without checkpoint updates.** Explain each step before running it.
❌ **Don't rely on terminal stdout to copy long JWT tokens or API keys.** Terminal output truncates the middle — always write to a file and verify length.
❌ **Don't waste time on DIY OCR (tesseract, easyocr, paddleocr) when a captcha service with available balance exists.**
❌ **Don't invent service details, trial offers, or key capabilities without verification.** If a captcha key fails or a service is unavailable, ask the user before offering unconfirmed alternatives.
❌ **Don't rely on stale session memory for domains/URLs — always verify from the current conversation context first. The correct URL is often in a recent message.**
