"""Declarative YAML executor — state machine for web automation scenarios.

HRM-12: Domain-agnostic. Reads YAML, dispatches actions through ActionRegistry,
manages checkpoints, redacts secrets, captures trace.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from harness.capabilities.blockers import detect_blocker
from harness.capabilities.browser import launch_context, new_page
from harness.capabilities.click import assert_success
from harness.capabilities.redaction import Redactor
from harness.capabilities.state import (
    ConfigMismatchError,
    compute_config_hash,
    is_step_done,
    save_checkpoint,
    validate_resume,
)
from harness.engine.actions import (
    ActionRegistry,
    ActionResult,
    ExecutionContext,
    create_default_registry,
)
from harness.engine.retry import RetryPolicy, dispatch_with_retry

logger = logging.getLogger("hermes.executor")


# ── Execution Result ─────────────────────────────────────────────────────────


@dataclass
class ExecutionResult:
    """Final result of running a site scenario."""

    success: bool
    task_id: str
    site: str
    final_url: str | None = None
    completed_steps: list[str] = field(default_factory=list)
    config_hash: str = ""
    artifacts_dir: str = ""
    error: str | None = None
    action_results: list[ActionResult] = field(default_factory=list)
    trace_path: str | None = None
    blocked_reason: str | None = None
    blocker: dict[str, Any] | None = None


# ── Helpers ──────────────────────────────────────────────────────────────────


def _safe_url(page) -> str:
    """Get current URL safely — empty string if page is closed."""
    try:
        return page.url
    except Exception:
        return ""


def _load_config(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _parse_visible_role(success_cond: dict) -> tuple[str, str] | None:
    role = success_cond.get("visible_role") or success_cond.get("role")
    name = success_cond.get("visible_name") or success_cond.get("name")
    if role and name:
        return (role, name)
    return None


def _reset_run(task_id: str, state_dir: str | Path) -> None:
    from harness.capabilities.state import reset_checkpoint
    reset_checkpoint(state_dir, task_id)


def _mark_blocked_if_detected(result: ExecutionResult, page) -> bool:
    """Attach structured blocker info to result if page shows a known gate."""
    blocker = detect_blocker(page)
    if blocker is None:
        return False
    result.blocked_reason = blocker.reason
    result.blocker = blocker.to_dict()
    if not result.error:
        result.error = f"Blocked by {blocker.reason}"
    return True


# ── Core Executor ────────────────────────────────────────────────────────────


def run_site_config(
    site_config_path: str | Path,
    *,
    task_id: str,
    fields: dict,
    state_dir: str | Path = "state",
    artifacts_dir: str | Path = "artifacts",
    headless: bool = True,
    reset: bool = False,
    registry: ActionRegistry | None = None,
    executable_path: str | None = None,
) -> ExecutionResult:
    """Execute a site YAML scenario through all steps.

    Args:
        site_config_path: Path to YAML file.
        task_id: Unique ID for this run (checkpoints keyed by this).
        fields: Input data (email, names, etc.).
        state_dir: Directory for checkpoints.
        artifacts_dir: Directory for artifacts (screenshots, trace).
        headless: Run browser headless.
        reset: If True, discard previous checkpoint and start fresh.
        registry: Custom ActionRegistry (default: built-in handlers).
        executable_path: Path to Chrome/Chromium binary (optional).

    Returns:
        ExecutionResult with success/failure and artifacts.
    """
    site_config_path = Path(site_config_path)
    config = _load_config(site_config_path)
    registry = registry or create_default_registry()

    # Compute config hash
    config_hash = compute_config_hash(config)
    state_dir = Path(state_dir)
    artifacts_dir = Path(artifacts_dir)

    # Redaction setup
    secret_fields = {
        name
        for name, spec in (config.get("fields_schema") or {}).items()
        if isinstance(spec, dict) and spec.get("secret")
    }
    redactor = Redactor([str(fields[k]) for k in secret_fields if k in fields])

    # Reset if requested
    if reset:
        _reset_run(task_id, state_dir)

    # Try to resume
    checkpoint = None
    try:
        checkpoint = validate_resume(state_dir, task_id, config_hash)
    except ConfigMismatchError as e:
        return ExecutionResult(
            success=False,
            task_id=task_id,
            site=config.get("name", ""),
            error=f"ConfigMismatchError: {e}",
            config_hash=config_hash,
        )

    context = ExecutionContext(
        task_id=task_id,
        fields=fields,
        capabilities=config.get("capabilities", {}),
        state_dir=str(state_dir),
        artifacts_dir=str(artifacts_dir),
    )

    retry_cfg = config.get("retry", {})
    retry_policy = RetryPolicy(
        max_attempts=retry_cfg.get("max_attempts", 3),
        strategy=retry_cfg.get("strategy", "conservative"),
    )

    result = ExecutionResult(
        success=False,
        task_id=task_id,
        site=config.get("name", ""),
        config_hash=config_hash,
        artifacts_dir=str(artifacts_dir),
    )
    completed_steps = checkpoint["done_steps"] if checkpoint else []
    final_url_safe = ""

    # Browser lifecycle
    browser, browser_context, playwright = launch_context(
        headless=headless,
        executable_path=executable_path,
    )
    page = new_page(browser_context)

    # Trace management
    trace_enabled = bool(config.get("browser", {}).get("trace", False))
    if trace_enabled:
        try:
            browser_context.tracing.start(
                screenshots=True, snapshots=True, sources=True
            )
        except Exception as e:
            logger.warning("failed to start tracing: %s", e)
            trace_enabled = False

    try:
        for step in config.get("steps", []):
            step_id = step.get("id", "")

            # Skip if already done
            if is_step_done({"done_steps": completed_steps}, step_id):
                logger.info("skip done step: %s", step_id)
                result.completed_steps.append(step_id)
                continue

            # Execute actions in this step with retry
            step_failed = False
            for action in step.get("actions", []):
                retry_result = dispatch_with_retry(
                    action, page, context, registry=registry, policy=retry_policy
                )
                if retry_result.action_result:
                    result.action_results.append(retry_result.action_result)

                if not retry_result.success:
                    logger.error(
                        "step %s action %s FAILED after %d attempts: %s",
                        step_id,
                        action.get("id", "?"),
                        len(retry_result.attempts),
                        retry_result.action_result.error if retry_result.action_result else "unknown",
                    )
                    step_failed = True
                    break

            if step_failed:
                result.error = (
                    f"Step '{step_id}' failed: "
                    + (result.action_results[-1].error if result.action_results else "unknown")
                )
                result.completed_steps = completed_steps
                _mark_blocked_if_detected(result, page)
                final_url_safe = _safe_url(page)
                break

            # Assert success
            success_cond = step.get("success")
            if success_cond:
                try:
                    assert_success(
                        page,
                        url_contains=success_cond.get("url_contains"),
                        visible_text=success_cond.get("visible_text"),
                        visible_role=_parse_visible_role(success_cond),
                        selector=success_cond.get("selector"),
                    )
                except Exception as e:
                    result.error = f"Step '{step_id}' postcondition failed: {e}"
                    result.completed_steps = completed_steps
                    _mark_blocked_if_detected(result, page)
                    final_url_safe = _safe_url(page)
                    break

            # Mark step done
            completed_steps.append(step_id)
            result.completed_steps.append(step_id)
            final_url_safe = _safe_url(page)

            # Save checkpoint with redacted fields
            save_checkpoint(
                state_dir,
                task_id,
                {
                    "task_id": task_id,
                    "site": config.get("name"),
                    "config_hash": config_hash,
                    "current_step": step_id,
                    "done_steps": completed_steps,
                    "status": "active",
                    "data": redactor.redact_fields(fields, secret_fields),
                },
            )

        else:
            # All steps completed without break
            result.success = True

    except Exception as e:
        result.error = str(e)
        result.completed_steps = completed_steps
        _mark_blocked_if_detected(result, page)
        final_url_safe = _safe_url(page)

    if not result.success and result.blocked_reason:
        try:
            save_checkpoint(
                state_dir,
                task_id,
                {
                    "task_id": task_id,
                    "site": config.get("name"),
                    "config_hash": config_hash,
                    "current_step": completed_steps[-1] if completed_steps else None,
                    "done_steps": completed_steps,
                    "status": "blocked",
                    "blocked_reason": result.blocked_reason,
                    "blocker": result.blocker,
                    "data": redactor.redact_fields(fields, secret_fields),
                },
            )
        except Exception as e:
            logger.warning("failed to save blocked checkpoint: %s", e)

    # Save trace + failure screenshot on failure
    if not result.success:
        run_dir = artifacts_dir / task_id
        run_dir.mkdir(parents=True, exist_ok=True)
        try:
            page.screenshot(
                path=str(run_dir / "failure.png"),
                mask=[page.locator("input[type=password]")],
            )
        except Exception as e:
            logger.warning("failed to save failure screenshot: %s", e)
        if trace_enabled:
            try:
                browser_context.tracing.stop(path=str(run_dir / "trace.zip"))
                result.trace_path = str(run_dir / "trace.zip")
            except Exception as e:
                logger.warning("failed to save trace: %s", e)

    result.final_url = final_url_safe

    # Cleanup
    try:
        browser_context.close()
    except Exception:
        pass
    try:
        browser.close()
    except Exception:
        pass
    try:
        playwright.stop()
    except Exception:
        pass

    return result
