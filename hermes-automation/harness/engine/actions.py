"""Action registry and dispatch engine.

HRM-5: Domain-agnostic action dispatch. New actions registered here,
NOT as special branches in executor.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from playwright.sync_api import Page

logger = logging.getLogger("hermes.actions")


# ── Action Result ────────────────────────────────────────────────────────────


@dataclass
class ActionResult:
    """Result of executing a single action."""

    success: bool
    action_type: str
    action_id: str | None = None
    url_before: str = ""
    url_after: str = ""
    duration_ms: float = 0
    error: str | None = None
    extra: dict = field(default_factory=dict)


# ── Execution Context ────────────────────────────────────────────────────────


@dataclass
class ExecutionContext:
    """Data available to all action handlers during a run."""

    task_id: str
    fields: dict = field(default_factory=dict)
    capabilities: dict = field(default_factory=dict)
    state_dir: str = "state"
    artifacts_dir: str = "artifacts"


# ── Action Handler Protocol ──────────────────────────────────────────────────


class ActionHandler(Protocol):
    """Protocol for action handlers."""

    def run(
        self,
        page: Page,
        action: dict,
        context: ExecutionContext,
    ) -> ActionResult: ...


# ── Registry ─────────────────────────────────────────────────────────────────


class ActionRegistry:
    """Registry of action_type → handler mappings.

    Executor.dispatches through this — never hardcodes domain logic.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, ActionHandler] = {}

    def register(self, action_type: str, handler: ActionHandler) -> None:
        """Register a handler for an action type."""
        if action_type in self._handlers:
            logger.warning("overwriting handler for '%s'", action_type)
        self._handlers[action_type] = handler

    def dispatch(
        self,
        action: dict,
        page: Page,
        context: ExecutionContext,
    ) -> ActionResult:
        """Look up handler by action['type'] and execute it."""
        action_type = action.get("type", "")
        handler = self._handlers.get(action_type)
        if handler is None:
            return ActionResult(
                success=False,
                action_type=action_type,
                error=f"No handler registered for action type: '{action_type}'",
            )
        return handler.run(page, action, context)


# ── Built-in Handlers ────────────────────────────────────────────────────────


class GotoHandler:
    """Navigate to a URL."""

    def run(
        self, page: Page, action: dict, context: ExecutionContext
    ) -> ActionResult:
        from time import monotonic

        url = action.get("payload", {}).get("url", "")
        t0 = monotonic()
        try:
            page.goto(url)
            return ActionResult(
                success=True,
                action_type="goto",
                action_id=action.get("id"),
                url_before="",
                url_after=page.url,
                duration_ms=(monotonic() - t0) * 1000,
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action_type="goto",
                action_id=action.get("id"),
                error=str(e),
            )


class FillHandler:
    """Fill a text field."""

    def run(
        self, page: Page, action: dict, context: ExecutionContext
    ) -> ActionResult:
        from time import monotonic

        from harness.capabilities.click import fill_role, fill_selector

        payload = action.get("payload", {})
        value = payload.get("value", "")

        # Resolve value from fields if it's a key reference
        if value in context.fields:
            value = context.fields[value]

        t0 = monotonic()
        try:
            if "selector" in payload:
                fill_selector(page, payload["selector"], value)
            elif "role" in payload:
                fill_role(page, payload["role"], payload.get("name", ""), value)
            else:
                return ActionResult(
                    success=False,
                    action_type="fill",
                    error="fill requires 'role' or 'selector' in payload",
                )
            return ActionResult(
                success=True,
                action_type="fill",
                action_id=action.get("id"),
                duration_ms=(monotonic() - t0) * 1000,
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action_type="fill",
                action_id=action.get("id"),
                error=str(e),
            )


