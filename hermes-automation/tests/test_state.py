"""Tests for state module (HRM-4)."""
import json
import os
import tempfile
from pathlib import Path

import pytest

from harness.capabilities.state import (
    ConfigMismatchError,
    compute_config_hash,
    is_step_done,
    load_checkpoint,
    reset_checkpoint,
    save_checkpoint,
    validate_resume,
)


@pytest.fixture
def state_dir():
    """Temporary state directory."""
    with tempfile.TemporaryDirectory() as d:
        yield d


def test_compute_config_hash_deterministic():
    """Same config produces same hash."""
    config = {"steps": [{"id": "step1"}, {"id": "step2"}]}
    h1 = compute_config_hash(config)
    h2 = compute_config_hash(config)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_compute_config_hash_different():
    """Different configs produce different hashes."""
    h1 = compute_config_hash({"a": 1})
    h2 = compute_config_hash({"a": 2})
    assert h1 != h2


def test_save_and_load_checkpoint(state_dir):
    """Save checkpoint and load it back."""
    payload = {
        "task_id": "t1",
        "config_hash": "sha256:abc",
        "done_steps": ["step1"],
        "current_step": "step2",
        "data": {"email": "test@test.com"},
    }
    save_checkpoint(state_dir, "t1", payload)
    loaded = load_checkpoint(state_dir, "t1")
    assert loaded is not None
    assert loaded["task_id"] == "t1"
    assert loaded["done_steps"] == ["step1"]
    assert loaded["data"]["email"] == "test@test.com"


def test_load_nonexistent(state_dir):
    """Loading missing checkpoint returns None."""
    assert load_checkpoint(state_dir, "nonexistent") is None


def test_is_step_done():
    """is_step_done correctly checks completed steps."""
    cp = {"done_steps": ["open_start", "submit_email"]}
    assert is_step_done(cp, "open_start") is True
    assert is_step_done(cp, "submit_email") is True
    assert is_step_done(cp, "verify_email") is False


def test_save_checkpoint_atomic(state_dir):
    """Saving over existing checkpoint doesn't corrupt."""
    save_checkpoint(state_dir, "t1", {"done_steps": ["a"]})
    save_checkpoint(state_dir, "t1", {"done_steps": ["a", "b"]})
    loaded = load_checkpoint(state_dir, "t1")
    assert loaded["done_steps"] == ["a", "b"]


def test_validate_resume_no_checkpoint(state_dir):
    """No checkpoint → returns None (fresh start)."""
    result = validate_resume(state_dir, "new_task", "hash123")
    assert result is None


def test_validate_resume_hash_match(state_dir):
    """Matching hash → returns checkpoint."""
    config = {"steps": [{"id": "s1"}]}
    config_hash = compute_config_hash(config)
    save_checkpoint(
        state_dir,
        "t1",
        {"task_id": "t1", "config_hash": config_hash, "done_steps": ["s1"]},
    )
    cp = validate_resume(state_dir, "t1", config_hash)
    assert cp is not None
    assert cp["done_steps"] == ["s1"]


def test_validate_resume_hash_mismatch(state_dir):
    """Mismatched hash → raises ConfigMismatchError."""
    config = {"steps": [{"id": "s1"}]}
    original_hash = compute_config_hash(config)
    save_checkpoint(
        state_dir,
        "t1",
        {"task_id": "t1", "config_hash": original_hash, "done_steps": []},
    )
    with pytest.raises(ConfigMismatchError):
        validate_resume(state_dir, "t1", "different_hash_value")


def test_reset_checkpoint(state_dir):
    """Reset removes checkpoint."""
    save_checkpoint(state_dir, "t1", {"data": "x"})
    assert load_checkpoint(state_dir, "t1") is not None
    reset_checkpoint(state_dir, "t1")
    assert load_checkpoint(state_dir, "t1") is None
