# Anti-Carousel / Progress Detector Protocol

## Purpose

Detect when the agent spins without making real forward progress across multiple tool calls, even when each individual tool call has different arguments (evading the per-tool guardrail).

## What Counts as Carousel

1. **File read carousel** — same files read 3+ times without any write/edit/terminal action between reads
2. **Search carousel** — search_files/web_search with semantically identical queries returning same results
3. **Terminal carousel** — commands producing same output or exit codes, without file changes
4. **Read-only lock** — 5+ consecutive turns with only read/search/browse tools, zero mutating actions
5. **Context bloat without action** — conversation grows but no files modified, no tests run, no commits made

## Signals of Real Progress

- File write, patch, delete
- Terminal command with new output (different stdout/stderr)
- git commit, push, merge
- Successful test run
- New directory created
- Package installed
- API call with new result

## Implementation Strategy

### Option A: Session-level progress tracker (recommended)

Track `ProgressLedger` per agent session:
- `files_read`: set of paths + timestamps
- `files_written`: set of paths + timestamps
- `searches`: list of (query_hash, result_hash, timestamp)
- `terminal_cmds`: list of (cmd_hash, output_hash, exit_code, timestamp)
- `last_mutation_turn`: int (turn number of last write/execute/mutate)

On every tool result, update ledger and run heuristics:

```python
if len(files_read) > 0 and len(files_written) == 0 and turns_since_mutation > 5:
    return ProgressDecision("read_only_lock", risk="high")

if _file_read_carousel_detected(files_read, window=5):
    return ProgressDecision("file_read_carousel", risk="medium")

if _search_carousel_detected(searches, window=5):
    return ProgressDecision("search_carousel", risk="medium")
```

### Option B: Plugin-based (lightweight)

Use `post_tool_call` hook to observe all tool calls and emit warnings when carousel patterns detected. Does not require core patches.

## Integration with Agent Loop

The detector runs after tool execution, before next API call. If carousel detected:
- **Warning**: append system message with guidance to the model
- **Hard-stop**: break turn with synthetic response asking user for direction

## Configuration

```yaml
progress_detector:
  enabled: true
  mode: warn           # warn | halt
  read_only_turn_limit: 6
  file_read_repeat_limit: 3
  search_repeat_limit: 3
  terminal_same_output_limit: 3
```

## Files

- `docs/progress-detector-protocol.md` — this file
- `profile/progress-state/<session_id>.yaml` — live ledger (runtime only, not git)