class ClickHandler:
    """Click an element."""

    def run(
        self, page: Page, action: dict, context: ExecutionContext
    ) -> ActionResult:
        from time import monotonic

        from harness.capabilities.click import click_role, click_text

        payload = action.get("payload", {})
        t0 = monotonic()
        try:
            if "role" in payload:
                click_role(page, payload["role"], payload.get("name", ""))
            elif "text" in payload:
                click_text(page, payload["text"], exact=payload.get("exact", False))
            elif "selector" in payload:
                page.locator(payload["selector"]).first.click()
            else:
                return ActionResult(
                    success=False,
                    action_type="click",
                    error="click requires 'role', 'text', or 'selector'",
                )

            url_after = page.url
            return ActionResult(
                success=True,
                action_type="click",
                action_id=action.get("id"),
                url_after=url_after,
                duration_ms=(monotonic() - t0) * 1000,
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action_type="click",
                action_id=action.get("id"),
                error=str(e),
            )


class CheckHandler:
    """Check a checkbox."""

    def run(
        self, page: Page, action: dict, context: ExecutionContext
    ) -> ActionResult:
        from time import monotonic

        from harness.capabilities.click import check_box

        payload = action.get("payload", {})
        t0 = monotonic()
        try:
            check_box(page, payload.get("label", ""))
            return ActionResult(
                success=True,
                action_type="check",
                action_id=action.get("id"),
                duration_ms=(monotonic() - t0) * 1000,
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action_type="check",
                action_id=action.get("id"),
                error=str(e),
            )


class WaitForUrlHandler:
    """Wait for URL to contain a string."""

    def run(
        self, page: Page, action: dict, context: ExecutionContext
    ) -> ActionResult:
        from time import monotonic

        payload = action.get("payload", {})
        t0 = monotonic()
        try:
            page.wait_for_url(
                lambda url: payload["url_contains"] in url,
                timeout=payload.get("timeout_ms", 15_000),
            )
            return ActionResult(
                success=True,
                action_type="wait_for_url",
                action_id=action.get("id"),
                url_after=page.url,
                duration_ms=(monotonic() - t0) * 1000,
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action_type="wait_for_url",
                action_id=action.get("id"),
                error=str(e),
            )


class WaitForTextHandler:
    """Wait for text to appear on the page."""

    def run(
        self, page: Page, action: dict, context: ExecutionContext
    ) -> ActionResult:
        from time import monotonic

        payload = action.get("payload", {})
        t0 = monotonic()
        try:
            page.get_by_text(payload["text"]).first.wait_for(
                state="visible",
                timeout=payload.get("timeout_ms", 15_000),
            )
            return ActionResult(
                success=True,
                action_type="wait_for_text",
                action_id=action.get("id"),
                duration_ms=(monotonic() - t0) * 1000,
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action_type="wait_for_text",
                action_id=action.get("id"),
                error=str(e),
            )


class ScreenshotHandler:
    """Take a screenshot."""

    def run(
        self, page: Page, action: dict, context: ExecutionContext
    ) -> ActionResult:
        from pathlib import Path
        from time import monotonic

        payload = action.get("payload", {})
        name = payload.get("name", action.get("id", "screenshot"))
        artifacts = Path(context.artifacts_dir) / context.task_id / "screenshots"
        artifacts.mkdir(parents=True, exist_ok=True)
        path = artifacts / f"{name}.png"

        t0 = monotonic()
        try:
            page.screenshot(path=str(path))
            return ActionResult(
                success=True,
                action_type="screenshot",
                action_id=action.get("id"),
                extra={"path": str(path)},
                duration_ms=(monotonic() - t0) * 1000,
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action_type="screenshot",
                action_id=action.get("id"),
                error=str(e),
            )


# ── Default Registry ─────────────────────────────────────────────────────────


def create_default_registry() -> ActionRegistry:
    """Create an ActionRegistry with all built-in handlers registered."""
    registry = ActionRegistry()
    registry.register("goto", GotoHandler())
    registry.register("fill", FillHandler())
    registry.register("click", ClickHandler())
    registry.register("check", CheckHandler())
    registry.register("wait_for_url", WaitForUrlHandler())
    registry.register("wait_for_text", WaitForTextHandler())
    registry.register("screenshot", ScreenshotHandler())
    return registry
