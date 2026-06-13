"""Tests for automation task-state mapping."""

from __future__ import annotations

import yaml

from hermes_agent.agent.automation_state import (
    state_from_automation_payload,
    write_automation_task_state,
)


def test_done_payload_maps_to_done_state():
    state = state_from_automation_payload({
        "schema_version": "hermes.automation.result.v1",
        "success": True,
        "task_id": "signup-1",
        "site": "golden",
        "completed_steps": ["open", "submit"],
        "final_url": "http://localhost/home",
    })

    assert state["session_id"] == "signup-1"
    assert state["status"] == "done"
    assert state["last_safe_step"] == "submit"
    assert state["requires_approval"] is False
    assert state["automation"]["final_url"] == "http://localhost/home"


def test_blocked_payload_maps_to_human_next_step():
    state = state_from_automation_payload({
        "schema_version": "hermes.automation.result.v1",
        "success": False,
        "task_id": "signup-2",
        "site": "example",
        "completed_steps": ["open_signup"],
        "blocked_reason": "captcha_visible",
        "blocker": {"reason": "captcha_visible", "requires_human": True},
    })

    assert state["status"] == "blocked"
    assert state["blocked_reason"] == "captcha_visible"
    assert state["requires_approval"] is True
    assert "security gate" in state["next_step"]
    assert state["automation"]["blocker"]["requires_human"] is True


def test_write_automation_task_state(tmp_path):
    update = write_automation_task_state(
        {
            "schema_version": "hermes.automation.result.v1",
            "success": False,
            "task_id": "signup-3",
            "site": "example",
            "blocked_reason": "email_verification_required",
        },
        task_state_dir=tmp_path,
        task_title="Signup example",
    )

    assert update.path.exists()
    loaded = yaml.safe_load(update.path.read_text())
    assert loaded["task_title"] == "Signup example"
    assert loaded["status"] == "blocked"
    assert "email verification" in loaded["next_step"].lower()
