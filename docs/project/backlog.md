# Hermes upgrade backlog

Each card should be implemented as a small PR. Do not combine unrelated cards unless Alex explicitly asks.

## HUP-00 — Repo hygiene baseline

Status: `PARTIAL`
Priority: `P0`
Owner role: `Repo Steward`

### Goal

Keep the GitHub repo safe as a clean Hermes workspace, not a dump of local runtime state.

### Current evidence

- `.gitignore` excludes `logs/`, `runtime/`, `backups/`, `.env`, `*.env`, `profile/.env`.
- Current `.gitignore` may exclude `core/`; that is no longer safe if `core/` contains custom Hermes changes.
- `AGENTS.md` says not to commit secrets, logs, sqlite/db files, browser profiles or caches.

### Keep enforcing

- Do not commit:
  - `.env`, keys, tokens;
  - `profile/state.db`;
  - `kanban.db`;
  - browser profiles/caches;
  - runtime logs and sessions;
  - old Sonya/B17/AI News config.

### Acceptance criteria

- `git status --short` contains only intentional source/docs/profile files.
- Secret scan has no real key values.
- Runtime/db files remain untracked.
- `core/` strategy is delegated to HUP-00A.

---

## HUP-00A — Core preservation strategy

Status: `READY`
Priority: `P0`
Owner role: `Repo Steward + Core Safety Engineer`

### Problem

Custom Hermes behavior lives in `/home/alex/hermes/core`. If `core/` is gitignored and not tracked anywhere, local work can disappear during risky git operations, failed rebases, directory syncs, or manual recovery.

Observed failure mode:

1. Older remote state had `core/` tracked.
2. New local state ignored `core/`.
3. A rebase/abort crossed those histories.
4. Git returned to a branch where `core/` was not tracked.
5. Local custom core files were no longer protected by git.

### What may have been lost

The following items were reportedly implemented in `core/` but not committed/tracked:

- hard-stop enforcement;
- anti-carousel/progress detection;
- task_state;
- decision_log;
- metrics;
- behavior tests;
- browser-safe / hermes-cli-safe toolsets.

These are not unrecoverable as product concepts because the design is documented in this project plan. The exact previous code may be recoverable only if it exists in:

- old remote commits;
- local reflog;
- local backups;
- shell/editor history;
- filesystem snapshots;
- copied exports.

### Options

| Option | Description | Pros | Cons |
| --- | --- | --- | --- |
| Track `core/` in this repo | Remove `core/` from `.gitignore` and commit sanitized core | Simple deploy from one repo | Large repo; must avoid vendoring runtime/venv/cache |
| Separate `hermes-core` fork | Keep profile repo separate; core changes live in a real fork/branch | Cleanest engineering model | Two repos to coordinate |
| Git submodule/subtree | Profile repo references exact core commit | Reproducible | More git complexity |
| Backup-only | Keep core ignored but auto-backup before git operations | Better than nothing | Not enough for collaboration/deploy |

### Recommended decision

Use a separate tracked core fork or branch for custom code, then reference its commit from this workspace repo.

Minimum immediate fix if no fork yet:

```bash
tar -czf /home/alex/hermes/backups/core-before-git-$(date +%Y%m%d-%H%M%S).tar.gz -C /home/alex/hermes core
git -C /home/alex/hermes status -sb
```

Before any `pull`, `rebase`, `checkout`, `reset`, `clean`, or export sync.

### Immediate recovery checklist

Run on Alex's machine:

```bash
git -C /home/alex/hermes reflog --date=iso | sed -n '1,80p'
git -C /home/alex/hermes log --all --oneline -- core | sed -n '1,80p'
find /home/alex/hermes -maxdepth 4 -type f \( -name '*task_state*' -o -name '*decision_log*' -o -name '*guardrail*' -o -name '*behavior*' \) | sort
find /home/alex/hermes/backups -maxdepth 4 -type f 2>/dev/null | sort | tail -80
```

If old commits contain `core/`, recover candidate files with:

```bash
git -C /home/alex/hermes show <commit>:core/run_agent.py > /tmp/run_agent.py.candidate
```

Do not overwrite the live core until candidates are diffed.

### Acceptance criteria

- Alex chooses one core preservation model.
- `core/` custom changes are tracked in git or backed up by an explicit pre-git protocol.
- `AGENTS.md` documents the chosen model.
- Future HUP core implementation PRs cannot exist only as untracked local files.

---

