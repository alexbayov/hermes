---
name: workflow-engine
description: Execution discipline engine for Hermes: checkpoints, retry classification, idempotency, journals, artifacts. Universal workflow harness — not tied to any specific domain.
version: "1.0"
author: alex+eni
platforms: [linux, macos]
metadata:
  hermes:
    tags: [workflow, checkpoint, retry, state-machine, execution]
    category: productivity
---

# Workflow Engine — Hermes Execution Discipline

## Purpose

Give Hermes a structured execution harness for ANY complex multi-step task. Not domain-specific — applies equally to browser automation, code projects, deployments, registrations.

## Core Rules (beyond SOUL.md discipline)

### 1. Checkpoint After Every Step

After completing a meaningful sub-task, save state:

```bash
STATE_DIR="$HOME/.hermes/state"
mkdir -p "$STATE_DIR"

cat > "$STATE_DIR/${TASK_ID}.json" << 'EOF'
{
  "task_id": "TODO",
  "task": "TODO",
  "step": "TODO",
  "done": [],
  "data": {},
  "attempts": {},
  "updated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
```

**Never redo a completed step.** Load checkpoint first, resume from last `done` step.

### 2. Journal Every Attempt

Before each action, record in the checkpoint:

```json
{
  "attempts": {
    "step_id": [
      {"approach": "what was tried", "result": "what happened", "ts": "..."}
    ]
  }
}
```

**NEVER repeat a failed approach.** New attempt MUST differ in method.

### 3. Retry Classification

| Retriable | Non-Retriable |
|-----------|---------------|
| Timeout waiting for element | Wrong credentials |
| Animation/overlay blocking click | Missing required field |
| Stale locator after rerender | Permission denied |
| Network hiccup | Config hash mismatch |
| Mail not yet arrived (within timeout) | Postcondition clearly wrong |
| Cookie banner intercepting | Destructive action without safety check |

**Max 3 different approaches per sub-task.** Exhausted → STOP, report: done / blocker / options.

### 4. Idempotency Safety

| Action type | Safe to repeat? | How to check |
|-------------|-----------------|--------------|
| fill/text input | Yes (overwrites) | — |
| checkbox | Check state first | Only click if needed |
| click navigate | Check URL before | Only if not already there |
| click submit | DANGEROUS | Check postcondition first |
| create/delete | DANGEROUS | Check if entity exists |
| email/payment | DANGEROUS | Server-side idempotency key |

**Before any dangerous action:** verify it hasn't already been done. If uncertain — STOP, ask LO.

### 5. Artifact Collection on Failure

When a step fails, save:

- URL at time of failure
- Action being attempted
- Error message + type
- Screenshot (if browser)
- Console/network summary (if browser)
- DOM snapshot (if browser)

```bash
ARTIFACT_DIR="artifacts/${TASK_ID}"
mkdir -p "$ARTIFACT_DIR/screenshots" "$ARTIFACT_DIR/html"

echo "ERROR: $ERROR_MSG" > "$ARTIFACT_DIR/error.txt"
echo "STEP: $CURRENT_STEP" >> "$ARTIFACT_DIR/error.txt"
echo "URL: $CURRENT_URL" >> "$ARTIFACT_DIR/error.txt"
```

### 6. Config Hash (for YAML-driven tasks)

```bash
CONFIG_HASH=$(sha256sum "sites/${SITE}.yaml" | cut -d' ' -f1)
```

Checkpoint stores `config_hash`. On resume, compare. Mismatch → STOP, ask LO for `--reset` or `--migrate`.

## Bash Toolbox

### Checkpoint helpers

```bash
# Save checkpoint
ck_save() {
    local task_id="$1" step="$2" data="$3"
    local dir="$HOME/.hermes/state"
    mkdir -p "$dir"
    local tmp="${dir}/${task_id}.tmp"
    python3 -c "
import json, sys, os
d = {}
if os.path.exists('${dir}/${task_id}.json'):
    with open('${dir}/${task_id}.json') as f:
        d = json.load(f)
d['step'] = '${step}'
d['done'] = d.get('done', []) + ['${step}']
d['data'] = {**d.get('data', {}), **json.loads('''${data}''')}
d['updated_at'] = '$(date -u +%Y-%m-%dT%H:%M:%SZ)'
with open('${tmp}', 'w') as f:
    json.dump(d, f, indent=2)
    f.flush()
    os.fsync(f.fileno())
os.replace('${tmp}', '${dir}/${task_id}.json')
"
}

# Load checkpoint
ck_load() {
    local task_id="$1"
    cat "$HOME/.hermes/state/${task_id}.json" 2>/dev/null || echo '{"done":[],"data":{}}'
}

# Check if step is done
ck_done() {
    local task_id="$1" step_id="$2"
    ck_load "$task_id" | python3 -c "import sys,json; d=json.load(sys.stdin); print('true' if '${step_id}' in d.get('done',[]) else 'false')"
}

# Reset checkpoint
ck_reset() {
    local task_id="$1"
    rm -f "$HOME/.hermes/state/${task_id}.json"
}
```

### Journal helpers

```bash
# Log attempt
jl_log() {
    local task_id="$1" step_id="$2" approach="$3" result="$4"
    python3 -c "
import json, os, sys
path = '${HOME}/.hermes/state/${task_id}.json'
d = {}
if os.path.exists(path):
    with open(path) as f: d = json.load(f)
d.setdefault('attempts', {}).setdefault('${step_id}', []).append({
    'approach': '''${approach}''',
    'result': '''${result}''',
    'ts': '$(date -u +%Y-%m-%dT%H:%M:%SZ)'
})
with open(path, 'w') as f:
    json.dump(d, f, indent=2)
"
}

# Check if approach was already tried
jl_tried() {
    local task_id="$1" step_id="$2" approach="$3"
    python3 -c "
import json, os
path = '${HOME}/.hermes/state/${task_id}.json'
if not os.path.exists(path): print('false'); exit()
with open(path) as f: d = json.load(f)
for a in d.get('attempts', {}).get('${step_id}', []):
    if a['approach'] == '''${approach}''':
        print('true'); exit()
print('false')
"
}
```

## Usage Example

Hermes, when starting a multi-step task:

1. `TASK_ID=$(date +%s)-$(echo "$TASK" | md5sum | cut -c1-8)`
2. Load checkpoint: `ck_load $TASK_ID`
3. For each step:
   - Skip if `ck_done $TASK_ID $STEP`
   - Log attempt BEFORE acting: `jl_log $TASK_ID $STEP "$APPROACH" "pending"`
   - Execute action
   - Log result: `jl_log $TASK_ID $STEP "$APPROACH" "$RESULT"`
   - Save checkpoint: `ck_save $TASK_ID $STEP '{"key":"value"}'`

## Integration with SOUL.md

This skill provides the MECHANICS (checkpoints, journals, retry logic). SOUL.md provides the MINDSET (discipline, success-checks, escalation). Together they make Hermes a reliable execution engine.

When a task is complex (> 3 steps), Hermes MUST:
1. Source this skill
2. Create a task_id
3. Use checkpoints for every step
4. Journal all attempts
5. Follow retry classification
6. Save artifacts on failure
