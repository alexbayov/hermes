"""Bounded context builder for Hermes automation tasks.

Automation turns should not stuff the whole conversation, raw DOM, and every
skill into the model. This module builds a compact, deterministic context from:

- current task state
- one or a few selected skills
- latest browser snapshot
- latest automation result
- allowed action names

It is intentionally pure/side-effect free so callers can test and adopt it
before wiring it into the live conversation loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

DEFAULT_MAX_CHARS = 12_000
DEFAULT_SNAPSHOT_CHARS = 4_000
DEFAULT_SKILL_CHARS = 3_000


@dataclass(frozen=True)
class SkillContext:
    """A selected skill included in a bounded automation prompt."""

    name: str
    body: str
    source: str | None = None


@dataclass(frozen=True)
class AutomationContextInput:
    """Inputs required to build a bounded automation context."""

    goal: str
    task_state: Mapping[str, Any] = field(default_factory=dict)
    skills: Sequence[SkillContext] = field(default_factory=list)
    browser_snapshot: Mapping[str, Any] | str | None = None
    last_result: Mapping[str, Any] | None = None
    allowed_actions: Sequence[str] = field(default_factory=list)
    policy: str = (
        "You are Hermes browser automation planner. Use deterministic harness "
        "actions where possible. Do not bypass CAPTCHA, 2FA, phone, passkey, "
        "or anti-bot gates; mark the task blocked and request human/approved "
        "handling instead."
    )


def _compact_value(value: Any, *, max_chars: int) -> str:
    """Render value as compact text with hard char limit."""
    if value is None:
        return "null"
    if isinstance(value, str):
        text = value
    elif isinstance(value, Mapping):
        lines = []
        for key in sorted(value.keys(), key=str):
            rendered = _compact_value(value[key], max_chars=max_chars)
            lines.append(f"{key}: {rendered}")
        text = "\n".join(lines)
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        text = "\n".join(f"- {_compact_value(v, max_chars=max_chars)}" for v in value)
    else:
        text = str(value)

    if len(text) <= max_chars:
        return text
    return text[: max_chars - 32].rstrip() + "\n...[truncated]"


def _section(title: str, body: str) -> str:
    body = (body or "").strip()
    return f"## {title}\n{body}" if body else f"## {title}\n(none)"


def build_automation_context(
    ctx: AutomationContextInput,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    snapshot_chars: int = DEFAULT_SNAPSHOT_CHARS,
    skill_chars: int = DEFAULT_SKILL_CHARS,
) -> str:
    """Build a bounded prompt/context packet for one automation planning turn."""

    skill_blocks = []
    for skill in ctx.skills:
        header = skill.name if not skill.source else f"{skill.name} ({skill.source})"
        skill_blocks.append(f"### {header}\n{_compact_value(skill.body, max_chars=skill_chars)}")

    sections = [
        _section("Policy", ctx.policy),
        _section("Goal", ctx.goal),
        _section("Task state", _compact_value(dict(ctx.task_state), max_chars=2_000)),
        _section("Relevant skills", "\n\n".join(skill_blocks)),
        _section("Browser snapshot", _compact_value(ctx.browser_snapshot, max_chars=snapshot_chars)),
        _section("Last automation result", _compact_value(ctx.last_result or {}, max_chars=2_000)),
        _section("Allowed actions", ", ".join(ctx.allowed_actions) or "none"),
    ]

    packet = "\n\n".join(sections).strip()
    if len(packet) <= max_chars:
        return packet
    return packet[: max_chars - 64].rstrip() + "\n\n...[context truncated to budget]"


def choose_relevant_skills(
    skills: Sequence[SkillContext],
    *,
    goal: str,
    browser_snapshot: Mapping[str, Any] | str | None = None,
    limit: int = 2,
) -> list[SkillContext]:
    """Small deterministic skill selector.

    This is deliberately simple: it ranks by token overlap in skill name/body
    against goal + browser snapshot. It gives Hermes a safe fallback until a
    richer registry/index is wired in.
    """

    query = f"{goal}\n{_compact_value(browser_snapshot, max_chars=1_000)}".lower()
    terms = {t for t in query.replace("_", " ").split() if len(t) >= 4}

    scored: list[tuple[int, int, SkillContext]] = []
    for idx, skill in enumerate(skills):
        haystack = f"{skill.name}\n{skill.body}".lower().replace("_", " ")
        score = sum(1 for term in terms if term in haystack)
        scored.append((score, -idx, skill))

    scored.sort(reverse=True)
    return [skill for score, _, skill in scored[:limit] if score > 0]
