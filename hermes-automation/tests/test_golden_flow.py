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
