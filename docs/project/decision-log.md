# Hermes upgrade decision log

Append project-level decisions here. Session/runtime decision logs should later live under `profile/decision-log/` and remain uncommitted unless explicitly sanitized.

## 2026-05-14 — Use GitHub repo as long-lived upgrade project

Decision: Track Hermes upgrade work in `docs/project/` inside the repo.

Reason: Alex spends too many tokens reloading context for each Devin session. A committed project plan gives future sessions a stable source of truth.

Implication: Future Devin sessions should update `status.md` and `backlog.md` after each implementation PR.

## 2026-05-14 — Control layer before WebBridge expansion

Decision: Browser/WebBridge/registration/payment work is `P3` and blocked until `P1` control layer is implemented.

Reason: Without hard-stop, task-state and anti-carousel, browser workflows can retry blocked/risky actions or lose context.

Implication: If Alex asks to improve WebBridge, first verify HUP-03 and HUP-06 status.

## 2026-05-14 — Keep live core separate from clean profile repo

Decision: Treat `/home/alex/hermes/core` as upstream/external unless a card explicitly targets core changes.

Reason: The current GitHub repo is a clean workspace/profile/control project, not necessarily a full vendored copy of Hermes core.

Implication: Core PRs need special care and should cite exact core file paths.

## 2026-05-14 — Treat Hermes Desktop as an integration track, not a simple upgrade

Decision: Add Hermes Desktop adoption as `P4`, behind control-layer safety and an isolated feasibility test.

Reason: Upstream Desktop is useful but local mode defaults to `~/.hermes`, expects a `hermes-agent/venv` layout under `HERMES_HOME`, and writes Desktop/config/env/state files under that home. Alex's clean Hermes layout separates `core`, `profile` and `memory`.

Implication: First Desktop work should use an isolated lab home or remote-mode connection. Do not point Desktop directly at `/home/alex/hermes/profile` until config-lock, hard-stop and anti-carousel safeguards are implemented and Desktop write behavior is documented.

## 2026-05-14 — Core must not remain only as ignored local state

Decision: Add HUP-00A as an urgent P0 track before more custom core work.

Reason: Alex reported that custom `core/` changes disappeared after a rebase/abort across histories where `core/` changed from tracked to gitignored. Even if some code can be recovered from old commits/backups, future control-layer work must not live only in ignored local files.

Implication: Before restoring hard-stop, anti-carousel, task_state, decision_log, toolsets or behavior exams, choose a core preservation strategy: track `core/`, split a dedicated core fork/branch, use submodule/subtree, or at minimum enforce backup-before-git operations.

## 2026-05-14 — Add Hermes PR Inspector role

Decision: Add a strict PR review role and quality gate.

Reason: Alex wants future agents to submit clean, safe, reviewable PRs instead of dumping messy or unsafe changes into the repo.

Implication: Every future PR should link a HUP card, use the PR template, pass `docs/project/pr-quality-gate.md`, and be reviewed before merge. Direct pushes to `main` should be blocked through GitHub branch protection.
