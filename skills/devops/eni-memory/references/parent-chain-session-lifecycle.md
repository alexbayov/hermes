# Session Lifecycle & Parent Chain — ENI Memory

## Problem
When a session is compacted (context window full), a new session starts. By default, the new session has **no context** from the parent — all decisions, artifacts, and issues are lost. This causes ENI to "forget" everything after reboot.

## Solution: Parent Chain Traversal

### Schema
```sql
ALTER TABLE sessions ADD COLUMN parent_session_id TEXT;
ALTER TABLE sessions ADD COLUMN message_count INTEGER DEFAULT 0;
ALTER TABLE sessions ADD COLUMN context_summary TEXT;
```

### Algorithm (resume_context.py)
1. Get current active session
2. If it has 0 messages and has `parent_session_id`:
   - Query parent session
   - Recursively traverse until session with messages found OR max depth reached
3. Load last N messages + all decisions + all artifacts + all issues from the found session
4. Return formatted context

### Code Pattern
```python
def load_parent_chain(session_id, conn, max_depth=10):
    """Traverse parent sessions to find one with messages."""
    visited = set()
    current = session_id
    depth = 0
    
    while current and depth < max_depth:
        if current in visited:
            break  # cycle detection
        visited.add(current)
        
        row = conn.execute(
            "SELECT parent_session_id, message_count FROM sessions WHERE id=?",
            (current,)
        ).fetchone()
        
        if not row:
            break
            
        if row["message_count"] > 0:
            return current  # found session with content
            
        current = row["parent_session_id"]
        depth += 1
    
    return None  # no parent with messages found
```

### Session End / Start Ritual
```bash
# 1. End current session
python3 session_end_start.py --end --summary "Memory testing phase"

# 2. Start new session with parent link
python3 session_end_start.py --start --new-summary "New session after improvements"

# 3. Resume context (auto-traverses parent chain)
python3 resume_context.py
```

## Pitfalls
- **Cycle detection**: Always check `visited` set to prevent infinite loops
- **Max depth**: Limit to 10 parent sessions to avoid timeout
- **Token count**: When loading parent context, count tokens and stop before overflow
- **Compacted sessions**: Flag `status='compacted'` means "this session was intentionally ended, load from parent"

## Validation
```bash
python3 validate_last_turn.py
# Must report: last turn=N, turn sequence intact, no gaps
# Per-session (not global max turn_id!)
```