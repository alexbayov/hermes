"""Retry policy and error classification.

HRM-16: Classifies errors as retriable/non-retriable.
dispatch_with_retry — action execution with smart retry.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Literal

from playwright.sync_api import Page

from harness.engine.actions import ActionResult, ExecutionContext

logger = logging.getLogger("hermes.retry")

RetryClass = Literal["retriable", "non_retriable"]


# ── Error Classification ─────────────────────────────────────────────────────


@dataclass
class RetryPolicy:
    """Per-run retry configuration."""

    max_attempts: int = 3
    strategy: str = "conservative"
    base_delay_s: float = 0.5


def classify_error(error_msg: str) -> tuple[RetryClass, str]:
    """Classify an error string as retriable or non-retriable.

    Retriable = transient UI/network glitches.
    Non-retriable = config/business logic/permission errors.
    """
    msg_lower = error_msg.lower()

    # Retriable patterns
    retriable_patterns = [
        "timeout",
        "stale element",
        "stale locator",
        "overlay",
        "not visible",
        "not yet visible",
        "intercepted",
        "network idle",
        "load state",
        "animation",
        "detached",
        "not attached",
        "connection reset",
        "connection refused",
        "no such window",
        "target closed",
        "waiting for",
        "retry",
    ]

    # Non-retriable patterns
    non_retriable_patterns = [
        "config mismatch",
        "config hash",
        "missing required field",
        "permission denied",
        "access denied",
        "wrong credential",
        "invalid password",
        "unauthorized",
        "forbidden",
        "not found: selector",
        "no handler registered",
        "postcondition failed",
        "assertion",
        "validation",
        "schema",
        "secret in plain",
        "redaction policy",
        "unsafe resume",
        "no such element",
        "resolve",
    ]

    for pattern in retriable_patterns:
        if pattern in msg_lower:
            return "retriable", error_msg

    for pattern in non_retriable_patterns:
        if pattern in msg_lower:
            return "non_retriable", error_msg

    # Default: non-retriable — be conservative
    return "non_retriable", error_msg


def is_retriable(error_msg: str) -> bool:
    """Shorthand: True if the error is worth retrying."""
    cls, _ = classify_error(error_msg)
    return cls == "retriable"


# ── Retry Dispatcher ─────────────────────────────────────────────────────────


@dataclass
class RetryResult:
    """Result after retry logic."""

    success: bool
    action_result: ActionResult | None = None
    attempts: list[str] = field(default_factory=list)


def dispatch_with_retry(
    action: dict,
    page: Page,
    context: ExecutionContext,
    *,
    registry=None,
    policy: RetryPolicy | None = None,
) -> RetryResult:
    """Execute an action with retry logic.

    - Up to policy.max_attempts attempts
    - Only retries on retriable errors
    - Different approach after each failure where possible
    """
    from harness.engine.actions import ActionRegistry, create_default_registry

    if registry is None:
        registry = create_default_registry()
    if policy is None:
        policy = RetryPolicy()

    attempts = []
    last_result = None

    for attempt in range(policy.max_attempts):
        result = registry.dispatch(action, page, context)
        attempts.append(
            f"attempt {attempt+1}: {'OK' if result.success else result.error}"
        )

        if result.success:
            return RetryResult(success=True, action_result=result, attempts=attempts)

        cls, _ = classify_error(result.error or "")
        if cls == "non_retriable":
            logger.warning(
                "action %s/%s: non-retriable error — not retrying: %s",
                action.get("type"),
                action.get("id"),
                result.error,
            )
            return RetryResult(
                success=False, action_result=result, attempts=attempts
            )

        if attempt < policy.max_attempts - 1:
            delay = policy.base_delay_s * (attempt + 1)
            logger.info(
                "action %s/%s: retry %d/%d after %.1fs: %s",
                action.get("type"),
                action.get("id"),
                attempt + 2,
                policy.max_attempts,
                delay,
                result.error,
            )
            time.sleep(delay)

        last_result = result

    return RetryResult(success=False, action_result=last_result, attempts=attempts)
