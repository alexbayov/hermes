"""DOM/ARIA primitives for browser interactions.

HRM-6: Unified layer for click_role, fill_role, check_box, assert_success.
All actions go through Playwright locator/actionability — no coordinates, no sleep, no DOM violence.
"""

from __future__ import annotations

import logging

from playwright.sync_api import Page, expect

logger = logging.getLogger("hermes.click")

DEFAULT_TIMEOUT_MS = 10_000


def click_role(
    page: Page,
    role: str,
    name: str,
    *,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> None:
    """Click element by ARIA role and accessible name."""
    locator = page.get_by_role(role, name=name)
    locator.first.wait_for(state="visible", timeout=timeout_ms)
    locator.first.click(timeout=timeout_ms)


def click_text(
    page: Page,
    text: str,
    *,
    exact: bool = False,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> None:
    """Click element containing text."""
    locator = page.get_by_text(text, exact=exact)
    locator.first.wait_for(state="visible", timeout=timeout_ms)
    locator.first.click(timeout=timeout_ms)


def fill_role(
    page: Page,
    role: str,
    name: str,
    value: str,
    *,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> None:
    """Fill a textbox/input by ARIA role and name."""
    locator = page.get_by_role(role, name=name)
    locator.first.wait_for(state="visible", timeout=timeout_ms)
    locator.first.fill(value, timeout=timeout_ms)


def fill_label(
    page: Page,
    label: str,
    value: str,
    *,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> None:
    """Fill an input by its associated label text."""
    loc = page.get_by_label(label)
    loc.first.wait_for(state="visible", timeout=timeout_ms)
    loc.first.fill(value, timeout=timeout_ms)


def fill_selector(
    page: Page,
    selector: str,
    value: str,
    *,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> None:
    """Fill an input by CSS selector."""
    locator = page.locator(selector)
    locator.first.wait_for(state="visible", timeout=timeout_ms)
    locator.first.fill(value, timeout=timeout_ms)


def check_box(
    page: Page,
    label: str,
    *,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> None:
    """Check a checkbox by its label — idempotent via Playwright .check().

    .check() is a no-op if already checked and asserts the final state.
    """
    # Strategy 1: role=checkbox with name=label
    cb = page.get_by_role("checkbox", name=label)
    if cb.count() > 0:
        cb.first.wait_for(state="visible", timeout=timeout_ms)
        cb.first.check(timeout=timeout_ms)
        return

    # Strategy 2: label-associated input via get_by_label
    try:
        page.get_by_label(label).first.check(timeout=timeout_ms)
        return
    except Exception:
        pass

    raise RuntimeError(f"Checkbox not found: {label}")


def assert_success(
    page: Page,
    *,
    url_contains: str | None = None,
    visible_role: tuple[str, str] | None = None,
    visible_text: str | None = None,
    selector: str | None = None,
    timeout_ms: int = 15_000,
) -> None:
    """Assert postconditions after an action group.

    At least one condition must be specified.
    """
    if all(v is None for v in (url_contains, visible_role, visible_text, selector)):
        raise ValueError("assert_success requires at least one condition")

    if url_contains is not None:
        page.wait_for_url(lambda u: url_contains in u, timeout=timeout_ms)

    if visible_role is not None:
        role, name = visible_role
        locator = page.get_by_role(role, name=name)
        expect(locator.first).to_be_visible(timeout=timeout_ms)

    if visible_text is not None:
        expect(page.get_by_text(visible_text).first).to_be_visible(
            timeout=timeout_ms
        )

    if selector is not None:
        expect(page.locator(selector).first).to_be_visible(timeout=timeout_ms)
