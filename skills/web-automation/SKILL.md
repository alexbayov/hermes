---
name: web-automation
description: Authoring skill for sites/*.yaml scenarios — write valid declarative web automation flows for the Hermes engine without touching Python code.
version: "1.0"
author: alex+eni
platforms: [linux, macos]
metadata:
  hermes:
    tags: [web-automation, yaml-authoring, browser, sites, declarative]
    category: productivity
---

# Web Automation — Authoring `sites/*.yaml`

## 1. When to Use

Activate this skill when:

- A new website target needs a declarative browser scenario (signup, form fill, onboarding, data extraction, QA flows).
- An existing YAML scenario needs a new step or action.
- You're debugging a failed run and need to interpret artifacts (`failure.png`, `trace.zip`).

**Do NOT use** when: you need a new action type (that's a code change in `actions.py`), or the engine itself needs modification.

**Trigger**: mention "site config", "YAML scenario", "automation flow", or reference a file in `sites/*.yaml`.

## 2. Top-Level YAML Schema

Every `sites/<name>.yaml` must declare these top-level keys:

```yaml
name: string              # REQUIRED — appears in ExecutionResult.site
start_url: string         # informational, not enforced by engine
browser:                  # optional, defaults below
  headless: bool          # default true
  viewport:               # default 1280x900
    width: int
    height: int
  trace: bool             # default false — enables Playwright trace on failure
capabilities:
  redaction:
    enabled: bool         # default false
fields_schema:            # declares input fields and their sensitivity
  <field_name>:
    secret: bool          # true → masked in checkpoints/screenshots
retry:
  max_attempts: int       # default 3
  strategy: "conservative"
steps:                    # REQUIRED — ordered list of Step objects
  - id: string            # unique, stable — used as checkpoint key
    actions: [...]        # ordered action list
    success: {...}        # postcondition — at least one field
```

> **Config hash warning.** Any YAML change invalidates the checkpoint (`ConfigMismatchError`). Never edit a config mid-run. Use `--reset` to start fresh.

## 3. Step Anatomy

```yaml
- id: unique_step_id       # stable key for checkpoints — never change mid-run
  actions:                 # executed in order, each with retry
    - type: action_type
      id: action_id        # optional, appears in logs/artifacts
      payload: {...}       # type-specific (see §4)
  success:                 # at least ONE condition required
    url_contains: string
    visible_text: string
    visible_role: string   # + visible_name
    selector: string
```

- A step is committed to checkpoint **only after `success` passes**.
- Changing a step's `id` invalidates resume for that step.
- If `success` is missing, the step is considered "done" after actions complete — use only for fire-and-forget steps.

## 4. Action Catalog (Registered Handlers)

Only these types are available. New types require code changes in `actions.py`.

### `goto` — Navigate

| payload key | type | description |
|---|---|---|
| `url` | string | Target URL |

```yaml
- type: goto
  payload:
    url: "https://example.com/signup"
```

### `fill` — Fill a text field

| payload key | type | description |
|---|---|---|
| `label` | string | Match by `<label>` text (preferred) |
| `role` + `name` | string, string | ARIA role + accessible name |
| `selector` | string | CSS selector (last resort) |
| `value` | string | Literal value to type |
| `value_from` | string | Key in `fields` — retrieves the actual value |

```yaml
# Explicit field substitution (preferred for dynamic data)
- type: fill
  payload:
    label: "Email"
    value_from: email

# Literal value
- type: fill
  payload:
    role: textbox
    name: "Search"
    value: "test query"
```

> `value_from` reads from the `fields` dict passed at runtime. `value` is a literal. Use `value_from` for any dynamic or secret data.

### `click` — Click an element

| payload key | type | description |
|---|---|---|
| `role` + `name` | string, string | ARIA role + accessible name (preferred) |
| `text` (+ `exact`) | string, bool | Click by visible text |
| `selector` | string | CSS selector (last resort) |

```yaml
- type: click
  payload:
    role: button
    name: "Continue"
```

### `check` — Check a checkbox

| payload key | type | description |
|---|---|---|
| `label` | string | Checkbox label text |

```yaml
- type: check
  payload:
    label: "I agree to the Terms"
```

Idempotent: uses Playwright's `.check()` which is a no-op if already checked.

### `wait_for_url` — Wait for URL to contain substring

| payload key | type | description |
|---|---|---|
| `url_contains` | string | Substring to match in URL |
| `timeout_ms` | int | Optional, default 15000 |

```yaml
- type: wait_for_url
  payload:
    url_contains: "/dashboard"
    timeout_ms: 10000
```

### `wait_for_text` — Wait for text to appear

| payload key | type | description |
|---|---|---|
| `text` | string | Text to wait for |
| `timeout_ms` | int | Optional, default 15000 |

```yaml
- type: wait_for_text
  payload:
    text: "Welcome back"
```

### `dismiss_cookies` — Best-effort cookie banner dismissal

No payload. Never fails the step — returns `success=True` even if no banner found.

```yaml
- type: dismiss_cookies
```

### `screenshot` — Capture a screenshot

| payload key | type | description |
|---|---|---|
| `name` | string | Optional filename prefix |

```yaml
- type: screenshot
  payload:
    name: "after_signup"
```

Password inputs are automatically masked (`input[type=password]`).

## 5. Locator Discipline (Priority Order)

Always select locators in this priority:

1. **`role` + accessible `name`** — most stable, survives redesign.
2. **`label`** — explicit `<label>` association.
3. **`data-testid`** — if the target site has test IDs.
4. **`text`** — visible text, but fragile to copy changes.
5. **CSS `selector`** — **LAST RESORT**. Fragile to class/ID changes.

**Never use**: coordinate clicks (`x, y`), `time.sleep` for synchronization, XPath expressions, `element.checked = true` (DOM violence).

Why: Playwright's actionability guarantees (visible, enabled, stable, not covered) only work with proper locators. Coordinates bypass all safety checks and produce flaky runs.

## 6. Secrets and Redaction

- **Never hardcode secrets** in YAML. Use `value_from` to pull from the `fields` dict.
- Mark all sensitive fields with `secret: true` in `fields_schema`.
- The engine automatically:
  - Replaces secret values with `***REDACTED***` in checkpoints (`state/*.json`).
  - Masks `input[type=password]` in screenshots.
  - Excludes secrets from structured logs.

```yaml
fields_schema:
  email:
    secret: false
  password:
    secret: true
  api_token:
    secret: true
```

```yaml
# In action — use value_from, never the literal
- type: fill
  payload:
    label: "Password"
    value_from: password
```

## 7. Success Conditions and Retry

### Success (postconditions)

Every step should declare at least one success condition. Without it, the step is marked "done" immediately after actions — no verification of outcomes.

```yaml
success:
  url_contains: "/home"          # most reliable
  visible_text: "Dashboard"      # good for landing pages
  visible_role: heading          # + visible_name: "Welcome"
  selector: "[data-testid=dashboard]"  # most stable when available
```

### Retry Classification

The engine (`retry.py`) classifies errors automatically:

| Retriable (auto-retry) | Non-retriable (fail fast) |
|---|---|
| Timeout waiting for element | Wrong credentials |
| Overlay/blocked click | Missing required field |
| Stale locator after re-render | Permission/403 |
| Animation not finished | Selector permanently not found |
| Transient network error | Config mismatch |
| | Postcondition clearly failed |

- Retriable errors: up to `retry.max_attempts` (default 3), with increasing delay.
- Non-retriable: step fails immediately — no wasted attempts.
- Structure your YAML so that transient UI glitches are surviveable, but business-logic errors surface fast.

## 8. Authoring Workflow

Step-by-step recipe to turn "automate site X" into a valid `sites/<name>.yaml`:

### 8.1 Reconnaissance

1. Open the target page in a browser (or Playwright).
2. Use accessibility snapshot / DevTools to identify:
   - ARIA roles and accessible names of key inputs and buttons.
   - `<label>` associations.
   - `data-testid` attributes (gold standard if available).
3. Map out the navigation flow: what URL → what action → what redirect → what URL.

### 8.2 Chunk into Steps

1. Each significant navigation transition (form submit, redirect, page load) becomes a `step`.
2. Use `success.url_contains` as the primary postcondition.
3. Give each step a stable, descriptive `id` (e.g., `open_signup`, `submit_email`, `verify_email`, `complete_profile`).

### 8.3 Write Actions per Step

1. Start with `dismiss_cookies` if the site has a banner.
2. Fill inputs in DOM order using the locator priority from §5.
3. Click submit/continue buttons by `role` and `name`.
4. Add `wait_for_url` or `wait_for_text` if redirects are slow or conditionally triggered.

### 8.4 Declare fields_schema

1. List every dynamic input value that comes from outside the YAML.
2. Mark passwords, tokens, and API keys as `secret: true`.
3. Use `value_from` in actions to reference these fields.

### 8.5 Add Success Conditions

1. Every step gets a `success` block.
2. Prefer `url_contains` — it's the cheapest, most reliable signal.
3. Add `visible_text` as a secondary check when URL alone isn't enough.

### 8.6 Test and Fix

1. Run with `--reset` on staging/sandbox.
2. On failure, check `artifacts/<task_id>/failure.png` (masked screenshot) and `trace.zip`.
3. Fix flaky locators by moving up the priority chain.
4. Re-run until green 10/10.

## 9. Annotated Example

See `sites/golden_onboarding.yaml` for the full canonical reference. Key decisions:

- **`dismiss_cookies` first** in `open_start` and `onboarding` — clears overlays before interacting with real UI.
- **`value_from` everywhere** — no literals for dynamic data; all values come from the `fields` dict.
- **`success.url_contains` on every step** — the cheapest verification: did we go to the right page?
- **`label` locators for onboarding fields** — more stable than `role` when accessible names are ambiguous.
- **`secret: true` on password** — ensures it never leaks to state files or screenshot artifacts.
- **`retry.max_attempts: 3`** — enough for transient UI hiccups, not so much that a broken flow spins forever.

## 10. Validation Checklist (Pre-Commit Gate)

Before submitting a new `sites/<name>.yaml`, verify:

- [ ] Every step has a **unique, stable `id`**.
- [ ] Every step has a **`success`** condition (at least one field).
- [ ] **No hardcoded secrets** in YAML; secret fields marked `secret: true`.
- [ ] **Locator priority** respected (§5): role/name → label → data-testid → text → selector.
- [ ] **No coordinates, no `sleep`, no XPath.**
- [ ] All `value_from` keys reference fields declared in `fields_schema`.
- [ ] Only **registered action types** used (see §4).
- [ ] Run on sandbox/staging **green** (10/10).
- [ ] Failure artifacts (`failure.png`, `trace.zip`) are generated and interpretable on a forced failure.
- [ ] `--reset` fresh run works; resume after kill continues from last checkpoint.

## Scope and Discipline

This skill enables automation of **authorized, controlled scenarios only** — your own sites, staging environments, QA sandboxes, internal panels, and test forms.

**Prohibited:**
- Farming or mass-account creation on third-party services.
- Bypassing anti-abuse, CAPTCHA, rate limits, domain bans, or ToS.
- Using disposable email for registration on external services (QA-mailhog/mailpit on your own infrastructure is fine).
- Stealth, `undetected-chromedriver`, anti-detection techniques.
- Any automation designed to fraudulently obtain trial credits, API keys, or resources from third parties.

This discipline section mirrors the SOUL.md execution rules. The engine is domain-agnostic by design — it doesn't know about "registration" or "Fireworks." Use cases must be reviewed by LO before deployment.
