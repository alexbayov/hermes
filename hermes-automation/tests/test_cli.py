"""Tests for hermes-automation CLI JSON contract."""

from __future__ import annotations

import json

from harness.cli import _load_fields, main
from harness.engine.actions import ActionResult
from harness.engine.executor import ExecutionResult
from harness.engine.result import result_to_dict


def test_load_fields_inline_json():
    assert _load_fields('{"email":"qa@example.test"}') == {
        "email": "qa@example.test"
    }


def test_result_to_dict_done_contract(tmp_path):
    result = ExecutionResult(
        success=True,
        task_id="task-1",
        site="golden",
        final_url="http://localhost/home",
        completed_steps=["open", "done"],
        config_hash="abc",
        artifacts_dir=str(tmp_path / "artifacts"),
        action_results=[
            ActionResult(success=True, action_type="goto", action_id="open")
        ],
    )

    payload = result_to_dict(result, state_dir=tmp_path / "state")

    assert payload["schema_version"] == "hermes.automation.result.v1"
    assert payload["status"] == "done"
    assert payload["success"] is True
    assert payload["task_id"] == "task-1"
    assert payload["completed_steps"] == ["open", "done"]
    assert payload["actions"][0]["action_type"] == "goto"


def test_result_to_dict_blocked_contract(tmp_path):
    result = ExecutionResult(
        success=False,
        task_id="task-2",
        site="broken",
        completed_steps=["open"],
        error="Step failed",
    )

    payload = result_to_dict(result, state_dir=tmp_path / "state", include_actions=False)

    assert payload["status"] == "blocked"
    assert payload["success"] is False
    assert payload["error"] == "Step failed"
    assert "actions" not in payload


def test_cli_run_uses_json_contract(monkeypatch, tmp_path, capsys):
    def fake_run_site_config(*args, **kwargs):
        return ExecutionResult(
            success=True,
            task_id=kwargs["task_id"],
            site="fake",
            completed_steps=["one"],
            artifacts_dir=kwargs["artifacts_dir"],
        )

    monkeypatch.setattr("harness.cli.run_site_config", fake_run_site_config)

    code = main([
        "run",
        "--recipe", "sites/fake.yaml",
        "--task-id", "task-cli",
        "--fields", '{"email":"qa@example.test"}',
        "--state-dir", str(tmp_path / "state"),
        "--artifacts-dir", str(tmp_path / "artifacts"),
    ])

    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["schema_version"] == "hermes.automation.result.v1"
    assert out["status"] == "done"
    assert out["task_id"] == "task-cli"
