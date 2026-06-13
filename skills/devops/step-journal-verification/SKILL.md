---
name: step-journal-verification
description: "Use for multi-step, fragile, external, auth, deployment, scraping, or account tasks. Enforces a step ledger: intent, preconditions, exact action, evidence, postcondition, checkpoint, and stop-on-uncertainty."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [journal, verification, checkpoint, postconditions, execution]
    related_skills: [workflow-engine, operator-intent-discipline, critical-input-confirmation, external-auth-discipline]
---

# Step Journal Verification

## Purpose

Make execution inspectable and resumable. Every meaningful step must leave a short ledger entry that explains what was intended, what was actually done, what evidence was observed, and whether the postcondition passed.

This is the mechanical loop that prevents drift, panic retries, and false success claims.

## When to Use

Use for any task with one or more of:

- external side effects;
- account/auth/session work;
- scraping through an identity;
- deployments, config changes, file moves, destructive operations;
- more than three steps;
- operator frustration/correction;
- any situation where retrying blindly could make things worse.

## Ledger Fields

For each meaningful step, record:

```json
{
  "step_id": "short-stable-id",
  "intent": "what this step is supposed to accomplish",
  "preconditions": ["what must be true before acting"],
  "action": "exact tool/command/surface used",
  "critical_inputs": {"name": "normalized value, if any"},
  "evidence": "tool output / file / status that was observed",
  "postcondition": "how success is recognized",
  "result": "passed | failed | uncertain | blocked",
  "next_allowed_action": "what may happen next"
}
```

Store the ledger in the existing workflow/task state location when available (`workflow-engine` checkpoint), or in a task-local JSON/markdown file if no state helper exists.

## Step Loop

1. **Before action** — write intent, preconditions, postcondition, and critical inputs.
2. **Act once** — execute the smallest action that advances the current step.
3. **Observe** — read tool output, file state, status, screenshot, or API response.
4. **Verify** — compare observation to the postcondition.
5. **Record result** — passed / failed / uncertain / blocked.
6. **Decide**:
   - passed → continue to the next planned step;
   - failed with new cause → choose a different bounded approach;
   - uncertain → STOP and report;
   - blocked → STOP and report blocker/options.

## Postcondition Rules

Every step needs a concrete postcondition before acting.

Good:

- `gh pr view` returns PR #24 with expected head branch.
- Session file exists and `get_me()` returns the expected Telegram account.
- Config file contains the new key and validation command passes.
- Browser URL matches expected success page and page contains account email.

Bad:

- "Probably worked."
- "No error printed."
- "I think the code was sent."
- "The page looked okay."

## Retry Discipline

- Never repeat the same failed action with the same inputs.
- Retry only after classifying why the previous attempt failed.
- If a side effect may have happened, do not retry without confirmation.
- Max three distinct approaches for non-side-effecting steps; then stop.
- Operator correction resets the loop: stop tools, summarize ledger, ask/offer next options.

## Report Format

When reporting progress or blockers:

```text
Current step: <step_id>
Done: <passed steps>
Evidence: <key observed output>
Blocked/uncertain: <specific issue>
Next allowed actions: A) ... B) ...
```

## Common Pitfalls

1. Writing the ledger after the fact from memory instead of before acting.
2. Treating absence of an error as a postcondition.
3. Continuing after `uncertain` because another idea is available.
4. Losing the operator-requested method while solving a subproblem.
5. Retrying a side-effecting step to "make sure".

## Verification Checklist

- [ ] Current step has intent/preconditions/postcondition before action.
- [ ] Critical inputs are normalized and recorded.
- [ ] Actual action is recorded exactly enough to audit.
- [ ] Evidence is from tool output or inspected state.
- [ ] Result is passed/failed/uncertain/blocked.
- [ ] Uncertain or blocked states stop instead of drifting.
