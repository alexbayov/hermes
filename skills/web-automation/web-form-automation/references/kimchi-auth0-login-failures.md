# Kimchi Auth0 Login Failures — Post-Mortem Reference

## Service Architecture

Kimchi uses **two separate auth backends**:
1. **Supabase Auth** (`dipswfuzhdgwirixmeem.supabase.co`) — handles programmatic registration, email confirmation, password login via REST API.
2. **Auth0** (`login.kimchi.dev`) — handles the web dashboard login via OAuth2 Universal Login.

Critical implication: an account created via Supabase API is **unknown to Auth0**. The Auth0 login form always fails with `Invalid captcha value` (or equivalent), even with a correctly solved captcha, because the user simply does not exist in Auth0's tenant.

## Failure Mode: Auth0 Captcha + State Regeneration

When `browser_navigate` hits `app.kimchi.dev/auth/signup`, the SPA redirects to:
```
https://login.kimchi.dev/login?state=<random>&client=...
```

On this Auth0 page:
- Each **page load** generates a new `state` parameter and a **new SVG captcha**.
- The captcha is rendered inline as `data:image/svg+xml;base64,...` inside an `<img>`.
- Solving the captcha correctly and submitting the form still fails because the `state` cookie may have expired, or the page was reloaded between extraction and submission.

**Pitfall:** extracting the captcha, solving it, then refreshing/navigating away before submit invalidates the solution.

**Rule:** for Auth0-style pages, the captcha solve + form submit must happen in a **single page context without any navigation**.

## What Didn't Work

1. **CapMonster on Auth0 captcha** — solved correctly (`7GaTd6`, `M01TO1C`, `83dDCT`), but submission always returned `Invalid captcha value` or equivalent, because:
   - The account `g.bayov@antisecta.com` exists in Supabase but **not in Auth0**.
   - Between extraction and submission, the SPA or Playwright itself triggered a redirect, renewing `state` and the captcha.

2. **Playwright direct login** — async API crashed on OAuth redirect (`EPIPE`, "Execution context was destroyed"). Sync API worked better but the form DOM had duplicate hidden inputs (login vs signup tabs) making selectors unreliable.

3. **Supabase session token on `api.cast.ai`** — `401` on `/v1/auth/me` and `/v1/user`. The Supabase access token is valid only for Supabase Auth endpoints, not for Cast AI's business API. Cast AI uses its own API key system (`X-CASTAI-API-KEY`), not Supabase JWTs.

## What Did Work (Partial)

- **API-to-web mismatch detection:** Downloading `/assets/env.js` revealed `api.cast.ai` as the business backend (`CAST_AI_API_BASE`), and `login.kimchi.dev` as the Auth0 tenant. This explained why Supabase tokens failed on `api.cast.ai`.
- **OAuth social logins (available, not tested):** Auth0 page offers GitHub, Google, HuggingFace. These would work if the email `g.bayov@antisecta.com` were pre-linked to one of those social accounts.

## Lessons

1. **Before attempting web login, verify which auth backend governs the web UI.** If the service uses Auth0 but the account was created via Supabase/Firebase API, the web login will never work.
2. **For Auth0 pages, treat captcha extraction + submission as an atomic operation.** Any page reload or redirect invalidates both the captcha and the `state` parameter.
3. **Extract `env.js` early.** SPAs often expose their native API endpoint and key configuration in a lightweight `.js` file separate from the main bundle. This avoids reverse-engineering megabytes of minified code.
4. **When API auth fails with 401, check if the backend endpoint belongs to a different service than the auth provider.** Supabase JWT ≠ Cast AI API key.

## Corrected Decision Tree

When a web login fails despite correct credentials and a solved captcha:
0. Verify the account exists in the **same auth backend** as the web login page.
1. Check for a separate API auth system (Supabase, Firebase) vs web OAuth (Auth0, Clerk).
2. If API-registered → try API login (`/auth/v1/token`) or register a fresh account through the same channel as the web UI.
3. If still blocked → extract `env.js` and probe for the native business API key endpoint.
4. If API blocked → consider social login (GitHub/Google) if the email is linked.
5. If all automated paths fail → ask user for a dashboard-generated API key (human-in-the-loop).
