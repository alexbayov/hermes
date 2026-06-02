"""State management: checkpoints, config hash, atomic writes.

HRM-4: Atomic checkpoint saves with config hash for safe resume.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ConfigMismatchError(Exception):
    """Current YAML config hash doesn't match the checkpoint hash."""


class StateError(Exception):
    """Base error for state module."""


def compute_config_hash(site_config: dict) -> str:
    """Compute deterministic SHA-256 hash of normalized config.

    Normalizes keys to strings and sorts them for stability.
    """
    normalized = _normalize_for_hash(site_config)
    canonical = json.dumps(normalized, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_for_hash(obj: Any) -> Any:
    """Recursively normalize for deterministic hashing."""
    if isinstance(obj, dict):
        return {str(k): _normalize_for_hash(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_for_hash(v) for v in obj]
    if isinstance(obj, (int, float)):
        return obj
    if isinstance(obj, bool):
        return obj
    if obj is None:
        return None
    return str(obj)


def save_checkpoint(
    state_dir: str | Path,
    task_id: str,
    payload: dict,
) -> None:
    """Atomically save checkpoint to state_dir/<task_id>.json.

    Writes to temp file, fsync, then atomic rename.
    Kill during write won't corrupt previous checkpoint.
    """
    state_path = Path(state_dir)
    state_path.mkdir(parents=True, exist_ok=True)

    target = state_path / f"{task_id}.json"
    tmp = state_path / f"{task_id}.tmp"

    payload.setdefault("updated_at", datetime.now(timezone.utc).isoformat())

    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())

    os.replace(tmp, target)


def load_checkpoint(state_dir: str | Path, task_id: str) -> dict | None:
    """Load checkpoint or None if not found/corrupted."""
    target = Path(state_dir) / f"{task_id}.json"
    if not target.exists():
        return None
    try:
        with open(target, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        # Save corrupted copy for diagnostics
        corrupted = Path(state_dir) / f"{task_id}.corrupted.json"
        shutil.copy2(target, corrupted)
        return None


def is_step_done(checkpoint: dict, step_id: str) -> bool:
    """Check if a step is marked as done in the checkpoint."""
    return step_id in checkpoint.get("done_steps", [])


def validate_resume(
    state_dir: str | Path,
    task_id: str,
    current_config_hash: str,
) -> dict | None:
    """Load checkpoint and validate config hash for safe resume.

    Returns checkpoint dict if safe to resume, None if no checkpoint exists.
    Raises ConfigMismatchError if hash changed.
    """
    checkpoint = load_checkpoint(state_dir, task_id)
    if checkpoint is None:
        return None

    stored_hash = checkpoint.get("config_hash", "")
    if stored_hash and stored_hash != current_config_hash:
        raise ConfigMismatchError(
            f"Config hash mismatch for task '{task_id}': "
            f"stored={stored_hash[:12]}... current={current_config_hash[:12]}... "
            f"Use --reset to start over or update the config."
        )

    return checkpoint


def reset_checkpoint(state_dir: str | Path, task_id: str) -> None:
    """Remove checkpoint and temp file for a task."""
    state_path = Path(state_dir)
    for suffix in (".json", ".tmp", ".corrupted.json"):
        f = state_path / f"{task_id}{suffix}"
        if f.exists():
            f.unlink()
