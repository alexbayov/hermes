"""Hermes self-improvement package.

Phase 1 exports observation persistence and loop-guard primitives only.
"""

from selfimprovement.loopguard import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    LoopGuard,
    LoopGuardBlocked,
    LoopGuardConfig,
    LoopGuardDecision,
    LoopGuardReason,
    LoopGuardTimeout,
)
from selfimprovement.observation import (
    JsonlIntegrityError,
    JsonlObservationSink,
    Observation,
    ObservationIntegrityError,
    ObservationRecorder,
    SecretRedactor,
    SQLiteObservationStore,
    stable_fingerprint,
)

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitState",
    "JsonlIntegrityError",
    "JsonlObservationSink",
    "LoopGuard",
    "LoopGuardBlocked",
    "LoopGuardConfig",
    "LoopGuardDecision",
    "LoopGuardReason",
    "LoopGuardTimeout",
    "Observation",
    "ObservationIntegrityError",
    "ObservationRecorder",
    "SecretRedactor",
    "SQLiteObservationStore",
    "stable_fingerprint",
]
