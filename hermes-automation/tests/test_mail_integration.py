"""Integration test for mail flow: wait_for_message + extract_link.

HRM-20: Tests the actual HTTP-dependent code path (wait_for_message)
against a mock Mailpit API server.
"""

import json
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import pytest
import yaml

from harness.capabilities.mail import extract_link, wait_for_message


# ── Mock Mailpit API ─────────────────────────────────────────────────────────

@pytest.fixture
def mock_mailpit(tmp_path):
    """Start a mock Mailpit HTTP server on a free port.

    Returns (port, shutdown_event).
    """
    # Write a temporary providers.yaml pointing to the mock
    config_path = tmp_path / "providers.yaml"
    config_path.write_text(
        yaml.dump({
            "mail": {
                "provider": "mailpit",
                "host": "127.0.0.1",
                "http_port": 0,  # will be replaced
                "domain": "test.local",
            }
        })
    )

    class MockHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/api/v1/messages":
                # List endpoint — returns summaries
                body = json.dumps({
                    "messages": [
                        {
                            "ID": "msg-001",
                            "Subject": "Welcome to our service",
                            "Created": "2026-06-02T12:00:00Z",
                            "To": [{"Address": "hermes+abc@test.local"}],
                        },
                        {
                            "ID": "msg-002",
                            "Subject": "Verify your email",
                            "Created": "2026-06-02T12:01:00Z",
                            "To": [{"Address": "qa-user@test.local"}],
                        },
                    ]
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            elif self.path == "/api/v1/message/msg-002":
                # Detail endpoint — full body
                body = json.dumps({
                    "ID": "msg-002",
                    "Subject": "Verify your email",
                    "HTML": '<a href="https://app.test/verify?token=abc123">Click here</a>',
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            elif self.path == "/api/v1/message/msg-001":
                body = json.dumps({
                    "ID": "msg-001",
                    "Subject": "Welcome",
                    "HTML": "No link here.",
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass  # suppress stderr spam

    # Start on port 0 (OS picks free port)
    server = HTTPServer(("127.0.0.1", 0), MockHandler)
    actual_port = server.server_address[1]

    # Update config with actual port
    cfg = yaml.safe_load(config_path.read_text())
    cfg["mail"]["http_port"] = actual_port
    config_path.write_text(yaml.dump(cfg))

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield str(config_path)

    server.shutdown()
    thread.join(timeout=2)


# ── Tests ────────────────────────────────────────────────────────────────────


def test_wait_for_message_with_mock(mock_mailpit):
    """wait_for_message finds the email and fetches full body."""
    msg = wait_for_message(
        subject_contains="Verify your email",
        timeout_s=10,
        poll_s=0.5,
        config_path=mock_mailpit,
    )
    assert msg is not None, "Should find the verification email"
    assert msg["Subject"] == "Verify your email"
    assert "abc123" in msg.get("HTML", ""), "Full body should contain verification link"


def test_wait_for_message_filtered_by_recipient(mock_mailpit):
    """Correct message found when filtering by recipient address."""
    msg = wait_for_message(
        recipient="qa-user@test.local",
        timeout_s=10,
        poll_s=0.5,
        config_path=mock_mailpit,
    )
    assert msg is not None
    assert "qa-user@test.local" in str(msg.get("To", ""))


def test_wait_for_message_no_match(mock_mailpit):
    """Returns None when no message matches subject filter."""
    msg = wait_for_message(
        subject_contains="NonExistentSubject",
        timeout_s=2,
        poll_s=0.5,
        config_path=mock_mailpit,
    )
    assert msg is None


def test_extract_link_from_mock_message(mock_mailpit):
    """Full end-to-end: fetch message + extract link."""
    msg = wait_for_message(
        subject_contains="Verify your email",
        timeout_s=10,
        poll_s=0.5,
        config_path=mock_mailpit,
    )
    assert msg is not None
    link = extract_link(msg, url_contains="verify")
    assert link == "https://app.test/verify?token=abc123"
