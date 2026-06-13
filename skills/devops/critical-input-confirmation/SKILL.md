---
name: critical-input-confirmation
description: Use before external side effects involving phone numbers, emails, usernames, repo names, URLs, file paths, payment targets, deletion targets, or login identities. Normalize, display, and bind exact values.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [input-validation, external-actions, safety, auth]
    related_skills: [operator-intent-discipline, external-auth-discipline, workflow-engine]
---

# Critical Input Confirmation

## Purpose

Prevent wrong-target actions. Critical inputs must be normalized, displayed, and stored before use.

## Critical Inputs

Treat these as critical:

- phone numbers and login identifiers;
- emails and recovery addresses;
- usernames, handles, channel names, invite links;
- repository/PR/issue names;
- file paths for deletion, overwrite, archive, or publish;
- account/app names;
- payment, crypto, market, or billing targets;
- any destination for a code, notification, invite, or irreversible action.

## Core Rule

Before an external side effect, bind the exact value in local state and show it to the operator or in the action plan.

```text
Raw input: <as provided>
Normalized input: <canonical form>
External action: <what will be sent/done to that exact target>
```

If the value is ambiguous, malformed, redacted, or reconstructed from logs: STOP.

## Redaction Rule

Redacted logs are display artifacts, not truth.

- Never use values containing `*`, `…`, or masked fragments as action input.
- Never infer that a redacted display value was the actual submitted value.
- Store actual normalized values in task state before executing commands.
- If actual submitted value is unknown after a side effect: STOP and report uncertainty.

## Normalization Examples

Phone:

```text
Raw: 79293257796
Normalized E.164: +79293257796
Reject: +792****7796
```

GitHub PR:

```text
Raw: oplot PR plan
Resolved: alexbayov/oplot#181
```

File path:

```text
Raw: delete old m12 docs
Resolved paths: docs/redesign/m12/* -> docs/redesign/archive/m12/
```

## Side-Effect Gate

Before these actions, require normalized input and target check:

- send login code / SMS / email;
- submit signup/login form;
- create/delete app/account/repo/file;
- post comment/review/message;
- archive/move/delete files;
- place order/payment/market action.

## Common Pitfalls

1. Pulling a phone/email from a prior assistant summary instead of the original operator input.
2. Copying masked values from tool logs.
3. Saying "sent" before verifying the target in the tool output or command arguments.
4. Normalizing silently and then using a different value in the script.

## Verification Checklist

- [ ] Raw input captured.
- [ ] Canonical normalized value computed.
- [ ] No redacted/masked value used.
- [ ] External action target equals normalized value.
- [ ] If uncertain, stopped before retrying.