## HUP-01 — Enforce `_config_lock`

Status: `PARTIAL`
Priority: `P0`
Owner role: `Core Safety Engineer`
Depends on: access to `/home/alex/hermes/core`

### Problem

`profile/config.yaml` has:

```yaml
_config_lock: true
```

But this is only a sentinel. Hermes core must respect it when saving config.

### Known code location

Expected target in live core:

```text
/home/alex/hermes/core/tui_gateway/server.py
```

Known function from audit:

```python
def _save_cfg(cfg: dict):
    ...
    with open(p, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f)
```

### Required behavior

When existing config has `_config_lock: true`:

1. Do not rewrite the whole expanded config.
2. Preserve the minimal file shape.
3. Only write explicitly allowed keys, or refuse the write with a clear warning.
4. Never silently expand `profile/config.yaml` to hundreds of lines.

### Acceptance criteria

- Changing TUI settings does not expand locked config.
- Test covers locked config save.
- If write is blocked, user-visible status explains why.

---

## HUP-02 — Verify `HERMES_HOME` propagation

Status: `TODO`
Priority: `P0`
Owner role: `Runtime Engineer`
Depends on: access to `/home/alex/hermes/core`

### Problem

Clean Hermes must always use:

```text
HERMES_HOME=/home/alex/hermes/profile
vault_path=/home/alex/hermes/memory
```

Fallback to `~/.hermes` risks profile contamination.

### Known code locations

Likely targets:

```text
/home/alex/hermes/core/hermes_constants.py
/home/alex/hermes/core/tui_gateway/server.py
```

### Required behavior

- Every subprocess spawned by Hermes must inherit `HERMES_HOME`.
- If `HERMES_HOME` is missing in clean profile mode, fail loudly.
- Logs should show active profile path during startup.

### Acceptance criteria

- Test or diagnostic proves subprocesses see `/home/alex/hermes/profile`.
- No automatic fallback to `~/.hermes` in clean launcher path.
- `hermes-clean` startup prints or records active `HERMES_HOME`.

---

## HUP-03 — Code-enforced hard-stop

Status: `TODO`
Priority: `P1`
Owner role: `Core Safety Engineer`
Depends on: HUP-00

### Problem

`profile/SOUL.md` defines hard-stop behavior, but prompt rules are not enough.

Hard-stop strings:

- `Command Approval Required`
- `Command denied by user`
- `BLOCKED`
- `Do NOT retry this command`
- approval timeout

### Known code location

Expected target in live core:

```text
/home/alex/hermes/core/run_agent.py
```

Audit target area: after tool execution returns results to the main agent loop.

### Required behavior

After any tool call result:

1. Inspect structured status and text output.
2. If hard-stop signal appears, set session state to blocked.
3. Prevent further tool calls in the current loop.
4. Send short status to Alex.
5. Wait for explicit confirmation before continuing.

### Acceptance criteria

- Unit test: tool returns `BLOCKED` → no second tool call.
- Unit test: command approval denial → no retry through another tool.
- Behavior exam: Hermes reports blocked status and waits.
- Existing successful tool calls continue normally.

---

## HUP-04 — Persistent task-state

Status: `TODO`
Priority: `P1`
Owner role: `State Engineer`
Depends on: HUP-03

### Problem

Hermes can lose task context after rebuild/restart or long loops.

### Proposed path

```text
/home/alex/hermes/profile/task-state/<session_id>.yaml
```

### Required fields

```yaml
session_id:
task_title:
current_goal:
status: active|blocked|done|cancelled
last_safe_step:
next_step:
blocked_reason:
requires_approval:
updated_at:
```

### Required behavior

- Create state at task start.
- Update after each meaningful step.
- Mark blocked on hard-stop.
- Load recent unfinished task on restart and ask Alex whether to continue.

### Acceptance criteria

- Restart/rebuild does not lose current task status.
- Blocked tasks show `blocked_reason` and `requires_approval`.
- State file contains no secrets.

---

## HUP-05 — Decision log

Status: `TODO`
Priority: `P1`
Owner role: `State Engineer`
Depends on: HUP-04

### Problem

Hermes makes risky or architectural decisions without durable rationale.

### Proposed path

```text
/home/alex/hermes/profile/decision-log/<session_id>.jsonl
```

### JSONL event shape

```json
{"ts":"...", "decision":"...", "reason":"...", "alternatives":["..."], "risk":"low|medium|high", "approved_by":"alex|not_required"}
```

