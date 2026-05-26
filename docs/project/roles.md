# Hermes upgrade roles

Use these roles to split work across future Devin sessions. One PR should normally have one primary role.

## Repo Steward

Mission: keep the GitHub repo safe and useful.

Owns:

- `.gitignore`;
- `AGENTS.md` / `CLAUDE.md`;
- project docs under `docs/project/`;
- secret/runtime-state hygiene.

Do not:

- modify live core behavior;
- commit runtime databases/logs/env files.

## Core Safety Engineer

Mission: convert safety rules from prompt text into runtime enforcement.

Owns:

- hard-stop enforcement;
- config lock enforcement;
- approval-denial handling;
- safety tests.

Likely files in live core:

- `/home/alex/hermes/core/run_agent.py`;
- `/home/alex/hermes/core/tui_gateway/server.py`;
- `/home/alex/hermes/core/agent/tool_guardrails.py`.

## Runtime Engineer

Mission: make clean Hermes always start with the intended profile and memory.

Owns:

- `HERMES_HOME` propagation;
- launcher behavior;
- subprocess environment;
- startup diagnostics.

Likely files:

- `/home/alex/hermes/bin/hermes-clean`;
- `/home/alex/hermes/core/hermes_constants.py`;
- `/home/alex/hermes/core/tui_gateway/server.py`.

## State Engineer

Mission: give Hermes durable memory of current work.

Owns:

- `task-state/<session_id>.yaml`;
- `decision-log/<session_id>.jsonl`;
- restart/resume behavior;
- blocked/done/cancelled transitions.

Do not store secrets in state/log files.

## Control Loop Engineer

Mission: stop infinite carousels and repeated useless work.

Owns:

- loop detection;
- same-tool failure thresholds;
- progress checks;
- integration with hard-stop and task-state.

Likely file:

- `/home/alex/hermes/core/agent/tool_guardrails.py`.

## QA Engineer

Mission: turn expected behavior into executable exams.

Owns:

- behavior exams;
- regression tests for control layer;
- pass/fail reporting.

Minimum exams:

- approval denial halts;
- no bypass through another tool;
- locked config is not expanded;
- restart resumes task-state;
- repeated failed browser action halts;
- secrets are not written to markdown/logs.

## Browser Workflow Engineer

Mission: safely return WebBridge, browser automation, registrations and payments.

Owns:

- `profiles/webbridge-test/`;
- Kimi/WebBridge launcher docs;
- browser action permission modes;
- registration/payment workflow templates.

Blocked until:

- HUP-03 hard-stop is done;
- HUP-06 anti-carousel is done;
- HUP-04 task-state is done for registration/payment workflows.

## Skills Librarian

Mission: make skill loading predictable.

Owns:

- skill priority rules;
- source path display;
- user skill override behavior;
- legacy skill quarantine.
