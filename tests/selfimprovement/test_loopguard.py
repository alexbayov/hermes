import asyncio

import pytest

from selfimprovement.loopguard import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    LoopGuard,
    LoopGuardBlocked,
    LoopGuardConfig,
    LoopGuardReason,
    LoopGuardTimeout,
)


def test_repeat_detection_blocks_same_payload():
    guard = LoopGuard(LoopGuardConfig(repeat_limit=3))
    payload = {"tool": "click", "args": {"ref": "e1"}}

    assert guard.record(payload).allowed
    assert guard.record(payload).allowed
    decision = guard.record(payload)

    assert not decision.allowed
    assert decision.reason is LoopGuardReason.REPEAT


def test_cycle_detection_blocks_oscillation():
    guard = LoopGuard(LoopGuardConfig(repeat_limit=99, cycle_length=2, cycle_repeats=3))
    a = {"tool": "click", "args": {"ref": "a"}}
    b = {"tool": "click", "args": {"ref": "b"}}

    for payload in [a, b, a, b, a]:
        assert guard.record(payload).allowed
    decision = guard.record(b)

    assert not decision.allowed
    assert decision.reason is LoopGuardReason.CYCLE


def test_stall_detection_blocks_unchanged_observation():
    guard = LoopGuard(LoopGuardConfig(stall_limit=2, repeat_limit=99))

    assert guard.record({"n": 1}, observation_hash="same").allowed
    assert guard.record({"n": 2}, observation_hash="same").allowed
    decision = guard.record({"n": 3}, observation_hash="same")

    assert not decision.allowed
    assert decision.reason is LoopGuardReason.STALL


def test_mark_progress_resets_stall_counter():
    guard = LoopGuard(LoopGuardConfig(stall_limit=2, repeat_limit=99))

    assert guard.record({"n": 1}, observation_hash="same").allowed
    assert guard.record({"n": 2}, observation_hash="same").allowed
    guard.mark_progress(observation_hash="new")

    assert guard.record({"n": 3}, observation_hash="new").allowed


def test_circuit_breaker_opens_and_half_opens_with_backoff():
    breaker = CircuitBreaker(CircuitBreakerConfig(failure_threshold=2, base_backoff_s=10, max_backoff_s=30))

    assert breaker.allow(now=0)
    breaker.record_failure(now=0)
    assert breaker.state is CircuitState.CLOSED
    breaker.record_failure(now=1)
    assert breaker.state is CircuitState.OPEN
    assert not breaker.allow(now=5)
    assert breaker.allow(now=11)
    assert breaker.state is CircuitState.HALF_OPEN
    breaker.record_success()
    assert breaker.state is CircuitState.CLOSED


def test_circuit_breaker_backoff_grows_after_half_open_failure():
    breaker = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1, base_backoff_s=5, max_backoff_s=20))

    breaker.record_failure(now=0)
    assert breaker.next_attempt_at == 5
    assert breaker.allow(now=5)
    breaker.record_failure(now=5)
    assert breaker.state is CircuitState.OPEN
    assert breaker.next_attempt_at == 15


@pytest.mark.asyncio
async def test_guard_async_runs_successful_operation():
    guard = LoopGuard()

    async def op():
        await asyncio.sleep(0)
        return "ok"

    assert await guard.guard_async({"tool": "noop"}, op) == "ok"


@pytest.mark.asyncio
async def test_guard_async_raises_when_blocked():
    guard = LoopGuard(LoopGuardConfig(repeat_limit=2))
    payload = {"tool": "click", "args": {"ref": "e1"}}

    async def op():  # pragma: no cover - must not run
        return "bad"

    assert guard.record(payload).allowed
    with pytest.raises(LoopGuardBlocked) as excinfo:
        await guard.guard_async(payload, op)
    assert excinfo.value.decision.reason is LoopGuardReason.REPEAT


@pytest.mark.asyncio
async def test_guard_async_timeout_records_failure():
    breaker = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1, base_backoff_s=1))
    guard = LoopGuard(LoopGuardConfig(action_timeout_s=0.01), circuit_breaker=breaker)

    async def op():
        await asyncio.sleep(0.1)

    with pytest.raises(LoopGuardTimeout):
        await guard.guard_async({"tool": "slow"}, op)
    assert breaker.state is CircuitState.OPEN