### Log when

- changing profile/config/launcher;
- enabling browser/WebBridge/payment workflows;
- bypassing a documented default;
- entering blocked state;
- selecting provider/model defaults.

### Acceptance criteria

- Decisions are append-only.
- No secrets are logged.
- Final task report can cite decision IDs/events.

---

## HUP-06 — Anti-carousel/progress detector

Status: `TODO`
Priority: `P1`
Owner role: `Control Loop Engineer`
Depends on: HUP-03, HUP-04

### Problem

Hermes can repeat similar tool calls or planning loops without measurable progress.

### Existing lead

Core audit found:

```text
core/agent/tool_guardrails.py
hard_stop_enabled: false
same_tool_failure_warn_after: 3
same_tool_failure_halt_after: 8
```

### Required behavior

- Detect repeated same-tool failures.
- Detect repeated equivalent model plans without state changes.
- Warn early.
- Halt and ask Alex after threshold.
- Update task-state with blocked reason.

### Acceptance criteria

- Test: repeated same failed command triggers halt.
- Test: repeated blocked action cannot be retried through another tool.
- Thresholds are configurable in profile.
- WebBridge test profile has guardrails enabled before browser automation resumes.

---

## HUP-07 — Behavior exams

Status: `TODO`
Priority: `P2`
Owner role: `QA Engineer`
Depends on: HUP-03, HUP-04, HUP-06

### Goal

Turn behavior expectations into executable checks.

### Source scenarios

Expected memory source on live system:

```text
/home/alex/hermes/memory/projects/hermes-behavior-exams.md
```

### Minimum exams

1. Hard-stop after approval denial.
2. No bypass through alternative tool.
3. Resume task after restart.
4. Do not expand locked config.
5. Detect repeated failed browser action.
6. Do not write secrets to memory/docs/logs.

### Acceptance criteria

- Exams can be run by future Devin.
- Pass/fail output is short and machine-readable.
- New control-layer PRs must run relevant exams.

---

## HUP-08 — Runtime metrics

Status: `TODO`
Priority: `P2`
Owner role: `Observability Engineer`
Depends on: HUP-03, HUP-04

### Goal

Make Hermes behavior inspectable without reading huge logs.

### Track

- tool call count by tool;
- hard-stop encounters;
- task-state transitions;
- repeated failures;
- config write attempts;
- browser/WebBridge approval gates.

### Acceptance criteria

- Metrics are written to local runtime logs, not committed.
- Summary command/report can show recent session health.
- No secret values in metrics.

---

## HUP-09 — WebBridge safe profile

Status: `BLOCKED`
Priority: `P3`
Owner role: `Browser Workflow Engineer`
Depends on: HUP-03, HUP-06

### Problem

WebBridge/browser workflows are useful but risky before control loop is reliable.

### Current state

There is an isolated test profile:

```text
profiles/webbridge-test/config.yaml
```

Known risks:

- expanded config shape;
- guardrails may be off or incomplete;
- browser actions need explicit approval gates;
- toolset definitions must be verified in live core.

### Required behavior

- Default read-only browser mode.
- Form drafting is allowed.
- Submit/OAuth/captcha/payment/delete/publish/security actions require explicit per-action approval.
- Hard-stop and anti-carousel must be active.

### Acceptance criteria

- WebBridge profile cannot submit forms without approval.
- Failed/blocked browser action halts.
- Toolsets resolve explicitly; no fallback surprise.
- Kimi/WebBridge launch/stop scripts are documented and safe.

---

## HUP-10 — Registration/payment workflows

Status: `BLOCKED`
Priority: `P3`
Owner role: `Browser Workflow Engineer`
Depends on: HUP-04, HUP-05, HUP-09

### Goal

Allow Hermes to help with registrations/billing safely.

### Required modes

| Mode | Allowed |
| --- | --- |
| read-only | inspect pages, summarize options |
| draft | fill fields but do not submit |
| approval-required | submit, OAuth, captcha, payment, delete, publish |

### Acceptance criteria

- Every risky action creates decision-log event.
- Task-state records approval requirement.
- Secrets/API keys are stored only in `.env`/secret store, never markdown.
- Final report says exactly what was submitted and what was only drafted.

---

## HUP-11 — Skill priority system

Status: `TODO`
Priority: `P3`
Owner role: `Skills Librarian`
Depends on: HUP-04

### Problem

Hermes needs deterministic skill selection.

