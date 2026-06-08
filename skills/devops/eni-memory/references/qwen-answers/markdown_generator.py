"""Markdown generator with strict 2200-character limit from Qwen (qwen-coder).
Truncates at section boundaries (oldest sections first)."""

def generate_markdown_with_limit(decisions, artifacts, issues, max_chars=2200):
    """
    Generates markdown with strict character limit.

    Args:
        decisions: List of dicts with 'id', 'title', 'rationale'
        artifacts: List of dicts with 'path', 'desc'
        issues: List of dicts with 'desc', 'severity'
        max_chars: Hard limit (default 2200)

    Returns:
        str: Markdown string within max_chars
    """
    def truncate_sections(sections, limit):
        """Truncates sections in reverse order until under limit."""
        while len(''.join(sections)) > limit:
            if not sections:
                break
            sections.pop(0)  # Remove oldest section (first in list)
        return ''.join(sections)

    # Format each section
    sections = []

    # Issues section (oldest)
    if issues:
        issue_md = "## Issues\n\n"
        for i in issues:
            desc = i['desc'][:60]
            severity = i['severity']
            issue_md += f"- {desc} ({severity})\n"
        sections.append(issue_md + "\n")

    # Artifacts section (middle)
    if artifacts:
        artifact_md = "## Artifacts\n\n"
        for a in artifacts:
            path = a['path']
            desc = a['desc'][:80]
            artifact_md += f"- `{path}`: {desc}\n"
        sections.append(artifact_md + "\n")

    # Decisions section (newest)
    if decisions:
        decision_md = "## Decisions\n\n"
        for d in decisions:
            id_val = d['id']
            title = d['title'][:80]
            rationale = d['rationale'][:120]
            decision_md += f"### {id_val}: {title}\n{rationale}\n\n"
        sections.append(decision_md)

    # Apply truncation starting from oldest sections
    result = truncate_sections(sections, max_chars)
    return result.rstrip()  # Remove trailing whitespace


# Example usage:
if __name__ == "__main__":
    decisions = [
        {"id": "D003", "title": "Use microservices", "rationale": "Improve scalability and maintainability"},
        {"id": "D004", "title": "Adopt event sourcing", "rationale": "Ensure audit trail and temporal queries"}
    ]
    artifacts = [
        {"path": "src/main.py", "desc": "Main application entry point"},
        {"path": "docs/spec.md", "desc": "System specification document"}
    ]
    issues = [
        {"desc": "High memory usage in prod", "severity": "critical"},
        {"desc": "Slow query response", "severity": "medium"}
    ]

    markdown = generate_markdown_with_limit(decisions, artifacts, issues)
    print(f"Length: {len(markdown)} chars")
    print(markdown)
