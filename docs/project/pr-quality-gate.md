# PR Quality Gate (HUP-19)

## Role: Hermes PR Inspector

Every PR must pass this gate before merge. The inspector is a mandatory reviewer.

## Checklist

### Scope & Linkage
- [ ] Linked HUP card in PR description (e.g., `Closes HUP-07`)
- [ ] Narrow scope — one HUP per PR, no unrelated changes
- [ ] No WIP commits or temporary files in diff

### Security & Hygiene
- [ ] No secrets, tokens, API keys in diff
- [ ] No runtime files (logs, .env, state.db, backups)
- [ ] No binary blobs without justification
- [ ] `.gitignore` covers new runtime artifacts if introduced

### Core Preservation
- [ ] No modifications to `~/.hermes/hermes-agent/` (upstream core)
- [ ] If core patch is unavoidable, it must be in `core/` with backup and rollback plan
- [ ] Custom plugins/skills go to `~/.hermes/plugins/` or workspace `skills/`

### Control Layer Integrity
- [ ] Hard-stop behavior not weakened (test `test_hup01_config_lock.py` still passes)
- [ ] Anti-carousel detector not disabled (plugin active)
- [ ] No approval bypass mechanisms introduced

### Verification
- [ ] New tests added for new behavior
- [ ] Existing tests pass (`scripts/run_tests.sh` or targeted pytest)
- [ ] Manual behavior exam notes attached if no automated test yet

### Documentation
- [ ] `AGENTS.md` updated if workflow changed
- [ ] Backlog/status updated if HUP status changed
- [ ] Rollback path documented (how to revert if merged)

### Merge Requirements
- [ ] At least one approving review from PR Inspector
- [ ] All CI checks green (once CI configured)
- [ ] Stale approvals dismissed on new commits
- [ ] Squash or rebase strategy chosen and documented

## Rejection Blockers

A PR is **BLOCKED** if any of the following are true:

1. Secrets or credentials visible in diff.
2. Direct upstream core patch without HUP-00A approval.
3. Hard-stop or guardrail behavior weakened.
4. No tests and no manual exam notes for behavioral changes.
5. Scope creep — multiple HUPs or unrelated features.
6. Missing rollback path for risky changes.

## Branch Protection (Recommended)

Configure `main` on GitHub:
- Require PR before merge
- Require at least 1 approving review
- Block direct pushes
- Dismiss stale approvals on new commits
- Require status checks once CI exists
