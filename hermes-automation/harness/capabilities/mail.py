"""Mail capability — single provider (Mailpit/Mailhog catch-all).

HRM-20: Agent has NO choice of provider. get_inbox() returns the configured
mailbox. Address is synthesized locally (catch-all), API only for reading.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

import yaml

logger = logging.getLogger("hermes.mail")

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "providers.yaml"

# ── Provider Config ──────────────────────────────────────────────────────────


@dataclass
class MailConfig:
    provider: str
    host: str
    http_port: int
    domain: str


def _load_mail_config(config_path: str | Path | None = None) -> MailConfig:
    """Load mail config from providers.yaml. Raises if not configured."""
    path = Path(config_path or DEFAULT_CONFIG_PATH)
    if not path.exists():
        raise RuntimeError(f"Provider config not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    mail = cfg.get("mail")
    if not mail:
        raise RuntimeError("No 'mail' section in provider config")

    return MailConfig(
        provider=mail.get("provider", "mailpit"),
        host=mail.get("host", "127.0.0.1"),
        http_port=mail.get("http_port", 8025),
        domain=mail.get("domain", "test.local"),
    )


# ── Public API ───────────────────────────────────────────────────────────────


def get_email_address(config_path: str | Path | None = None) -> str:
    """Synthesize a unique catch-all address — no API call needed.

    Mailpit/Mailhog accept any address @domain → all mail lands in one inbox.
    """
    cfg = _load_mail_config(config_path)
    local_part = f"hermes+{uuid.uuid4().hex[:8]}"
    return f"{local_part}@{cfg.domain}"


def get_inbox(config_path: str | Path | None = None) -> MailConfig:
    """Return the configured mailbox. Agent uses this, never another service."""
    return _load_mail_config(config_path)


def wait_for_message(
    *,
    subject_contains: str | None = None,
    timeout_s: int = 120,
    poll_s: int = 5,
    config_path: str | Path | None = None,
) -> dict | None:
    """Poll Mailpit/Mailhog API for a message matching criteria.

    Returns the first matching message or None on timeout.
    """
    cfg = _load_mail_config(config_path)
    base_url = f"http://{cfg.host}:{cfg.http_port}"
    api_url = f"{base_url}/api/v1/messages"

    deadline = time.time() + timeout_s

    while time.time() < deadline:
        try:
            req = Request(api_url, headers={"Accept": "application/json"})
            resp = urlopen(req, timeout=10)
            data = json.loads(resp.read().decode("utf-8"))

            messages = data.get("messages", data) if isinstance(data, dict) else data
            if isinstance(messages, dict):
                messages = messages.get("messages", [])

            for msg in messages:
                subject = msg.get("Subject", msg.get("subject", ""))
                if subject_contains and subject_contains.lower() not in subject.lower():
                    continue
                return msg

        except (URLError, json.JSONDecodeError, OSError) as e:
            logger.debug("mail poll error: %s", e)

        time.sleep(poll_s)

    return None


def extract_link(
    message: dict,
    *,
    url_contains: str | None = None,
) -> str | None:
    """Extract a verification link from an email body."""
    body = message.get("Body", message.get("body", ""))
    html = message.get("HTML", message.get("html", ""))
    text = html or body or ""

    # Find all hrefs
    hrefs = re.findall(r'href=["\']?(https?://[^\s"\'<>]+)["\']?', text)
    for href in hrefs:
        if url_contains is None or url_contains in href:
            return href

    # Fallback: plain URLs in text
    urls = re.findall(r'https?://[^\s<>"\']+', text)
    for url in urls:
        if url_contains is None or url_contains in url:
            return url.rstrip(".,;)" )

    return None
