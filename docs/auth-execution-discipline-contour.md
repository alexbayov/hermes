# Auth Execution Discipline Contour

## Why

Recent account-auth automation exposed a reliability gap: the agent can understand a technical blocker but still lose operator trust by switching methods, retrying side-effecting actions, or making claims before tool evidence is checked.

This contour adds rails around fragile external-auth work: registrations, phone/email login, OAuth, 2FA, Telegram/Telethon sessions, provider accounts, and scraping accounts tied to an operator identity.

## Target behavior

The agent should follow this loop:

1. Capture the operator's goal and requested method.
2. Normalize critical inputs before use.
3. Check preconditions and existing state.
4. Execute one bounded action.
5. Journal the step: intent, preconditions, exact action, evidence, postcondition, result.
6. Verify tool output/state before claiming success.
7. Stop on blocker, uncertainty, method switch, or operator stop.
8. Report evidence and options without theatrical retries.

The agent should not silently substitute a different surface. If the operator asks for Telethon, moving to browser QR, web.telegram.org, my.telegram.org, Tor, or public scraping requires explicit confirmation.

## Files added

- `skills/devops/operator-intent-discipline/SKILL.md` — locks the requested method and defines stop gates.
- `skills/devops/critical-input-confirmation/SKILL.md` — normalizes and confirms phones, emails, handles, repo names, deletion paths, payment targets, and login targets.
- `skills/devops/external-auth-discipline/SKILL.md` — safe handling for login codes, OAuth, 2FA, rate limits, and side-effecting auth attempts.
- `skills/devops/step-journal-verification/SKILL.md` — per-step ledger and postcondition checks for fragile execution.
- `skills/devops/telegram-telethon-login/SKILL.md` — Telegram/Telethon-specific runbook.

These skills are deliberately small and composable. They sit on top of `workflow-engine/SKILL.md`, which already provides checkpointing, journaling, retry classification, idempotency, and artifacts.

## Profile / instruction changes to make after merge

Add the following rules to the agent's durable profile instructions (the primary always-loaded behavior file, not a public prompt dump):

```text
Execution discipline for external-auth and account tasks:
- The operator's requested method is binding. Do not switch tools, websites, login surfaces, or strategy without explicit confirmation.
- Before any external side effect, restate the exact target and action; normalize critical inputs first.
- Redacted logs are not source of truth for actual sent input. Track actual input in local variables/state.
- After any failed or uncertain auth attempt, stop and summarize. Do not retry blindly.
- If the operator says stop / what are you doing / not that, immediately stop tool use and report current state.
- Claims must be grounded in tool output. If evidence is incomplete, say so.
- In auth, credentials, scraping accounts, money, or destructive tasks: use concise operator mode; no roleplay, pet names, or apology loops.
```

If the runtime supports a skills policy or trigger list, ensure these skills are considered for prompts containing: `login`, `sign in`, `register`, `OAuth`, `2FA`, `code`, `phone`, `Telegram`, `Telethon`, `Pyrogram`, `account`, `SMS`, `email verification`, `scrape private`, `session`.

## Rollout plan

1. Merge this PR.
2. Add the profile/instruction block above to the deployed agent profile.
3. Restart the agent/session so skill metadata is reloaded.
4. Run a replay test using a Telegram/Telethon scenario:
   - operator requests Telethon specifically;
   - phone number is provided without plus;
   - `api_id/api_hash` are missing;
   - operator says not to use browser/VPN path;
   - operator says stop.
5. Expected replay behavior:
   - normalizes `792...` to `+792...`;
   - searches existing sessions/configs;
   - states Telethon blocker if credentials/session are missing;
   - does not open web.telegram.org or my.telegram.org without confirmation;
   - does not send repeated codes;
   - stops immediately on operator stop.

## Follow-up infra

Recommended next work is not Telegram-specific tooling. First harden the generic execution loop:

- Add an executable behavior exam that simulates a fragile auth task and asserts: method lock, critical input normalization, step ledger entries, postcondition checks, and stop-on-uncertainty.
- Wire a lightweight task ledger helper into the runtime if existing `workflow-engine` checkpoints are not reliably available to the agent.
- Only add domain wrappers (Telegram, provider-specific login, etc.) after replay exams show the generic loop is being followed.
