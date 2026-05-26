# Hermes PR quality gate

Use this document for every PR before merge.

Primary reviewer role: **Hermes PR Inspector**.

The inspector is intentionally strict. Their job is to keep the repo clean, reproducible and safe, not to be nice to a messy diff.

## Inspector mission

Reject or request changes on any PR that:

- mixes unrelated work;
- changes `core/` without a preservation strategy;
- commits secrets, runtime state, generated caches or logs;
- bypasses approval/hard-stop rules;
- expands locked config without an explicit HUP card;
- edits memory/project files without a clear reason;
- lacks verification notes;
- cannot be rolled back safely.

## Required review order

1. Scope.
2. Safety.
3. Git/core preservation.
4. Secrets/runtime hygiene.
5. Tests/verification.
6. Diff quality.
7. Documentation/status updates.
8. Merge decision.

## 1. Scope check

Every PR must answer:

- Which HUP card does this close or advance?
- Is the PR small enough to review?
- Are unrelated changes excluded?

Reject if:

- feature work is mixed with formatting/refactor/noise;
- Desktop/WebBridge work starts before blocking P1/P0 dependencies;
- core restoration is mixed with new behavior work.

## 2. Safety check

Reject if the PR weakens:

- approval hard-stop;
- browser risky-action approval;
- secret redaction;
- clean `HERMES_HOME`;
- legacy context isolation;
- config lock protections.

## 3. Core preservation check

If PR touches or depends on `/home/alex/hermes/core`, require one of:

- `core/` changes are tracked in git;
- changes live in a dedicated core fork/branch;
- submodule/subtree commit is updated;
- temporary backup is documented and attached to task notes.

Reject if custom core changes exist only as ignored local files.

Before approving core work, ask:

```bash
git status --short
git ls-files core | sed -n '1,20p'
git check-ignore -v core 2>/dev/null || true
```

## 4. Secrets/runtime hygiene

Reject if PR includes:

- `.env`, keys, tokens;
- `profile/state.db`;
- `kanban.db`;
- logs, runtime sessions, pid/sock files;
- browser profiles/caches;
- generated dumps with sensitive data.

Run at least:

```bash
git diff --name-only origin/main...HEAD
git diff --check origin/main...HEAD
git grep -n -I -E '(sk-[A-Za-z0-9_-]{30,}|ghp_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|FIREWORKS_API_KEY=|OPENAI_API_KEY=|TELEGRAM_BOT_TOKEN=)' -- . ':!*.md'
```

Variable names are okay. Real values are not.

## 5. Tests/verification

Every PR must say what was checked.

Minimum expectations:

- docs-only: markdown reviewed, links/paths checked, no secret patterns;
- config/profile: inspect diff and run relevant Hermes startup/doctor if available;
- core behavior: unit/behavior tests or manual behavior exam;
- browser/Desktop/WebBridge: isolated profile or remote-mode test, not main clean profile first.

Reject if PR claims success without verification notes.

## 6. Diff quality

Reject if:

- broad `git add .` captured unrelated files;
- large generated files are committed;
- comments explain the diff instead of durable behavior;
- patch is hard-coded to pass one example;
- tests were weakened without explicit approval.

## 7. Documentation/status updates

If a HUP card changes status, PR must update:

- `docs/project/status.md`;
- relevant card in `docs/project/backlog.md`;
- `docs/project/decision-log.md` for architectural decisions.

## 8. Merge decision

Approve only when:

- scope is clear;
- no secrets/runtime junk;
- core preservation is handled;
- verification is adequate;
- rollback is obvious;
- project status is updated.

Otherwise request changes with short, concrete blockers.

## Standard inspector comment

```text
Review result: REQUEST CHANGES

Blockers:
1. ...
2. ...

Required fix:
- ...

Do not merge until these are resolved.
```

or:

```text
Review result: APPROVE

Checked:
- scope
- secrets/runtime hygiene
- core preservation
- verification notes
- project status updates
```
