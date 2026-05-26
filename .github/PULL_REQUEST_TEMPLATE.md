## HUP card

Linked card: HUP-__

## Summary

What changed:

-

What did not change:

-

## Risk level

Choose one:

- [ ] Docs-only
- [ ] Profile/config
- [ ] Core behavior
- [ ] Browser/WebBridge/Desktop
- [ ] Runtime/deploy/migration

## Core preservation

Choose one:

- [ ] Does not touch or depend on `/home/alex/hermes/core`
- [ ] `core/` changes are tracked in this PR/repo
- [ ] `core/` changes are tracked in a separate core fork/branch
- [ ] Temporary backup was created before local git operations

Notes:

-

## Safety checklist

- [ ] No `.env`, real keys/tokens, runtime logs, sqlite/db files, pid/sock files, browser profiles or caches
- [ ] No broad unrelated changes
- [ ] No weakened hard-stop/approval behavior
- [ ] No locked config expansion unless explicitly intended
- [ ] Project status/backlog updated if HUP status changed

## Verification

Commands/checks run:

```text

```

Result:

-

## Rollback

How to revert safely:

-

## Human review focus

- [ ] Scope is correct
- [ ] Core preservation is acceptable
- [ ] Verification is enough for this risk level
