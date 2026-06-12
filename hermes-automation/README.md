# Hermes Automation Harness

Declarative Playwright automation runner for Hermes.

## CLI contract

Run a YAML recipe and print a stable JSON result for the main Hermes agent:

```bash
hermes-automation run \
  --recipe sites/golden_onboarding.yaml \
  --task-id signup-example-001 \
  --fields '{"email":"qa@example.test","first_name":"Hermes","last_name":"QA","password":"TestPass123!"}' \
  --state-dir state \
  --artifacts-dir artifacts \
  --reset
```

The command exits with:

- `0` when all recipe steps complete (`status: done`)
- `2` when execution stops before completion (`status: blocked`)

JSON schema marker:

```json
{
  "schema_version": "hermes.automation.result.v1",
  "status": "done|blocked",
  "success": true,
  "task_id": "...",
  "site": "...",
  "current_step": "...",
  "completed_steps": [],
  "final_url": "...",
  "config_hash": "...",
  "error": null,
  "artifacts": {"dir": "...", "trace": "..."},
  "checkpoint": {},
  "actions": []
}
```

This JSON boundary is intentionally separate from Python dataclass internals so
`hermes-agent` can call the runner as a tool/subprocess and update task state
without importing Playwright-dependent modules.

## Blocker detection

The runner detects common human/security gates and reports them instead of
continuing blindly:

- `captcha_visible`
- `two_factor_required`
- `phone_verification_required`
- `passkey_required`
- `email_verification_required`
- `rate_limited`

Detection only marks the run as blocked; it does not solve or bypass these
checks. The JSON result includes `blocked_reason` and `blocker` so the main
Hermes agent can update task state and ask for human/email handling.
