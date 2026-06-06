## HUP Linkage

Closes HUP-___

## Scope

<!-- One sentence: what does this PR do? -->

## Changes

- [ ] Feature / fix / refactor / docs
- [ ] Files changed: ___

## Security & Hygiene

- [ ] No secrets, tokens, or credentials in this PR
- [ ] No runtime files (logs, .env, state.db) committed
- [ ] `.gitignore` updated if new runtime artifacts introduced

## Core Preservation

- [ ] No modifications to upstream `~/.hermes/hermes-agent/` core
- [ ] If unavoidable core patch: backup and rollback path documented below

## Control Layer

- [ ] Hard-stop behavior not weakened
- [ ] Anti-carousel detector not disabled
- [ ] No approval bypass mechanisms

## Verification

- [ ] New tests added (or manual exam notes attached)
- [ ] Existing tests pass: `scripts/run_tests.sh` or targeted pytest
- [ ] Behavior exam reference: ___

## Documentation

- [ ] `AGENTS.md` updated if workflow changed
- [ ] Backlog/status updated

## Rollback

If this PR causes issues, revert via:
```bash
git revert <merge-commit>
# or
git reset --hard origin/main~1 && git push --force-with-lease
```

## Risk Level

- [ ] Low — docs, tests, config-only
- [ ] Medium — new feature with tests
- [ ] High — core behavior change or upstream patch
