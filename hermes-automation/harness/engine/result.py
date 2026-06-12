"""Structured result serialization for Hermes automation runs.

The automation harness is consumed by Hermes agent code through a stable JSON
contract instead of Python dataclass internals. Keep this module lightweight and
side-effect free so it can be used by CLI tests without launching a browser.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from harness.capabilities.state import load_checkpoint
from harness.engine.executor import ExecutionResult


def _action_result_to_dict(action: Any) -> dict[str, Any]:
    """Convert an ActionResult-like object to a JSON-safe dict."""
    if hasattr(action, "__dataclass_fields__"):
        return asdict(action)
    if isinstance(action, dict):
        return action
    return {"repr": repr(action)}


def result_to_dict(
    result: ExecutionResult,
    *,
    state_dir: str | Path | None = None,
    include_actions: bool = True,
) -> dict[str, Any]:
    """Return the stable JSON contract for a completed automation run.

    Status values:
    - ``done``: all recipe steps completed.
    - ``blocked``: execution stopped before completion and can be resumed or
      inspected by Hermes/human operator.

    ``checkpoint`` is read after execution when ``state_dir`` is supplied. It is
    expected to already have secret fields redacted by the executor.
    """

    checkpoint = None
    if state_dir is not None:
        checkpoint = load_checkpoint(state_dir, result.task_id)

    done_steps = list(result.completed_steps)
    current_step = None
    if checkpoint:
        current_step = checkpoint.get("current_step")
        done_steps = checkpoint.get("done_steps", done_steps)

    payload: dict[str, Any] = {
        "schema_version": "hermes.automation.result.v1",
        "status": "done" if result.success else "blocked",
        "success": result.success,
        "task_id": result.task_id,
        "site": result.site,
        "current_step": current_step,
        "completed_steps": done_steps,
        "final_url": result.final_url,
        "config_hash": result.config_hash,
        "error": result.error,
        "artifacts": {
            "dir": result.artifacts_dir,
            "trace": result.trace_path,
        },
        "checkpoint": checkpoint,
    }

    if include_actions:
        payload["actions"] = [
            _action_result_to_dict(action) for action in result.action_results
        ]

    return payload
