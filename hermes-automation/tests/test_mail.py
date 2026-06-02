"""Tests for mail capability (HRM-20)."""
import os
import tempfile

import yaml

from harness.capabilities.mail import (
    extract_link,
    get_email_address,
    get_inbox,
    _load_mail_config,
)


def test_config_loading():
    """Provider config loads correctly."""
    cfg = _load_mail_config()
    assert cfg.provider == "mailpit"
    assert cfg.domain == "test.local"
    assert cfg.host == "127.0.0.1"


def test_get_email_address_synthesized():
    """Address is synthesized locally, ends with domain."""
    addr = get_email_address()
    assert addr.endswith("@test.local")
    assert "hermes+" in addr


def test_get_inbox_returns_config():
    """get_inbox returns the configured provider."""
    inbox = get_inbox()
    assert inbox.provider == "mailpit"


def test_extract_link_from_html():
    """Extract verification link from HTML body."""
    msg = {
        "HTML": '<a href="https://example.com/verify?token=abc">Verify</a>',
    }
    link = extract_link(msg, url_contains="verify")
    assert link == "https://example.com/verify?token=abc"


def test_extract_link_from_body():
    """Extract from plain text."""
    msg = {"Body": "Click here: https://test.com/confirm?code=xyz"}
    link = extract_link(msg, url_contains="confirm")
    assert link == "https://test.com/confirm?code=xyz"


def test_extract_link_none():
    """Returns None when no link matches."""
    msg = {"Body": "Hello, welcome!"}
    link = extract_link(msg, url_contains="verify")
    assert link is None
