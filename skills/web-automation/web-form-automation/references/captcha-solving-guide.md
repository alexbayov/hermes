# Captcha Solving — Reference Guide

## CapMonster Cloud

**Base URL:** `https://api.capmonster.cloud`

**Endpoints:**
- `POST /createTask` — submit a captcha for solving
- `POST /getTaskResult` — poll for result
- `POST /getBalance` — check remaining balance

### ImageToTextTask (image/text CAPTCHA)

**Request:**
```json
POST https://api.capmonster.cloud/createTask
Content-Type: application/json

{
  "clientKey": "YOUR_KEY",
  "task": {
    "type": "ImageToTextTask",
    "body": "BASE64_IMAGE_STRING"
  }
}
```

**Response:**
```json
{
  "errorId": 0,
  "taskId": 123456789
}
```

**Polling:**
```json
POST https://api.capmonster.cloud/getTaskResult
{
  "clientKey": "YOUR_KEY",
  "taskId": 123456789
}
```

**Result (ready):**
```json
{
  "errorId": 0,
  "status": "ready",
  "solution": {
    "text": "A7B3C9"
  }
}
```

**Result (processing):**
```json
{
  "errorId": 0,
  "status": "processing"
}
```

### Supported Task Types

| Type | Use case |
|------|----------|
| `ImageToTextTask` | Static image CAPTCHA (letters, numbers, math) |
| `RecaptchaV2Task` | Google reCAPTCHA v2 (invisible too) |
| `RecaptchaV3Task` | Google reCAPTCHA v3 |
| `HCaptchaTask` | hCaptcha |
| `FunCaptchaTask` | Arkose FunCaptcha |
| `GeeTestTask` | GeeTest slider / click |

For token-based tasks (reCAPTCHA, hCaptcha) you need:
- `websiteURL`
- `websiteKey` (data-sitekey)
- Optional: `isInvisible`, `data-s`, `enterprisePayload`

### Quick Python Snippet

```python
import base64, requests, time

def solve_image_captcha(image_path: str, client_key: str, timeout: int = 60) -> str:
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    r = requests.post("https://api.capmonster.cloud/createTask", json={
        "clientKey": client_key,
        "task": {"type": "ImageToTextTask", "body": b64}
    }).json()

    if r.get("errorId") != 0:
        raise RuntimeError(f"CapMonster createTask failed: {r}")

    task_id = r["taskId"]
    for _ in range(timeout // 2):
        res = requests.post("https://api.capmonster.cloud/getTaskResult", json={
            "clientKey": client_key,
            "taskId": task_id
        }).json()
        if res.get("status") == "ready":
            return res["solution"]["text"]
        time.sleep(2)
    raise TimeoutError("CapMonster solve timed out")
```

### Balance Check

```python
requests.post("https://api.capmonster.cloud/getBalance",
              json={"clientKey": key}).json()
# → {"balance": 1.0, "errorId": 0, "errorCode": null, ...}
```

### Captcha Regeneration Pitfalls

**1. Page-load regeneration**
Many services (including Kimchi via Auth0) generate a **new captcha on every page load**. If you extract a captcha image, show it to the user for manual solving, and then the page is reloaded before submission, the submitted code will be rejected as "Invalid captcha value" because it corresponds to the previous image.

**Workflows that work:**
- **Fully automated:** Extract → solve via API → submit, all in one browser context without any page reload.
- **Manual but live session:** Keep the browser open (via sync Playwright), extract the captcha, show it to the user, wait for the answer, and submit — all without navigating away or refreshing.
- **What NOT to do:** Extract captcha → close browser → show to user → reopen browser → fill form. The new page load will have a different captcha.

**2. Auth0 state + captcha double regeneration**
Auth0 Universal Login regenerates **both the captcha AND the OAuth `state` parameter** on every redirect. Even if you avoid reloading the page, an OAuth redirect (e.g. `login.kimchi.dev/login?state=abc` → `login.kimchi.dev/login?state=xyz`) silently invalidates the captcha you extracted.

**Rule for Auth0 pages:** Extraction, solving, and submission must happen in a **strictly single page context** with zero navigation, zero redirects, and no `browser_navigate` calls after extraction.

**Related:** See `references/kimchi-registration.md` for API-first bypass (avoids captcha entirely), and `references/kimchi-auth0-login-failures.md` for a full post-mortem of why Auth0 captcha solving failed despite correct solutions.

### Rate Limits & Pitfalls

- **Polling interval:** minimum 1–2 seconds. Do not hammer `getTaskResult`.
- **Result lifetime:** solved tasks expire after a few minutes; fetch promptly.
- **Cost-aware:** ImageToTextTask is cheap (~$0.001–0.003). RecaptchaV2/V3 ~$0.002–0.005. Balance depletes fast at scale.
- **Image format:** PNG or JPEG recommended. SVG-based CAPTCHAs must be rasterized first (use `cairosvg` or browser screenshot).

### Alternatives

If CapMonster fails or balance runs out:
- **Anti-Captcha** (`https://api.anti-captcha.com`) — similar `createTask` / `getTaskResult` API.
- **2Captcha** (`https://2captcha.com/in.php` + `res.php`) — older API, slightly different polling model.

Both follow the same pattern: submit task, poll, extract `text` from solution.
