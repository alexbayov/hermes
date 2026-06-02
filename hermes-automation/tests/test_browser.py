"""Tests for browser capability (HRM-2, HRM-3)."""
import pytest
from playwright.sync_api import sync_playwright

from harness.capabilities.browser import (
    COOKIE_BANNER_RULES,
    dismiss_cookie_banner,
    version_report,
)


@pytest.fixture(scope="module")
def playwright():
    """Module-level Playwright instance — started once, closed after all tests."""
    pw = sync_playwright().start()
    yield pw
    pw.stop()


@pytest.fixture
def browser(playwright):
    """Per-test browser + context auto-closed."""
    browser = playwright.chromium.launch(
        headless=True,
        executable_path="/usr/bin/google-chrome",
        args=["--no-sandbox"],
    )
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    yield browser, context
    context.close()
    browser.close()


@pytest.fixture
def page(browser):
    """Per-test page."""
    _, context = browser
    pg = context.new_page()
    yield pg
    pg.close()


def test_launch_and_navigate(page):
    """Browser launches and navigates to about:blank."""
    page.goto("about:blank")
    assert page.title() == ""


def test_launch_repeatable(page):
    """Multiple tests can get pages — proves stability."""
    page.goto("about:blank")


def test_dismiss_cookie_banner_no_banner(page):
    """No banner on blank page — returns False gracefully."""
    page.goto("about:blank")
    result = dismiss_cookie_banner(page)
    assert result is False


def test_dismiss_cookie_banner_no_crash(page):
    """dismiss_cookie_banner never raises."""
    page.goto("about:blank")
    result = dismiss_cookie_banner(page)
    assert isinstance(result, bool)


def test_version_report():
    """Version report includes expected keys."""
    report = version_report()
    assert "python_version" in report
    assert "os" in report
    assert "playwright_version" in report
    assert "chromium_path" in report


def test_browser_session_closes(page):
    """Page is usable and closes without errors."""
    page.goto("about:blank")
    assert page.title() == ""


def test_cookie_banner_rules_not_empty():
    """Banner rules list is populated."""
    assert len(COOKIE_BANNER_RULES) > 0
    for rule in COOKIE_BANNER_RULES:
        assert isinstance(rule, dict)
        # Each rule has at least one identification method
        assert any(k in rule for k in ("role", "text", "selector"))
