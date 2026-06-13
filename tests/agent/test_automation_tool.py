"""Tests for hermes-automation subprocess adapter."""

from __future__ import annotations

import json
import subprocess

import pytest

from hermes_agent.agent.automation_tool import (
    AutomationRunRequest,
    AutomationToolError,
    build_automation_command,
    run_automation_recipe,
    summarize_automation_result,
)


def test_build_automation_command_contains_contract_args():
    request = AutomationRunRequest(
        recipe="sites/golden_onboarding.yaml",
        task_id="task-1",
        fields={"email": "qa@example.test"},
        state_dir="state",
        artifacts_dir="artifacts",
        reset=True,
        include_actions=False,
    )

    cmd = build_automation_command(request, python_executable="python")

    assert cmd[:4] == ["python", "-m", "harness.cli", "run"]
    assert "--recipe" in cmd
    assert "sites/golden_onboarding.yaml" in cmd
    assert "--reset" in cmd
    assert "--no-actions" in cmd
    assert json.loads(cmd[cmd.index("--fields") + 1]) == {"email": "qa@example.test"}


def test_run_automation_recipe_parses_done(monkeypatch, tmp_path):
    payload = {
        "schema_version": "hermes.automation.result.v1",
        "status": "done",
        "success": True,
        "task_id": "task-1",
        "site": "golden",
        "completed_steps": ["open"],
        "final_url": "http://localhost/home",
    }

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, json.dumps(payload), "")

    monkeypatch.setattr("subprocess.run", fake_run)

    result = run_automation_recipe(
        AutomationRunRequest(recipe="r.yaml", task_id="task-1"),
        cwd=tmp_path,
        python_executable="python",
    )

    assert result.success is True
    assert result.status == "done"
    assert "completed_steps=1" in summarize_automation_result(result)


def test_run_automation_recipe_accepts_blocked_exit(monkeypatch, tmp_path):
    payload = {
        "schema_version": "hermes.automation.result.v1",
        "status": "blocked",
        "success": False,
        "task_id": "task-2",
        "site": "example",
        "blocked_reason": "captcha_visible",
    }

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 2, json.dumps(payload), "")

    monkeypatch.setattr("subprocess.run", fake_run)

    result = run_automation_recipe(
        AutomationRunRequest(recipe="r.yaml", task_id="task-2"),
        cwd=tmp_path,
        python_executable="python",
    )

    assert result.success is False
    assert result.status == "blocked"
    assert result.blocked_reason == "captcha_visible"


def test_run_automation_recipe_rejects_bad_schema(monkeypatch, tmp_path):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, '{"schema_version":"wrong"}', "")

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(AutomationToolError):
        run_automation_recipe(
            AutomationRunRequest(recipe="r.yaml", task_id="task-3"),
            cwd=tmp_path,
            python_executable="python",
        )
