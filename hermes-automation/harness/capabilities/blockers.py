"""Browser blocker detection for safe automation stops.

The harness should not blindly keep clicking when a site asks for CAPTCHA,
2FA, phone verification, passkeys, or other human/security gates. This module
only detects blockers and returns structured reasons; it does not solve or
bypass them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class Blocker:
    """A detected condition that should stop autonomous execution."""

    reason: str
    confidence: float
    matched: str
    requires_human: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_PATTERNS: list[tuple[str, float, re.Pattern[str]]] = [
    (
        "captcha_visible",
        0.95,
        re.compile(r"\b(captcha|recaptcha|hcaptcha|verify you are human|i'?m not a robot)\b", re.I),
    ),
    (
        "two_factor_required",
        0.9,
        re.compile(r"\b(2fa|two[- ]factor|multi[- ]factor|authentication code|verification code|one[- ]time code|otp)\b", re.I),
    ),
    (
        "phone_verification_required",
        0.9,
        re.compile(r"\b(phone verification|verify your phone|phone number|sms code|text message code)\b", re.I),
    ),
    (
        "passkey_required",
        0.9,
        re.compile(r"\b(passkey|security key|webauthn|touch your security key|biometric)\b", re.I),
    ),
    (
        "email_verification_required",
        0.85,
        re.compile(r"\b(check your email|verify your email|confirmation email|verification link|email verification)\b", re.I),
    ),
    (
        "rate_limited",
        0.8,
        re.compile(r"\b(too many attempts|try again later|rate limit|temporarily blocked|temporarily unavailable)\b", re.I),
    ),
]


def detect_blocker_from_text(text: str) -> Blocker | None:
    """Detect blocker patterns in visible page text."""
    normalized = " ".join((text or "").split())
    if not normalized:
        return None
    for reason, confidence, pattern in _PATTERNS:
        match = pattern.search(normalized)
        if match:
            return Blocker(reason=reason, confidence=confidence, matched=match.group(0))
    return None


def detect_blocker(page: Any) -> Blocker | None:
    """Best-effort blocker detection from a Playwright page.

    Uses visible body text first, then a few common iframe/selectors for CAPTCHA
    widgets. All errors are swallowed so detection never breaks the executor.
    """
    try:
        text = page.locator("body").inner_text(timeout=1500)
    except Exception:
        text = ""

    found = detect_blocker_from_text(text)
    if found:
        return found

    selector_checks = [
        ("captcha_visible", "iframe[src*='recaptcha'], iframe[src*='hcaptcha'], .g-recaptcha, .h-captcha"),
        ("passkey_required", "input[name*='webauthn'], [data-testid*='passkey'], [aria-label*='passkey' i]"),
    ]
    for reason, selector in selector_checks:
        try:
            if page.locator(selector).count() > 0:
                return Blocker(reason=reason, confidence=0.9, matched=selector)
        except Exception:
            continue
    return None
