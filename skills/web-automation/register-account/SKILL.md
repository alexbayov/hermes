---
name: register-account
description: Safely create an account through browser automation using Hermes automation recipes, email verification, and explicit blocker handling.
version: 0.1.0
author: Hermes
metadata:
  hermes:
    category: web-automation
    safety: requires-human-for-security-gates
---

# Register Account

Use this skill when the user asks Hermes to create an account or complete a
normal signup/onboarding flow on a site where the user is authorized to do so.

## Preconditions

- The target site and purpose are explicit.
- Required identity fields are available through task input or an approved vault:
  email, name, password/profile fields.
- An email inbox connector is available, or Hermes can stop and ask the user for
  email verification.
- The automation runner has a recipe for the site, or the user approved creating
  a new generic recipe.

## Procedure

1. Create/update task state with `status: active`, `current_goal`,
   `last_safe_step`, and `next_step`.
2. Select the smallest relevant recipe/skill set. Do not load unrelated web
   automation notes or whole browser logs.
3. Run the site recipe through `hermes-automation run` and consume the JSON
   contract (`hermes.automation.result.v1`).
4. If `status: done`, save evidence and report the successful end state.
5. If `blocked_reason` is present, mark task state `status: blocked` and ask for
   the exact approved next input.
6. If email verification is required and an inbox connector is configured, use
   the email verification capability; otherwise ask the user to verify manually.
7. Resume from checkpoint after the user or inbox completes the blocked step.

## Success signals

- Automation result has `status: done` and `success: true`.
- Final URL or visible page state matches the recipe's success condition.
- Checkpoint contains all completed steps with secrets redacted.

## Blockers / hard stops

Stop autonomous execution and set `blocked_reason` for:

- `captcha_visible`
- `two_factor_required`
- `phone_verification_required`
- `passkey_required`
- `rate_limited`
- explicit anti-bot or security gate
- terms or policy text that forbids the requested automation

Do not bypass CAPTCHA, 2FA, phone verification, passkeys, or anti-bot gates.
Ask the user to complete the gate in the browser or provide an approved,
site-compliant next step.

## Context discipline

Give the model only:

- current task state
- this skill and at most one site recipe
- latest compact browser snapshot
- last automation JSON result
- allowed actions

Never include raw full DOM dumps, unrelated skills, old traceback history, or
unredacted secrets in the planning context.
