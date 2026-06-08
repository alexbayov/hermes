"""Auto-commit skill changes and push to origin/main."""
import os
import sys
import subprocess
import re
from datetime import datetime

REPO_DIR = "/root/.hermes"
SAFE_PATHS = [
    r"^skills/",
    r"^\.gitignore$",
    r"^plans/",
    r"^scripts/",
    r"^data/backup/",
    r"^\.env\.template$",
]

RUNTIME_PATHS = [
    r"^logs/",
    r"^cache/",
    r"^lsp/",
    r"^state\.db",
    r"^response_store\.db",
    r"^\.tirith-install-failed",
    r"^kanban\.db",
    r"^gateway\.lock",
    r"^gateway\.pid",
    r"^\.skills_prompt_snapshot\.json",
]


def _run(cmd: list, cwd: str = REPO_DIR) -> str:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"ERROR: {' '.join(cmd)}\n{r.stderr}", file=sys.stderr)
        return ""
    return r.stdout.strip()


def _is_safe(path: str) -> bool:
    for pat in SAFE_PATHS:
        if re.search(pat, path):
            return True
    for pat in RUNTIME_PATHS:
        if re.search(pat, path):
            return False
    return False


def auto_commit(dry_run: bool = False, push: bool = True) -> bool:
    os.chdir(REPO_DIR)

    status = _run(["git", "status", "--short"])
    if not status:
        print("Nothing to commit")
        return False

    lines = status.splitlines()
    safe_files = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) < 2:
            continue
        path = parts[1].strip()
        if _is_safe(path):
            safe_files.append(path)
        else:
            print(f"  SKIP (runtime): {path}")

    if not safe_files:
        print("No safe files to commit")
        return False

    # Group by skill directory for commit message
    skill_dirs = set()
    for f in safe_files:
        m = re.match(r"skills/([^/]+)/", f)
        if m:
            skill_dirs.add(m.group(1))

    scope = ",".join(sorted(skill_dirs)) if skill_dirs else "repo"
    msg = f"auto({scope}): update {len(safe_files)} file(s) at {datetime.utcnow().strftime('%H:%M')}"

    if dry_run:
        print(f"DRY-RUN: would commit {len(safe_files)} files\n  message: {msg}")
        for f in safe_files:
            print(f"    {f}")
        return False

    _run(["git", "add"] + safe_files)
    _run(["git", "commit", "-m", msg])
    print(f"Committed: {msg}")

    if push:
        out = _run(["git", "push", "origin", "main"])
        if out:
            print(f"Pushed: {out}")
        else:
            print("WARNING: push failed", file=sys.stderr)

    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-push", action="store_true")
    args = parser.parse_args()
    auto_commit(dry_run=args.dry_run, push=not args.no_push)
