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


def _fetch_message_body(cfg: MailConfig, msg_id: str) -> str:
    """Fetch full message body by ID from Mailpit/Mailhog."""
    base_url = f"http://{cfg.host}:{cfg.http_port}"
    detail_url = f"{base_url}/api/v1/message/{msg_id}"
    try:
        req = Request(detail_url, headers={"Accept": "application/json"})
        resp = urlopen(req, timeout=10)
        data = json.loads(resp.read().decode("utf-8"))
        return (data.get("HTML") or data.get("html") or
                data.get("Body") or data.get("body") or
                data.get("Text") or data.get("text") or "")
    except (URLError, json.JSONDecodeError, OSError) as e:
        logger.warning("failed to fetch message body for %s: %s", msg_id, e)
        return ""


def wait_for_message(
    *,
    subject_contains: str | None = None,
    recipient: str | None = None,
    timeout_s: int = 120,
    poll_s: int = 5,
    config_path: str | Path | None = None,
) -> dict | None:
    """Poll Mailpit/Mailhog for a message, fetch full body by ID.

    Args:
        subject_contains: Substring to match in subject.
        recipient: Email address to match in To field.
        timeout_s: Max wait time.
        poll_s: Polling interval.
        config_path: Override provider config.

    Returns:
        Message dict with HTML/Body fields populated, or None on timeout.
    """
    cfg = _load_mail_config(config_path)
    base_url = f"http://{cfg.host}:{cfg.http_port}"
    list_url = f"{base_url}/api/v1/messages"

    deadline = time.time() + timeout_s

    while time.time() < deadline:
        try:
            req = Request(list_url, headers={"Accept": "application/json"})
            resp = urlopen(req, timeout=10)
            data = json.loads(resp.read().decode("utf-8"))

            messages = data.get("messages", data) if isinstance(data, dict) else data
            if isinstance(messages, dict):
                messages = messages.get("messages", [])

            # Sort by date newest first
            if messages and isinstance(messages, list):
                messages = sorted(
                    messages,
                    key=lambda m: m.get("Created", m.get("created", "")),
                    reverse=True,
                )

            for msg in messages:
                # Filter by subject
                subject = msg.get("Subject", msg.get("subject", ""))
                if subject_contains and subject_contains.lower() not in subject.lower():
                    continue

                # Filter by recipient
                if recipient:
                    to_list = msg.get("To", msg.get("to", []))
                    if isinstance(to_list, list):
                        to_addrs = [a.get("Address", a.get("address", "")) for a in to_list]
                    else:
                        to_addrs = [str(to_list)]
                    if not any(recipient.lower() in a.lower() for a in to_addrs):
                        continue

                # Fetch full body
                msg_id = msg.get("ID", msg.get("id", ""))
                if msg_id:
                    full_body = _fetch_message_body(cfg, str(msg_id))
                    msg["HTML"] = full_body
                    msg["Body"] = full_body
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
