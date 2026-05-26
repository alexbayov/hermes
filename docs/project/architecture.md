# Target architecture: Hermes control layer

This document describes the target shape of the Hermes upgrade. It is a planning artifact, not proof that the code already exists.

## Current problem

Hermes has useful tools and profile rules, but the most important behavior is not enforced deeply enough by code.

Main failure modes:

- prompt says hard-stop, runtime may continue;
- task context can be lost after rebuild/restart;
- config can be expanded/rewritten by UI saves;
- repeated failed actions can turn into carousels;
- browser workflows can reach risky actions without durable state/approval record.

## Target layers

```text
Alex request
  ↓
Task protocol
  ↓
Persistent task-state
  ↓
Tool execution
  ↓
Hard-stop detector
  ↓
Progress detector / anti-carousel
  ↓
Decision log
  ↓
Final report / resume point
```

## 1. Hard-stop detector

Runs immediately after every tool result.

Signals:

- `Command Approval Required`
- `Command denied by user`
- `BLOCKED`
- `Do NOT retry this command`
- approval timeout

Effect:

- stop current tool/model loop;
- update task-state to `blocked`;
- write decision-log event;
- tell Alex short status;
- wait for explicit confirmation.

## 2. Persistent task-state

Stores the current task's durable state.

Proposed path:

```text
/home/alex/hermes/profile/task-state/<session_id>.yaml
```

Use it for:

- current goal;
- last safe step;
- next intended step;
- blocked reason;
- approval requirement;
- final status.

## 3. Decision log

Append-only audit trail for important decisions.

Proposed path:

```text
/home/alex/hermes/profile/decision-log/<session_id>.jsonl
```

Use it for:

- config/profile changes;
- risky browser actions;
- provider/model default changes;
- hard-stop events;
- approval-sensitive decisions.

## 4. Config lock

`profile/config.yaml` may intentionally stay small.

When `_config_lock: true`, config writes must either:

- preserve minimal shape and update only allowed fields; or
- refuse the write with a clear status.

No silent full YAML expansion.

## 5. Anti-carousel

Hermes should detect no-progress loops:

- repeated same tool failure;
- repeated blocked command;
- repeated browser action failure;
- repeated plan without state change.

After threshold:

- halt;
- mark task blocked;
- summarize what was tried;
- ask Alex for next approval/choice.

## 6. Browser/WebBridge permission model

Browser actions should have explicit modes:

| Mode | Examples | Approval |
| --- | --- | --- |
| read-only | open page, inspect, summarize | not required |
| draft | fill fields without submit | may be allowed per task |
| risky | submit, OAuth, captcha, payment, delete, publish | required per action |

Browser/WebBridge remains experimental until hard-stop and anti-carousel are enforced.

## Non-goals

- Do not turn Hermes into a large enterprise workflow engine.
- Do not add complex roles before control layer works.
- Do not make browser automation the foundation of reliability.
- Do not store secrets in memory markdown.

## Desktop GUI integration

Hermes Desktop should sit above the control layer, not replace it.

Target safe shape:

```text
Hermes Desktop GUI
  ↓ remote/local API
Clean Hermes gateway/API
  ↓
Control layer
  ↓
Tools, memory, skills, schedules
```

Avoid this until proven safe:

```text
Hermes Desktop GUI
  ↓ direct writes
/home/alex/hermes/profile/config.yaml
/home/alex/hermes/profile/.env
/home/alex/hermes/profile/state.db
```

Reason: Desktop is designed around a `~/.hermes` home that contains the agent repo, venv, config, env, state DB and profiles. Alex's clean setup deliberately separates core, profile and memory.

Preferred first adoption path:

1. isolated Desktop lab home;
2. remote-mode connection to clean Hermes API;
3. only later consider adapter/full migration.
