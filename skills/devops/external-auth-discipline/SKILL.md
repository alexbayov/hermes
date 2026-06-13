---
name: external-auth-discipline
description: Use for login, registration, OAuth, 2FA, email/SMS codes, session creation, account scraping setup, or provider authentication. Enforces side-effect limits, evidence-based claims, and operator-mode reporting.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [auth, login, 2fa, oauth, side-effects, operator-mode]
    related_skills: [workflow-engine, operator-intent-discipline, critical-input-confirmation]
---

# External Auth Discipline

## Purpose

Make auth work boring and reliable. Login/registration flows can send codes, trigger security alerts, rate-limit accounts, or lock users out. Treat them as side-effecting operations.

## Required Companion Skills

Before acting, apply:

1. `operator-intent-discipline` — do not change method/surface silently.
2. `critical-input-confirmation` — normalize targets before side effects.
3. `workflow-engine` — journal attempts and stop after bounded retries.

## Auth Side Effects

These are dangerous unless explicitly planned:

- sending login code / SMS / email;
- OAuth consent or app creation;
- QR login;
- new device login;
- password reset;
- repeated failed login attempts;
- proxy/Tor/VPN login that may trip fraud controls.

## Attempt Limits

- One send-code attempt per normalized target unless the operator confirms another.
- No repeated submit/login attempts with the same credentials and same error.
- Max two technical retries only when no external side effect occurred.
- After any uncertain side effect: STOP.

## Evidence Before Claims

Do not say:

- "code sent";
- "I am inside";
- "login worked";
- "app created";
- "session saved";

unless tool output proves it.

Use this format:

```text
Claim: <what happened>
Evidence: <specific return value / file / status>
Uncertainty: <delivery may be delayed, code may arrive in app not SMS, etc.>
```

If output is ambiguous:

```text
I cannot confirm the code was sent. The command returned <X>. I am stopping before retrying.
```

## Operator Mode Style

For auth, credentials, account scraping, money, or destructive tasks:

- no roleplay;
- no pet names;
- no dramatic apology loops;
- no "I'll just try";
- concise status, evidence, blocker, next options.

## Stop Conditions

STOP and ask/report when:

- requested method lacks credentials or preconditions;
- next step would use a different auth surface;
- target is redacted or uncertain;
- rate limit / fraud / suspicious login appears;
- a code was sent or may have been sent;
- operator expresses alarm or says stop.

## Common Pitfalls

1. Treating a login code as harmless. It is an external account event.
2. Using browser QR as a fallback when the operator requested API login.
3. Trying Tor/VPN after the operator says that path is blocked.
4. Making reassurance claims not grounded in tool output.

## Verification Checklist

- [ ] Requested auth method is locked.
- [ ] Critical target normalized.
- [ ] Attempt count checked.
- [ ] Evidence collected before status claim.
- [ ] No method switch without explicit confirmation.
- [ ] Operator mode style used.
