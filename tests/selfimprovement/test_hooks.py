"""Smoke tests for selfimprovement/hooks.py."""

from selfimprovement import hooks as si
from selfimprovement.assessment import AssessmentCategory
from selfimprovement.loopguard import LoopGuardConfig, LoopGuardBlocked


def test_hooks_session_records_observation(tmp_path):
    sess = si.session(
        db_path=tmp_path / "obs.sqlite3",
        jsonl_path=tmp_path / "obs.jsonl",
    )
    sess.before_step("terminal", {"command": "echo hello"})
    obs = sess.after_step("hello", latency_ms=50)

    assert obs.event_type == "tool:terminal"
    assert obs.latency_ms == 50
    assert obs.payload["payload"] == {"command": "echo hello"}
    assert obs.payload["result_summary"] == "hello"


def test_hooks_end_turn_returns_assessment(tmp_path):
    sess = si.session(
        db_path=tmp_path / "obs.sqlite3",
        jsonl_path=tmp_path / "obs.jsonl",
    )
    sess.before_step("terminal", {"command": "echo hello"})
    sess.after_step("hello", latency_ms=50)
    report = sess.end_turn()

    assert report is not None
    assert report.status.value == "passed"
    assert report.assessment is not None


def test_hooks_loop_guard_blocks_repeat(tmp_path):
    sess = si.session(
        db_path=tmp_path / "obs.sqlite3",
        jsonl_path=tmp_path / "obs.jsonl",
        loop_guard=si.LoopGuard(LoopGuardConfig(repeat_limit=3)),
    )
    payload = {"tool": "click", "args": {"ref": "e1"}}

    sess.before_step("click", payload)
    sess.after_step("ok")
    sess.before_step("click", payload)
    sess.after_step("ok")

    try:
        sess.before_step("click", payload)
        assert False, "should raise"
    except si.LoopGuardBlocked:
        pass
