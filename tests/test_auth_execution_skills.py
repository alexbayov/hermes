from pathlib import Path
import re
import subprocess
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILLS = [
    ROOT / "skills/devops/operator-intent-discipline/SKILL.md",
    ROOT / "skills/devops/critical-input-confirmation/SKILL.md",
    ROOT / "skills/devops/external-auth-discipline/SKILL.md",
    ROOT / "skills/devops/step-journal-verification/SKILL.md",
    ROOT / "skills/devops/telegram-telethon-login/SKILL.md",
]


def parse_frontmatter(path: Path):
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    match = re.search(r"\n---\s*\n", text[4:])
    assert match, f"missing closing frontmatter fence: {path}"
    end = 4 + match.start()
    data = yaml.safe_load(text[4:end])
    assert isinstance(data, dict)
    return data, text[end + len("\n---\n"):]


def test_auth_execution_skills_have_valid_frontmatter():
    for path in SKILLS:
        data, body = parse_frontmatter(path)
        assert data.get("name")
        assert data.get("description")
        assert len(data["description"]) <= 1024
        assert data.get("version")
        assert data.get("metadata", {}).get("hermes", {}).get("tags")
        assert body.strip()


def test_telegram_skill_encodes_required_stop_rules():
    text = (ROOT / "skills/devops/telegram-telethon-login/SKILL.md").read_text(encoding="utf-8")
    required = [
        "Telethon/Pyrogram require `api_id` and `api_hash`",
        "Web Telegram / QR login is a different method",
        "At most one send-code attempt",
        "Reject masked values",
        "Not switching to: web.telegram.org, QR, my.telegram.org",
    ]
    for phrase in required:
        assert phrase in text


def test_behavior_exams_include_auth_manual_replay():
    text = (ROOT / "docs/behavior-exams.md").read_text(encoding="utf-8")
    assert "Auth method lock" in text
    assert "Critical auth input confirmation" in text
    assert "Operator stop halts auth/tool execution" in text


def test_step_journal_skill_requires_evidence_and_postconditions():
    text = (ROOT / "skills/devops/step-journal-verification/SKILL.md").read_text(encoding="utf-8")
    for phrase in [
        "intent",
        "preconditions",
        "evidence",
        "postcondition",
        "uncertain → STOP",
        "absence of an error",
    ]:
        assert phrase in text


def test_profile_patch_installer_is_idempotent(tmp_path):
    script = ROOT / "scripts/install_auth_discipline_profile_patch.py"
    profile = tmp_path / "SOUL.md"
    profile.write_text("# Voice\n\nExisting profile.\n", encoding="utf-8")

    subprocess.run(
        [sys.executable, str(script), "--profile", str(profile)],
        check=True,
        text=True,
        capture_output=True,
    )
    first = profile.read_text(encoding="utf-8")
    assert "Execution discipline for external-auth/account tasks" in first
    assert "Journal fragile steps" in first

    second = subprocess.run(
        [sys.executable, str(script), "--profile", str(profile)],
        check=True,
        text=True,
        capture_output=True,
    )
    assert "already present" in second.stdout
    assert profile.read_text(encoding="utf-8") == first
