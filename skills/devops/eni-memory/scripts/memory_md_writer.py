"""Generate MEMORY.md from SQLite with 2200-char hard limit."""
import argparse
from datetime import datetime
from db_utils import get_conn, retry_on_lock

MEMORY_PATH = "/root/.hermes/MEMORY.md"
HARD_LIMIT = 2200


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    # Try to truncate at last newline before limit
    cut = text.rfind("\n", 0, max_len - 3)
    if cut == -1:
        cut = max_len - 3
    return text[:cut] + "..."


@retry_on_lock()
def generate_memory(max_chars: int = HARD_LIMIT):
    conn = get_conn()
    lines = []

    # Header
    lines.append("# MEMORY")
    lines.append("")
    lines.append(f"_Generated {datetime.utcnow().isoformat()}_")
    lines.append("")

    # Active session
    active = conn.execute(
        "SELECT id, parent_id, started_at, message_count, summary FROM sessions WHERE status = 'active' ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    if active:
        lines.append("## Active Session")
        lines.append(f"- **ID:** {active['id']}")
        lines.append(f"- **Parent:** {active['parent_id'] or 'none'}")
        lines.append(f"- **Started:** {active['started_at']}")
        lines.append(f"- **Messages:** {active['message_count']}")
        if active['summary']:
            lines.append(f"- **Summary:** {active['summary']}")
        lines.append("")

    # Recent closed sessions (up to 5)
    sessions = conn.execute(
        """
        SELECT id, parent_id, started_at, ended_at, message_count, summary, status
        FROM sessions WHERE status != 'active' ORDER BY started_at DESC LIMIT 5
        """
    ).fetchall()

    if sessions:
        lines.append("## Recent Sessions")
        for s in sessions:
            lines.append(f"### {s['id']} ({s['status']})")
            lines.append(f"- **Started:** {s['started_at']}")
            if s['ended_at']:
                lines.append(f"- **Ended:** {s['ended_at']}")
            lines.append(f"- **Messages:** {s['message_count']}")
            if s['summary']:
                lines.append(f"- **Summary:** {s['summary']}")
            lines.append("")

    # Key decisions (active, last 10)
    decisions = conn.execute(
        """
        SELECT session_id, turn_id, title, choice, rationale, active
        FROM decisions WHERE active = 1 ORDER BY created_at DESC LIMIT 10
        """
    ).fetchall()
    if decisions:
        lines.append("## Key Decisions")
        for d in decisions:
            lines.append(f"- **{d['title']}** ({d['session_id']} T{d['turn_id']}): {d['choice']}")
            if d['rationale']:
                lines.append(f"  - Rationale: {d['rationale']}")
        lines.append("")

    # Active artifacts (last 10)
    artifacts = conn.execute(
        """
        SELECT session_id, turn_id, name, path, type, status, description
        FROM artifacts WHERE status = 'active' ORDER BY created_at DESC LIMIT 10
        """
    ).fetchall()
    if artifacts:
        lines.append("## Active Artifacts")
        for a in artifacts:
            lines.append(f"- **{a['name']}** (`{a['type']}`): {a['path']}")
            if a['description']:
                lines.append(f"  - {a['description']}")
        lines.append("")

    # Open issues (last 10)
    issues = conn.execute(
        """
        SELECT session_id, turn_id, title, symptom, root_cause, fix, status
        FROM issues WHERE status != 'resolved' ORDER BY created_at DESC LIMIT 10
        """
    ).fetchall()
    if issues:
        lines.append("## Open Issues")
        for i in issues:
            lines.append(f"- **{i['title']}** ({i['status']})")
            if i['symptom']:
                lines.append(f"  - Symptom: {i['symptom']}")
        lines.append("")

    text = "\n".join(lines)

    # Hard limit enforcement: section-level truncation
    if len(text) > max_chars:
        # Truncate from oldest sections first
        while len(text) > max_chars and lines:
            # Remove oldest non-header line block
            # Find last section header and remove everything after it
            last_section = -1
            for i in range(len(lines) - 1, -1, -1):
                if lines[i].startswith("## "):
                    last_section = i
                    break
            if last_section > 0:
                lines = lines[:last_section]
                text = "\n".join(lines) + "\n\n_...truncated_"
            else:
                text = _truncate(text, max_chars)
                break

    if len(text) > max_chars:
        text = _truncate(text, max_chars)

    with open(MEMORY_PATH, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"MEMORY.md written: {len(text)} chars (limit {max_chars})")
    return MEMORY_PATH


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=HARD_LIMIT, help="Character hard limit")
    args = parser.parse_args()
    generate_memory(args.limit)
