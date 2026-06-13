---
name: telegram-telethon-login
description: Use when accessing Telegram through Telethon or Pyrogram, logging in by phone, reusing Telegram sessions, listing dialogs, or preparing Telegram scraping from an account. Covers api_id/api_hash, sessions, code sends, and blockers.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [telegram, telethon, pyrogram, mtproto, auth]
    related_skills: [external-auth-discipline, critical-input-confirmation, operator-intent-discipline, workflow-engine]
---

# Telegram Telethon Login

## Purpose

Reliable Telegram MTProto login and session reuse without improvising across auth surfaces.

## Non-Negotiable Facts

- Telethon/Pyrogram require `api_id` and `api_hash`. Phone alone is not enough.
- Existing `.session` files may avoid a new login code, but the script still needs compatible API credentials.
- `my.telegram.org/apps` may reject VPN/Tor/datacenter IPs. Do not assume it can create an app from the agent host.
- Web Telegram / QR login is a different method. Use only after explicit operator confirmation.
- Public API credential pairs are unreliable and lower-trust. Label them as such.

## Required Skills First

Apply these before any Telegram auth action:

1. `operator-intent-discipline`
2. `critical-input-confirmation`
3. `external-auth-discipline`
4. `workflow-engine` for checkpoint/journal if the task has more than one step

## Standard Flow

### 1. Lock method and goal

```text
Goal: access Telegram account for <purpose>.
Requested method: Telethon/Pyrogram MTProto.
Not switching to: web.telegram.org, QR, my.telegram.org, Tor/VPN, public scraping unless confirmed.
```

### 2. Inspect local state

Search persistent locations for existing Telegram config/session before asking for codes:

```bash
find "$HOME" . -type f \
  \( -name '*.session' -o -name '*.session-journal' -o -name '.env' -o -iname '*telegram*' -o -iname '*telethon*' -o -iname '*pyrogram*' \) \
  -not -path '*/.git/*' 2>/dev/null

grep -RIn --exclude-dir=.git --exclude='*.session' --exclude='*.session-journal' \
  -E 'TELEGRAM_API_ID|TELEGRAM_API_HASH|api_id|api_hash|TelegramClient|Pyrogram|Client\(' . "$HOME/.hermes" 2>/dev/null
```

Do not print secrets. Report presence/path, not raw hashes.

### 3. Check prerequisites

Need one of:

- confirmed `api_id` + `api_hash`; or
- existing project config that supplies them; or
- explicit permission to try a lower-trust public pair; or
- explicit permission to create/retrieve app credentials through another surface.

If missing, STOP:

```text
Blocked on Telethon prerequisite: missing api_id/api_hash and no existing session config found.
I am not switching to web/QR/my.telegram.org without confirmation.
Options: ...
```

### 4. Normalize phone before send-code

If a phone login is needed:

```text
Raw phone: <operator input>
Normalized phone: +<country><number>
Action: send Telegram login code to exactly <normalized phone>
```

Reject masked values such as `+792****7796`.

### 5. Send code once

Only after prerequisites and normalized phone are confirmed. Log the exact command arguments in task state, but do not expose secrets.

A successful send-code claim requires evidence such as a returned `phone_code_hash` or library status object for the normalized phone. Delivery may be Telegram app notification rather than SMS.

### 6. Sign in and save session

- Ask for code only after send-code evidence.
- If 2FA password is required, prefer a secure prompt/tool. If unavailable, explain the sensitivity and ask the operator how to proceed.
- Save session to a named path with restricted permissions.
- Verify by calling `get_me()` and listing a small number of dialogs.

## Forbidden Behaviors

- Claiming a code was sent without tool evidence.
- Re-sending code repeatedly because the first one did not arrive.
- Using a masked/redacted phone as input.
- Opening web.telegram.org or QR flow after a Telethon request without confirmation.
- Trying my.telegram.org through VPN/Tor after the operator says that route fails.
- Asking the operator to provide API credentials if an existing project/session can be found locally first.

## Blocker Report Template

```text
Blocked: <specific Telethon prerequisite or Telegram response>.
Evidence: <command/tool output summary>.
Done: <searched paths/config, installed libs, normalized phone, etc.>.
Not doing without confirmation: <web/QR/my.telegram.org/Tor/public pair/retry>.
Options:
A) use existing api_id/api_hash from <path or operator-provided>;
B) search wider for old sessions/config;
C) operator confirms alternate method <method>;
D) stop.
```

## Verification Checklist

- [ ] Requested method is Telethon/Pyrogram and still locked.
- [ ] Existing sessions/config searched before external code send.
- [ ] `api_id/api_hash` prerequisite satisfied or blocker reported.
- [ ] Phone normalized and not redacted.
- [ ] At most one send-code attempt per confirmed target.
- [ ] Claims grounded in returned evidence.
- [ ] Session verified with `get_me()` / dialog listing before scraping.
