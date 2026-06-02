"""Golden end-to-end test: sandbox app → full scenario → success.

HRM-18: Hermetic golden flow, no external services.
"""

import socket
import time
from pathlib import Path

import pytest

from harness.engine.executor import run_site_config

SANDBOX_APP = Path(__file__).parent.parent / "sandbox_app" / "app.py"
SITE_CONFIG = Path(__file__).parent.parent / "sites" / "golden_onboarding.yaml"
CHROME_PATH = "/usr/bin/google-chrome"


def _wait_port(host, port, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"Server {host}:{port} did not start in {timeout}s")


@pytest.fixture(scope="module")
def sandbox_server():
    """Start sandbox app, wait for port, yield, stop."""
    import subprocess

    proc = subprocess.Popen(
        ["python3", str(SANDBOX_APP)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _wait_port("127.0.0.1", 8080)

    yield "http://localhost:8080"

    proc.terminate()
    proc.wait(timeout=5)


def test_golden_onboarding_full_flow(sandbox_server, tmp_path):
    """Run the full golden onboarding scenario — 4 steps, all succeed."""
    fields = {
        "email": "qa-user@example.test",
        "first_name": "Hermes",
        "last_name": "QA",
        "password": "TestPass123!",
    }

    result = run_site_config(
        str(SITE_CONFIG),
        task_id="test-golden-full",
        fields=fields,
        state_dir=str(tmp_path / "state"),
        artifacts_dir=str(tmp_path / "artifacts"),
        headless=True,
        reset=True,
        executable_path=CHROME_PATH,
    )

    assert result.success is True, f"Full flow failed: {result.error}"
    assert len(result.completed_steps) == 4, (
        f"Expected 4 steps, got {len(result.completed_steps)}: {result.completed_steps}"
    )
    assert "/home" in (result.final_url or ""), (
        f"Should end at /home, got {result.final_url}"
    )
    assert len(result.action_results) > 0


def test_golden_onboarding_checkpoint_resume(sandbox_server, tmp_path):
    """First run succeeds, then resume skips all done steps."""
    task_id = "test-golden-resume"
    fields = {
        "email": "qa-resume@example.test",
        "first_name": "Resume",
        "last_name": "Test",
        "password": "TestPass123!",
    }

    result1 = run_site_config(
        str(SITE_CONFIG),
        task_id=task_id,
        fields=fields,
        state_dir=str(tmp_path / "state"),
        artifacts_dir=str(tmp_path / "artifacts"),
        headless=True,
        reset=True,
        executable_path=CHROME_PATH,
    )
    assert result1.success, f"First run failed: {result1.error}"
    assert len(result1.completed_steps) == 4

    result2 = run_site_config(
        str(SITE_CONFIG),
        task_id=task_id,
        fields=fields,
        state_dir=str(tmp_path / "state"),
        artifacts_dir=str(tmp_path / "artifacts"),
        headless=True,
        reset=False,
        executable_path=CHROME_PATH,
    )
    assert result2.success
    assert len(result2.completed_steps) == 4


def test_golden_onboarding_reset(sandbox_server, tmp_path):
    """--reset flag forces a fresh run."""
    task_id = "test-golden-reset"
    fields = {
        "email": "qa-reset@example.test",
        "first_name": "Reset",
        "last_name": "Test",
        "password": "TestPass123!",
    }

    result1 = run_site_config(
        str(SITE_CONFIG),
        task_id=task_id,
        fields=fields,
        state_dir=str(tmp_path / "state"),
        artifacts_dir=str(tmp_path / "artifacts"),
        headless=True,
        reset=True,
        executable_path=CHROME_PATH,
    )
    assert result1.success

    result2 = run_site_config(
        str(SITE_CONFIG),
        task_id=task_id,
        fields=fields,
        state_dir=str(tmp_path / "state"),
        artifacts_dir=str(tmp_path / "artifacts"),
        headless=True,
        reset=True,
        executable_path=CHROME_PATH,
    )
    assert result2.success
    assert result2.completed_steps == [
        "open_start",
        "submit_email",
        "verify_email",
        "onboarding",
    ]


def test_redaction_password_not_in_checkpoint(sandbox_server, tmp_path):
    """After a successful run, the checkpoint must NOT contain the password."""
    import json

    task_id = "test-redact-cp"
    fields = {
        "email": "qa-redact@example.test",
        "first_name": "Redact",
        "last_name": "Test",
        "password": "SecretPass99!",
    }

    result = run_site_config(
        str(SITE_CONFIG),
        task_id=task_id,
        fields=fields,
        state_dir=str(tmp_path / "state"),
        artifacts_dir=str(tmp_path / "artifacts"),
        headless=True,
        reset=True,
        executable_path=CHROME_PATH,
    )
    assert result.success

    cp_path = tmp_path / "state" / f"{task_id}.json"
    assert cp_path.exists()
    with open(cp_path) as f:
        cp = json.load(f)

    data = cp.get("data", {})
    password_val = data.get("password", "")
    assert "SecretPass99!" not in str(data), (
        f"Plaintext password found in checkpoint data: {data}"
    )
    assert password_val == "***REDACTED***", (
        f"Expected redacted password, got: {password_val}"
    )


def test_failure_on_broken_config(sandbox_server, tmp_path):
    """Invalid YAML step (wrong selector) produces result.success=False."""
    import yaml
    from pathlib import Path

    broken_yaml = {
        "name": "broken_test",
        "start_url": "http://localhost:8080/signup",
        "browser": {"headless": True, "trace": False},
        "fields_schema": {},
        "steps": [
            {
                "id": "doomed_step",
                "actions": [
                    {
                        "type": "click",
                        "id": "nonexistent",
                        "payload": {"role": "button", "name": "ThisButtonDoesNotExist"},
                    }
                ],
                "success": {"visible_text": "NeverAppears"},
            }
        ],
    }

    broken_path = tmp_path / "broken.yaml"
    with open(broken_path, "w") as f:
        yaml.dump(broken_yaml, f)

    result = run_site_config(
        str(broken_path),
        task_id="test-broken",
        fields={},
        state_dir=str(tmp_path / "state"),
        artifacts_dir=str(tmp_path / "artifacts"),
        headless=True,
        reset=True,
        executable_path=CHROME_PATH,
    )

    assert result.success is False, "Broken config should fail"
    assert result.error is not None
    assert len(result.error) > 0
