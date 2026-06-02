"""Golden end-to-end test: sandbox app → full scenario → success.

HRM-18: Hermetic golden flow, no external services.
"""

import multiprocessing
import time
from pathlib import Path

import pytest

from harness.engine.executor import run_site_config

SANDBOX_APP = Path(__file__).parent.parent / "sandbox_app" / "app.py"
SITE_CONFIG = Path(__file__).parent.parent / "sites" / "golden_onboarding.yaml"


@pytest.fixture(scope="module")
def sandbox_server():
    """Start sandbox app in a subprocess, yield its URL, then stop."""
    import subprocess

    proc = subprocess.Popen(
        ["python3", str(SANDBOX_APP)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1.5)  # Let Flask start

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
    """First run succeeds from step 1, then 'resume' skips to step 4."""
    task_id = "test-golden-resume"
    fields = {
        "email": "qa-resume@example.test",
        "first_name": "Resume",
        "last_name": "Test",
        "password": "TestPass123!",
    }

    # First run — full flow
    result1 = run_site_config(
        str(SITE_CONFIG),
        task_id=task_id,
        fields=fields,
        state_dir=str(tmp_path / "state"),
        artifacts_dir=str(tmp_path / "artifacts"),
        headless=True,
        reset=True,
    )
    assert result1.success, f"First run failed: {result1.error}"
    assert result1.completed_steps == [
        "open_start",
        "submit_email",
        "verify_email",
        "onboarding",
    ]

    # Second run same task_id — should skip all steps (already done)
    result2 = run_site_config(
        str(SITE_CONFIG),
        task_id=task_id,
        fields=fields,
        state_dir=str(tmp_path / "state"),
        artifacts_dir=str(tmp_path / "artifacts"),
        headless=True,
        reset=False,
    )
    assert result2.success
    # All steps already done, so completed_steps should be the same 4
    assert len(result2.completed_steps) == 4


def test_golden_onboarding_reset(sandbox_server, tmp_path):
    """--reset flag forces a fresh run even with existing checkpoint."""
    task_id = "test-golden-reset"
    fields = {
        "email": "qa-reset@example.test",
        "first_name": "Reset",
        "last_name": "Test",
        "password": "TestPass123!",
    }

    # First run
    result1 = run_site_config(
        str(SITE_CONFIG),
        task_id=task_id,
        fields=fields,
        state_dir=str(tmp_path / "state"),
        artifacts_dir=str(tmp_path / "artifacts"),
        headless=True,
        reset=True,
    )
    assert result1.success

    # Second run with reset=True — should run all steps again
    result2 = run_site_config(
        str(SITE_CONFIG),
        task_id=task_id,
        fields=fields,
        state_dir=str(tmp_path / "state"),
        artifacts_dir=str(tmp_path / "artifacts"),
        headless=True,
        reset=True,
    )
    assert result2.success
    assert result2.completed_steps == [
        "open_start",
        "submit_email",
        "verify_email",
        "onboarding",
    ]
