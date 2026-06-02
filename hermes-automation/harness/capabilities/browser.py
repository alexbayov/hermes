"""Browser capability: Playwright launch, context, page management.

HRM-2 + HRM-3: Unified browser lifecycle with cookie/modal dismissal.
"""

from __future__ import annotations

import logging
import platform
from contextlib import contextmanager
from typing import Iterator

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    sync_playwright,
)

logger = logging.getLogger("hermes.browser")

DEFAULT_VIEWPORT = {"width": 1280, "height": 900}
DEFAULT_DEVICE_SCALE_FACTOR = 1.0
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)

# Known cookie banner selectors — idempotent, safe to try
COOKIE_BANNER_RULES: list[dict] = [
    {"role": "button", "name": "Accept all cookies"},
    {"role": "button", "name": "Accept all"},
    {"role": "button", "name": "Accept cookies"},
    {"role": "button", "name": "I accept"},
    {"role": "button", "name": "OK"},
    {"role": "button", "name": "Got it"},
    {"text": "Accept all cookies"},
    {"text": "Accept cookies"},
    {"text": "Accept all"},
    {"text": "I accept"},
    # German
    {"role": "button", "name": "Alle akzeptieren"},
    {"role": "button", "name": "Akzeptieren"},
    {"role": "button", "name": "Verstanden"},
    # French
    {"role": "button", "name": "Tout accepter"},
    {"role": "button", "name": "Accepter"},
    {"role": "button", "name": "J'accepte"},
    # Generic
    {"selector": "[aria-label='Accept all cookies']"},
    {"selector": "[data-testid='cookie-accept']"},
]

BANNER_DISMISS_TIMEOUT_MS = 2_000


def launch_context(
    *,
    headless: bool = True,
    executable_path: str | None = "/usr/bin/google-chrome",
    browser_args: list[str] | None = None,
    storage_state: str | None = None,
    viewport: dict | None = None,
    device_scale_factor: float = DEFAULT_DEVICE_SCALE_FACTOR,
    user_agent: str | None = None,
    trace: bool = True,
    playwright_instance: Playwright | None = None,
) -> tuple[Browser, BrowserContext, Playwright]:
    """Launch browser and create a context.

    Returns (browser, context, playwright). Caller must close all.

    Args:
        headless: Run without UI. Always a bool per spec.
        executable_path: Path to Chrome/Chromium binary.
        browser_args: Extra Chrome CLI args (e.g. ['--no-sandbox']).
        storage_state: Path to Playwright storage state JSON for session resume.
        viewport: Override default viewport dict.
        device_scale_factor: Device pixel ratio.
        user_agent: Custom UA string (not for stealth, for client compat).
        trace: Whether to enable Playwright trace on context.
        playwright_instance: Reuse existing Playwright manager (for tests).
    """
    if browser_args is None:
        browser_args = ["--no-sandbox"]

    if playwright_instance is not None:
        playwright = playwright_instance
    else:
        playwright = sync_playwright().start()

    browser = playwright.chromium.launch(
        headless=headless,
        executable_path=executable_path,
        args=browser_args,
    )

    viewport = viewport or DEFAULT_VIEWPORT
    context_kwargs: dict = {
        "viewport": viewport,
        "device_scale_factor": device_scale_factor,
    }
    if storage_state is not None:
        context_kwargs["storage_state"] = storage_state
    if user_agent is not None:
        context_kwargs["user_agent"] = user_agent

    context = browser.new_context(**context_kwargs)

    if trace:
        context.tracing.start(screenshots=False, snapshots=True)

    return browser, context, playwright


def new_page(context: BrowserContext) -> Page:
    """Create a new page with console/network listeners.

    Attaches safe cookie/modal dismissal handlers if configured.
    """
    page = context.new_page()

    # Console listener
    page.on("console", lambda msg: logger.debug("console.%s: %s", msg.type, msg.text))

    # Network failure listener
    page.on(
        "requestfailed",
        lambda req: logger.debug(
            "network.failed: %s %s — %s", req.method, req.url, req.failure
        ),
    )

    return page


def dismiss_cookie_banner(page: Page) -> bool:
    """Try to dismiss known cookie banners on the page.

    Returns True if something was closed, False if nothing found.
    Never raises — banners are optional.
    """
    for rule in COOKIE_BANNER_RULES:
        try:
            if "role" in rule and "name" in rule:
                locator = page.get_by_role(rule["role"], name=rule["name"])
            elif "text" in rule:
                locator = page.get_by_text(rule["text"], exact=True)
            elif "selector" in rule:
                locator = page.locator(rule["selector"])
            else:
                continue

            # Quick check: is it visible?
            if locator.count() > 0 and locator.first.is_visible():
                locator.first.click(timeout=BANNER_DISMISS_TIMEOUT_MS)
                logger.info("dismissed banner: %s", rule)
                return True
        except Exception:
            continue

    return False


def close_browser(browser: Browser) -> None:
    """Safely close browser — no exceptions on already-closed."""
    try:
        browser.close()
    except Exception:
        pass


@contextmanager
def browser_session(
    *,
    headless: bool = True,
    executable_path: str | None = "/usr/bin/google-chrome",
    viewport: dict | None = None,
    storage_state: str | None = None,
    playwright_instance: Playwright | None = None,
) -> Iterator[Page]:
    """Context manager: opens browser, yields page, closes everything.

    Usage:
        with browser_session() as page:
            page.goto("https://example.com")
    """
    browser, context, playwright = launch_context(
        headless=headless,
        executable_path=executable_path,
        viewport=viewport,
        storage_state=storage_state,
        playwright_instance=playwright_instance,
    )
    own_playwright = playwright_instance is None
    page = new_page(context)
    try:
        yield page
    finally:
        try:
            context.close()
        except Exception:
            pass
        close_browser(browser)
        if own_playwright:
            try:
                playwright.stop()
            except Exception:
                pass


def version_report() -> dict:
    """Return environment info for run reports."""
    return {
        "python_version": platform.python_version(),
        "os": platform.system(),
        "os_release": platform.release(),
        "playwright_version": _get_playwright_version(),
        "chromium_path": "/usr/bin/google-chrome",
    }


def _get_playwright_version() -> str:
    try:
        import playwright
        return getattr(playwright, "__version__", "unknown")
    except ImportError:
        return "not installed"
