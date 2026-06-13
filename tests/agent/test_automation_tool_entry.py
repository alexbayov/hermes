"""Tests for automation tool schema/handler entrypoint."""

from __future__ import annotations

import json

from hermes_agent.agent.automation_tool import AutomationRunResult
from hermes_agent.agent.automation_tool_entry import (
    AUTOMATION_TOOL_DEFINITION,
    TOOL_NAME,
    handle_run_browser_automation_recipe,
)


def test_tool_definition_shape():
    assert AUTOMATION_TOOL_DEFINITION["type"] == "function"
    fn = AUTOMATION_TOOL_DEFINITION["function"]
    assert fn["name"] == TOOL_NAME
    assert "recipe" in fn["parameters"]["required"]
    assert "task_id" in fn["parameters"]["required"]


def test_handler_requires_recipe_and_task_id():
    payload = json.loads(handle_run_browser_automation_recipe({}))
    assert payload["ok"] is False
    assert "recipe and task_id" in payload["error"]


def test_handler_runs_adapter_and_writes_task_state(monkeypatch, tmp_path):
    result_payload = {
        "schema_version": "hermes.automation.result.v1",
        "status": "blocked",
        "success": False,
        "task_id": "signup-1",
        "site": "example",
        "blocked_reason": "email_verification_required",
        "completed_steps": ["open"],
        "artifacts": {"dir": "artifacts"},
    }

    def fake_run(request, cwd=None):
        return AutomationRunResult(
            payload=result_payload,
            exit_code=2,
            stdout=json.dumps(result_payload),
            stderr="",
        )

    monkeypatch.setattr("_hermes_automation_tool_entry.run_automation_recipe", fake_run)

    out = json.loads(handle_run_browser_automation_recipe({
        "recipe": "sites/example.yaml",
        "task_id": "signup-1",
        "task_state_dir": str(tmp_path),
    }))

    assert out["ok"] is True
    assert out["status"] == "blocked"
    assert out["blocked_reason"] == "email_verification_required"
    assert out["task_state_path"].endswith("signup-1.yaml")
    assert (tmp_path / "signup-1.yaml").exists()