### Desired priority

1. User-authored skills in `/home/alex/hermes/memory/skills/`.
2. Clean profile skills.
3. Bundled/upstream optional skills.
4. Legacy archive only when Alex explicitly asks.

### Acceptance criteria

- Skill discovery output shows source path and priority.
- User skills override bundled skills with same name/domain.
- Legacy Sonya/B17/temp-mail/news skills are not loaded by default.

---

## HUP-12 — Hermes Desktop feasibility

Status: `READY`
Priority: `P4`
Owner role: `Desktop Integration Engineer`
Depends on: HUP-00

### Context

Hermes Desktop is a native GUI companion:

```text
https://github.com/fathah/hermes-desktop
```

Upstream Desktop is promising for daily use, but it is not a drop-in replacement for Alex's clean Hermes layout.

### Findings from upstream Desktop v0.5.x docs/source

- Desktop local mode defaults to `~/.hermes`.
- Desktop installer runs the official Hermes install script and expects:

```text
<HERMES_HOME>/hermes-agent
<HERMES_HOME>/hermes-agent/venv
<HERMES_HOME>/hermes-agent/hermes
<HERMES_HOME>/config.yaml
<HERMES_HOME>/.env
<HERMES_HOME>/state.db
<HERMES_HOME>/profiles/
```

- Desktop has a custom home adoption path via `HERMES_HOME`/override, but it validates the Desktop-style install layout.
- Alex's clean Hermes layout is different:

```text
/home/alex/hermes/core
/home/alex/hermes/profile
/home/alex/hermes/memory
/home/alex/hermes/bin
```

- Desktop writes additional files under `HERMES_HOME`, including `desktop.json`, `.env`, staging data, profile state and session DB.
- Desktop can also use remote mode with an API URL/API key.

### Recommended experiment

Do not point Desktop at `/home/alex/hermes/profile` first.

Use an isolated desktop home:

```text
/home/alex/hermes-desktop-lab
```

or use Desktop remote mode against a separately started clean Hermes API/gateway.

### Test plan

1. Install Desktop package for the OS.
2. Launch with isolated environment:

```bash
HERMES_HOME=/home/alex/hermes-desktop-lab hermes-desktop
```

3. Let Desktop install/adopt Hermes only inside the lab path.
4. Configure a non-sensitive test provider or local OpenAI-compatible endpoint.
5. Verify chat works.
6. Inspect files Desktop writes:

```bash
find /home/alex/hermes-desktop-lab -maxdepth 3 -type f | sort
```

7. Compare generated config shape with Alex's clean minimal config.
8. Confirm Desktop can run without touching:

```text
/home/alex/hermes/profile
/home/alex/hermes/memory
/home/alex/hermes/core
```

### Acceptance criteria

- Desktop runs in isolated lab home.
- No changes to clean profile/memory/core.
- File write inventory is documented.
- Config write behavior is known.
- Provider/API key storage behavior is known.
- Decision made: remote-mode integration, adapter integration, or no adoption yet.

---

## HUP-13 — Hermes Desktop safe adoption

Status: `BLOCKED`
Priority: `P4`
Owner role: `Desktop Integration Engineer`
Depends on: HUP-01, HUP-03, HUP-06, HUP-12

### Problem

Desktop gives a friendly GUI, but it can also edit config, env, tools, skills, schedules, gateway and memory. That is valuable only after the control layer is safe.

### Safe adoption options

| Option | Description | Risk |
| --- | --- | --- |
| Remote mode | Desktop connects to clean Hermes API/gateway URL | Lowest |
| Adapter mode | Add wrappers/symlinks so Desktop can see clean layout | Medium |
| Full migration | Move clean Hermes into Desktop's expected `~/.hermes` layout | Highest |

### Recommended direction

Start with remote mode or isolated lab mode. Avoid full migration until Desktop behavior is proven.

### Required safeguards before main-profile adoption

- `_config_lock` enforcement is implemented.
- Hard-stop enforcement is implemented.
- Anti-carousel is implemented.
- Desktop write behavior is tested.
- Desktop provider key handling is tested.
- Backup of clean profile/memory exists.

### Acceptance criteria

- Alex can open Desktop and chat with clean Hermes without profile contamination.
- Desktop cannot silently expand locked `profile/config.yaml`.
- Desktop-created files are either isolated or intentionally mapped.
- Rollback path is documented.
- Browser/WebBridge risky actions still require approval.
