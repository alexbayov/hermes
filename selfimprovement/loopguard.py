"""Loop protection and circuit breaker primitives for Hermes self-improvement.

The guard blocks repeated actions, short oscillating cycles, and no-progress
stalls before they burn tool calls. The circuit breaker is time based and uses
exponential backoff plus half-open probes, so transient failures do not disable
self-improvement permanently.
"""

from __future__ import annotations

import asyncio
import time
from collections import Counter, deque
from collections.abc import Awaitable, Callable, Iterable
from enum import StrEnum
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from selfimprovement.observation import DEFAULT_VOLATILE_KEY_PATTERNS, stable_fingerprint

T = TypeVar("T")


class LoopGuardReason(StrEnum):
    """Reason a loop-guard decision was denied."""

    NONE = "none"
    REPEAT = "repeat"
    CYCLE = "cycle"
    STALL = "stall"
    TIMEOUT = "timeout"
    CIRCUIT_OPEN = "circuit_open"


class CircuitState(StrEnum):
    """Circuit breaker state."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class LoopGuardConfig(BaseModel):
    """Configuration for action-fingerprint and stall detection."""

    model_config = ConfigDict(frozen=True)

    window_size: int = Field(default=12, ge=3)
    repeat_limit: int = Field(default=3, ge=2)
    cycle_length: int = Field(default=2, ge=2)
    cycle_repeats: int = Field(default=3, ge=2)
    stall_limit: int = Field(default=3, ge=1)
    min_unique_ratio: float = Field(default=0.34, ge=0.0, le=1.0)
    action_timeout_s: float | None = Field(default=None, gt=0.0)
    volatile_key_patterns: tuple[str, ...] = DEFAULT_VOLATILE_KEY_PATTERNS


class CircuitBreakerConfig(BaseModel):
    """Configuration for exponential-backoff circuit breaking."""

    model_config = ConfigDict(frozen=True)

    failure_threshold: int = Field(default=3, ge=1)
    base_backoff_s: float = Field(default=5.0, gt=0.0)
    max_backoff_s: float = Field(default=300.0, gt=0.0)
    half_open_successes: int = Field(default=1, ge=1)


class LoopGuardDecision(BaseModel):
    """Structured decision returned by LoopGuard."""

    model_config = ConfigDict(frozen=True)

    allowed: bool
    reason: LoopGuardReason = LoopGuardReason.NONE
    message: str = "allowed"
    fingerprint: str | None = None
    observation_hash: str | None = None
    unique_ratio: float | None = None
    circuit_state: CircuitState | None = None
    next_attempt_at: float | None = None


class LoopGuardBlocked(RuntimeError):
    """Raised by guard_async when a planned action is blocked."""

    def __init__(self, decision: LoopGuardDecision) -> None:
        super().__init__(decision.message)
        self.decision = decision


class LoopGuardTimeout(TimeoutError):
    """Raised when a guarded async action exceeds action_timeout_s."""


class CircuitBreaker:
    """Time-based circuit breaker with exponential backoff and half-open probes."""

    def __init__(self, config: CircuitBreakerConfig | None = None) -> None:
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.consecutive_successes = 0
        self.opened_at: float | None = None
        self.next_attempt_at: float | None = None

    def allow(self, *, now: float | None = None) -> bool:
        """Return whether an operation may run at *now*."""

        now = time.monotonic() if now is None else now
        if self.state is CircuitState.CLOSED:
            return True
        if self.state is CircuitState.HALF_OPEN:
            return True
        if self.next_attempt_at is not None and now >= self.next_attempt_at:
            self.state = CircuitState.HALF_OPEN
            self.consecutive_successes = 0
            return True
        return False

    def record_success(self) -> None:
        """Record a successful protected operation."""

        if self.state is CircuitState.HALF_OPEN:
            self.consecutive_successes += 1
            if self.consecutive_successes >= self.config.half_open_successes:
                self.close()
            return
        self.failure_count = 0
        self.consecutive_successes = 0

    def record_failure(self, *, now: float | None = None) -> None:
        """Record a failed protected operation and open the circuit if needed."""

        now = time.monotonic() if now is None else now
        self.failure_count += 1
        self.consecutive_successes = 0
        if self.state is CircuitState.HALF_OPEN or self.failure_count >= self.config.failure_threshold:
            self.open(now=now)

    def open(self, *, now: float | None = None) -> None:
        """Open the circuit and schedule the next half-open probe."""

        now = time.monotonic() if now is None else now
        exponent = max(self.failure_count - self.config.failure_threshold, 0)
        backoff = min(self.config.base_backoff_s * (2**exponent), self.config.max_backoff_s)
        self.state = CircuitState.OPEN
        self.opened_at = now
        self.next_attempt_at = now + backoff

    def close(self) -> None:
        """Close the circuit and reset counters."""

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.consecutive_successes = 0
        self.opened_at = None
        self.next_attempt_at = None


class LoopGuard:
    """Detect repeated actions, cycles, stalls, and circuit-open state."""

    def __init__(
        self,
        config: LoopGuardConfig | None = None,
        *,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self.config = config or LoopGuardConfig()
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self._fingerprints: deque[str] = deque(maxlen=self.config.window_size)
        self._last_observation_hash: str | None = None
        self._stall_count = 0

    def fingerprint(self, payload: Any) -> str:
        """Return the normalized action fingerprint for *payload*."""

        return stable_fingerprint(payload, volatile_key_patterns=self.config.volatile_key_patterns)

    def record(self, payload: Any, *, observation_hash: str | None = None, now: float | None = None) -> LoopGuardDecision:
        """Record a candidate action and return whether it may proceed."""

        if not self.circuit_breaker.allow(now=now):
            return LoopGuardDecision(
                allowed=False,
                reason=LoopGuardReason.CIRCUIT_OPEN,
                message="circuit breaker is open",
                circuit_state=self.circuit_breaker.state,
                next_attempt_at=self.circuit_breaker.next_attempt_at,
            )

        fingerprint = self.fingerprint(payload)
        sequence = [*self._fingerprints, fingerprint]
        unique_ratio = len(set(sequence)) / len(sequence)

        if Counter(sequence)[fingerprint] >= self.config.repeat_limit:
            return LoopGuardDecision(
                allowed=False,
                reason=LoopGuardReason.REPEAT,
                message=f"action fingerprint {fingerprint} repeated {self.config.repeat_limit} times",
                fingerprint=fingerprint,
                observation_hash=observation_hash,
                unique_ratio=unique_ratio,
                circuit_state=self.circuit_breaker.state,
            )

        cycle_reason = self._detect_cycle(sequence)
        if cycle_reason is not None:
            return LoopGuardDecision(
                allowed=False,
                reason=LoopGuardReason.CYCLE,
                message=cycle_reason,
                fingerprint=fingerprint,
                observation_hash=observation_hash,
                unique_ratio=unique_ratio,
                circuit_state=self.circuit_breaker.state,
            )

        if observation_hash is not None and observation_hash == self._last_observation_hash:
            self._stall_count += 1
        else:
            self._stall_count = 0
        self._last_observation_hash = observation_hash

        if self._stall_count >= self.config.stall_limit:
            return LoopGuardDecision(
                allowed=False,
                reason=LoopGuardReason.STALL,
                message="environment observation did not change after repeated actions",
                fingerprint=fingerprint,
                observation_hash=observation_hash,
                unique_ratio=unique_ratio,
                circuit_state=self.circuit_breaker.state,
            )

        if len(sequence) >= self.config.window_size and unique_ratio < self.config.min_unique_ratio:
            return LoopGuardDecision(
                allowed=False,
                reason=LoopGuardReason.REPEAT,
                message=f"recent action diversity too low: unique_ratio={unique_ratio:.2f}",
                fingerprint=fingerprint,
                observation_hash=observation_hash,
                unique_ratio=unique_ratio,
                circuit_state=self.circuit_breaker.state,
            )

        self._fingerprints.append(fingerprint)
        return LoopGuardDecision(
            allowed=True,
            fingerprint=fingerprint,
            observation_hash=observation_hash,
            unique_ratio=unique_ratio,
            circuit_state=self.circuit_breaker.state,
        )

    def mark_progress(self, *, observation_hash: str | None = None) -> None:
        """Reset stall state after externally confirmed progress."""

        self._stall_count = 0
        if observation_hash is not None:
            self._last_observation_hash = observation_hash

    async def guard_async(
        self,
        payload: Any,
        coro_factory: Callable[[], Awaitable[T]],
        *,
        observation_hash: str | None = None,
    ) -> T:
        """Guard and run an async operation.

        Raises LoopGuardBlocked when the action is denied and LoopGuardTimeout
        when the operation exceeds the configured timeout.
        """

        decision = self.record(payload, observation_hash=observation_hash)
        if not decision.allowed:
            self.circuit_breaker.record_failure()
            raise LoopGuardBlocked(decision)

        try:
            if self.config.action_timeout_s is None:
                result = await coro_factory()
            else:
                result = await asyncio.wait_for(coro_factory(), timeout=self.config.action_timeout_s)
        except TimeoutError as exc:
            self.circuit_breaker.record_failure()
            raise LoopGuardTimeout(f"guarded action timed out after {self.config.action_timeout_s}s") from exc
        except Exception:
            self.circuit_breaker.record_failure()
            raise
        else:
            self.circuit_breaker.record_success()
            return result

    def _detect_cycle(self, sequence: Iterable[str]) -> str | None:
        seq = list(sequence)
        block_len = self.config.cycle_length
        repeats = self.config.cycle_repeats
        needed = block_len * repeats
        if len(seq) < needed:
            return None
        tail = seq[-needed:]
        block = tail[:block_len]
        if all(tail[i : i + block_len] == block for i in range(0, needed, block_len)):
            return f"cycle detected: block of {block_len} actions repeated {repeats} times"
        return None


__all__ = [
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitState",
    "LoopGuard",
    "LoopGuardBlocked",
    "LoopGuardConfig",
    "LoopGuardDecision",
    "LoopGuardReason",
    "LoopGuardTimeout",
]
