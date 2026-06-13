"""Tests for bounded automation context construction."""

from hermes_agent.agent.context_builder import (
    AutomationContextInput,
    SkillContext,
    build_automation_context,
    choose_relevant_skills,
)


def test_build_context_includes_core_sections():
    packet = build_automation_context(
        AutomationContextInput(
            goal="Register an account on example.com",
            task_state={"status": "active", "last_safe_step": "open_signup"},
            skills=[SkillContext(name="register-account", body="Fill signup forms safely")],
            browser_snapshot={"url": "https://example.com/signup", "buttons": ["Continue"]},
            last_result={"status": "blocked", "blocked_reason": "email_verification_required"},
            allowed_actions=["goto", "fill", "click", "mark_blocked"],
        )
    )

    assert "## Policy" in packet
    assert "## Goal" in packet
    assert "Register an account" in packet
    assert "register-account" in packet
    assert "email_verification_required" in packet
    assert "goto, fill, click, mark_blocked" in packet


def test_build_context_hard_limits_large_snapshot():
    packet = build_automation_context(
        AutomationContextInput(
            goal="Open signup",
            browser_snapshot={"dom": "x" * 50_000},
        ),
        max_chars=2_000,
        snapshot_chars=500,
    )

    assert len(packet) <= 2_000
    assert "truncated" in packet


def test_choose_relevant_skills_prefers_matching_skill():
    skills = [
        SkillContext(name="email-verification", body="Handle check your email links"),
        SkillContext(name="cookie-banner", body="Dismiss cookie consent banners"),
        SkillContext(name="github", body="Repository issue workflow"),
    ]

    selected = choose_relevant_skills(
        skills,
        goal="Continue registration after email verification",
        browser_snapshot="Check your email for a verification link",
        limit=1,
    )

    assert [s.name for s in selected] == ["email-verification"]
