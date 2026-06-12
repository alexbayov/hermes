"""Tests for safe blocker detection."""

from harness.capabilities.blockers import detect_blocker_from_text
from harness.engine.executor import ExecutionResult
from harness.engine.result import result_to_dict


def test_detect_captcha_text():
    blocker = detect_blocker_from_text("Please verify you are human with CAPTCHA")
    assert blocker is not None
    assert blocker.reason == "captcha_visible"
    assert blocker.requires_human is True


def test_detect_two_factor_text():
    blocker = detect_blocker_from_text("Enter the one-time code from your authenticator app")
    assert blocker is not None
    assert blocker.reason == "two_factor_required"


def test_detect_email_verification_text():
    blocker = detect_blocker_from_text("Check your email for a verification link")
    assert blocker is not None
    assert blocker.reason == "email_verification_required"


def test_result_contract_includes_blocker():
    result = ExecutionResult(
        success=False,
        task_id="task-blocked",
        site="example",
        error="Blocked by captcha_visible",
        blocked_reason="captcha_visible",
        blocker={
            "reason": "captcha_visible",
            "confidence": 0.95,
            "matched": "CAPTCHA",
            "requires_human": True,
        },
    )
    payload = result_to_dict(result, include_actions=False)
    assert payload["status"] == "blocked"
    assert payload["blocked_reason"] == "captcha_visible"
    assert payload["blocker"]["requires_human"] is True
