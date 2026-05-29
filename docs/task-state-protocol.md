# Task State Protocol

## Location

```
/home/alex/hermes/profile/task-state/<session_id>.yaml
```

## Fields

| Field | Type | Description |
|---|---|---|
| session_id | string | Unique session identifier |
| task_title | string | Human-readable task name |
| current_goal | string | What we are trying to achieve |
| status | enum | active, blocked, done, cancelled |
| last_safe_step | string | Last successfully completed step |
| next_step | string | What should be done next |
| blocked_reason | string | Why task is blocked (if status=blocked) |
| requires_approval | boolean | Whether Alex needs to approve next action |
| updated_at | ISO timestamp | Last modification time |

## Usage

- Created at task start
- Updated after each meaningful step
- Marked blocked on hard-stop
- Loaded on restart to resume

## Example

```yaml
session_id: "sess_20260529_001"
task_title: "Configure Hermes Fireworks API"
current_goal: "Make Hermes work with Fireworks Kimi K2.6"
status: done
last_safe_step: "Updated config.yaml provider to openai-api"
next_step: "Test gateway startup"
blocked_reason: null
requires_approval: false
updated_at: "2026-05-29T17:00:00Z"
```
