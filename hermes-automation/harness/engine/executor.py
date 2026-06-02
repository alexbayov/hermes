"""Declarative YAML executor — state machine for web automation scenarios.

HRM-12: Domain-agnostic. Reads YAML, dispatches actions through ActionRegistry,
manages checkpoints. Never hardcodes business logic.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from playwright.sync_api import Page

from harness.capabilities.browser import browser_session
from harness.capabilities.click import assert_success
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
) -> ExecutionResult:
    """Execute a site YAML scenario through all steps.

    Args:
        site_config_path: Path to YAML file.
        task_id: Unique ID for this run (checkpoints keyed by this).
        fields: Input data (email, names, etc.).
        state_dir: Directory for checkpoints.
        headless: Run browser headless.
        reset: If True, discard previous checkpoint and start fresh.
        registry: Custom ActionRegistry (default: built-in handlers).

    Returns:
        ExecutionResult with success/failure and artifacts.
    """
    site_config_path = Path(site_config_path)
    config = _load_config(site_config_path)
    registry = registry or create_default_registry()

    # Compute config hash
    config_hash = compute_config_hash(config)

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

    result = ExecutionResult(
        success=False,
        task_id=task_id,
        site=config.get("name", ""),
        config_hash=config_hash,
        artifacts_dir=str(artifacts_dir),
    )
    completed_steps = checkpoint["done_steps"] if checkpoint else []

    try:
        with browser_session(headless=headless) as page:
            for step in config.get("steps", []):
                step_id = step.get("id", "")

                # Skip if already done
                if is_step_done({"done_steps": completed_steps}, step_id):
                    logger.info("skip done step: %s", step_id)
                    result.completed_steps.append(step_id)
                    continue

                # Execute actions in this step
                for action in step.get("actions", []):
                    action_result = registry.dispatch(action, page, context)
                    result.action_results.append(action_result)
                    if not action_result.success:
                        # One more try
                        logger.warning(
                            "action failed: %s/%s: %s",
                            step_id,
                            action.get("id", "?"),
                            action_result.error,
                        )

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
                        result.final_url = page.url
                        return result

                # Mark step done
                completed_steps.append(step_id)
                result.completed_steps.append(step_id)

                # Save checkpoint
                save_checkpoint(
                    state_dir,
                    task_id,
                    {
                        "task_id": task_id,
                        "site": config.get("name"),
                        "config_hash": config_hash,
                        "current_step": step_id,
                        "done_steps": completed_steps,
                        "data": fields,
                    },
                )

        result.success = True
        result.final_url = page.url if "page" in dir() else None

    except Exception as e:
        result.error = str(e)
        result.completed_steps = completed_steps

    return result


# ── Helpers ──────────────────────────────────────────────────────────────────


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
