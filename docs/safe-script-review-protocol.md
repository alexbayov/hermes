# Safe Script Review Protocol (HUP-16)

## Classification

| Class | Examples | Required Action |
|-------|----------|---------------|
| **read-only** | `status`, `diagnostics`, `grep-like checks`, `hermes doctor` | Can run |
| **local-write** | formatters, generators, config writes (non-destructive) | Explain first, run after confirmation |
| **network-write** | deploy, publish, upload, API mutation, `git push` | **Approval required** |
| **destructive** | `rm -rf`, `dd`, database migration, payment action, `clean_all` | **Hard stop + explicit approval** |

## Pre-Execution Checklist

Before running any script classified as network-write or destructive:

1. **What does it do?** — one sentence summary
2. **What does it touch?** — files, databases, APIs, wallets
3. **Can it be undone?** — rollback path
4. **Is there a safer alternative?** — read-only diagnostic first
5. **Has Alex approved?** — log decision if running autonomously

## Hard-Stop Triggers

- `rm -rf /` or any absolute-path deletion without whitelist
- `DROP TABLE`, `DELETE FROM` without `WHERE`
- Any command with `> /dev/sd` (disk writes)
- Payment or transaction commands
- `git push --force` to protected branches
- OAuth / captcha / submit without explicit approval

## Example Safe Flow

```
# NOT SAFE: hermes runs deploy.sh immediately
# SAFE:
1. Read deploy.sh with read_file
2. Classify as "network-write"
3. Present summary to Alex: "This runs `aws s3 sync` and invalidates CloudFront cache"
4. Wait for /approve or /deny
5. If approved, run and log decision
```
