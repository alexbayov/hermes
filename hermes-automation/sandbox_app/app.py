"""Hermetic golden flow sandbox app for automation testing.

Provides: signup → email verification → onboarding → success.
Uses a fake email queue (list) for verification link delivery.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

from flask import Flask, redirect, render_template_string, request, url_for

app = Flask(__name__)

# ── Fake email store ─────────────────────────────────────────────────────────

_registration: dict | None = None
_verified: bool = False
_onboarding_complete: bool = False


def reset_state() -> None:
    """Reset all state for a fresh test run."""
    global _registration, _verified, _onboarding_complete
    _registration = None
    _verified = False
    _onboarding_complete = False


# ── Templates ────────────────────────────────────────────────────────────────

SIGNUP_HTML = """<!DOCTYPE html>
<html>
<head><title>Sign Up — Golden Flow</title></head>
<body>
  <h1>Create your account</h1>

  <div class="cookie-banner">
    <p>We use cookies.</p>
    <button role="button" name="Accept all cookies">Accept all cookies</button>
  </div>

  <form method="POST" action="/signup">
    <label>Email <input type="email" name="email" required /></label><br/>
    <button type="submit" name="Continue">Continue</button>
  </form>
</body>
</html>"""

CHECK_EMAIL_HTML = """<!DOCTYPE html>
<html>
<head><title>Check Your Email</title></head>
<body>
  <h1>Check your email</h1>
  <p>We sent a verification link to {{ email }}.</p>
  <p data-testid="check-email-hint">Check your inbox.</p>
</body>
</html>"""

ONBOARDING_HTML = """<!DOCTYPE html>
<html>
<head><title>Onboarding</title></head>
<body>
  <h1>Complete your profile</h1>
  <form method="POST" action="/onboarding">
    <label>First Name <input type="text" name="first_name" required /></label><br/>
    <label>Last Name <input type="text" name="last_name" required /></label><br/>
    <label>Password <input type="password" name="password" required autocomplete="new-password" /></label><br/>
    <label>
      <input type="checkbox" name="agree_terms" /> I agree to the Terms
    </label><br/>
    <button type="submit" name="Continue">Continue</button>
  </form>
</body>
</html>"""

HOME_HTML = """<!DOCTYPE html>
<html>
<head><title>Home</title></head>
<body>
  <h1>Welcome, {{ first_name }}!</h1>
  <p data-testid="dashboard">Your account is ready.</p>
</body>
</html>"""

# ── Routes ───────────────────────────────────────────────────────────────────


@app.route("/")
def index():
    return redirect("/signup")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    global _registration
    if request.method == "POST":
        _registration = {"email": request.form["email"]}
        return redirect("/check-email")
    return render_template_string(SIGNUP_HTML)


@app.route("/check-email")
def check_email():
    if _registration is None:
        return redirect("/signup")
    return render_template_string(
        CHECK_EMAIL_HTML, email=_registration.get("email", "unknown")
    )


@app.route("/verify")
def verify():
    global _verified
    token = request.args.get("token", "")
    if token == "test-token-123":
        _verified = True
        return redirect("/onboarding")
    return "Invalid token", 400


@app.route("/onboarding", methods=["GET", "POST"])
def onboarding():
    global _onboarding_complete
    if not _verified:
        return redirect("/signup")
    if request.method == "POST":
        global _registration
        _registration["first_name"] = request.form.get("first_name", "")
        _registration["last_name"] = request.form.get("last_name", "")
        _registration["password"] = request.form.get("password", "")
        _onboarding_complete = True
        return redirect("/home")
    return render_template_string(ONBOARDING_HTML)


@app.route("/home")
def home():
    if not _onboarding_complete:
        return redirect("/signup")
    return render_template_string(
        HOME_HTML, first_name=_registration.get("first_name", "User")
    )


@app.route("/reset")
def reset():
    reset_state()
    return "State reset"


# ── Fake email API (simulates Mailpit/Mailhog) ───────────────────────────────


@app.route("/fake-inbox")
def fake_inbox():
    """Return a fake verification email with link."""
    if _registration is None:
        return {"messages": []}
    return {
        "messages": [
            {
                "subject": "Verify your email",
                "body": f'Click here to verify: <a href="{url_for("verify", token="test-token-123", _external=True)}">Verify Email</a>',
                "from": "noreply@goldenflow.test",
            }
        ]
    }


# ── Run ──────────────────────────────────────────────────────────────────────


def run(host: str = "127.0.0.1", port: int = 8080) -> None:
    """Start the sandbox app."""
    reset_state()
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    run()
