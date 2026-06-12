"""Deterministic assessment for Hermes self-improvement Phase 2.

This module scores observations and identifies one concrete bottleneck. It does
not modify code, write patches, or execute strategies. Later phases can consume
AssessmentResult objects as read-only planning input.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from selfimprovement.observation import Observation


class AssessmentCategory(StrEnum):
    """Primary bottleneck category detected from an observation."""

    HEALTHY = "healthy"
    LATENCY_REGRESSION = "latency_regression"
    INTENT_DRIFT = "intent_drift"
    TOOL_RETRY_LOOP = "tool_retry_loop"
    VALIDATION_FAILURE = "validation_failure"
    LOW_INFORMATION_OUTPUT = "low_information_output"
    MISSING_PERSISTENCE = "missing_persistence"
    UNKNOWN = "unknown"


class AssessmentSeverity(StrEnum):
    """Severity level derived from quality score and risk signals."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class BaselineMetrics(BaseModel):
    """Historical baseline for a comparable task family."""

    model_config = ConfigDict(frozen=True)

    latency_ms_p50: int | None = Field(default=None, ge=0)
    latency_ms_p95: int | None = Field(default=None, ge=0)
    retry_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    error_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    intent_drift_avg: float | None = Field(default=None, ge=0.0, le=1.0)
    quality_score_avg: float | None = Field(default=None, ge=0.0, le=1.0)
    sample_size: int = Field(default=0, ge=0)


class AssessmentConfig(BaseModel):
    """Thresholds and weights for deterministic quality assessment."""

    model_config = ConfigDict(frozen=True)

    latency_regression_factor: float = Field(default=1.75, gt=1.0)
    absolute_latency_ms: int = Field(default=30_000, ge=1)
    retry_loop_threshold: int = Field(default=2, ge=1)
    intent_drift_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    low_output_tokens_threshold: int = Field(default=20, ge=0)
    minimum_quality_score: float = Field(default=0.72, ge=0.0, le=1.0)


class AssessmentResult(BaseModel):
    """Assessment output consumed by strategy generation."""

    model_config = ConfigDict(frozen=True)

    observation_id: str
    category: AssessmentCategory
    severity: AssessmentSeverity
    quality_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    expected_impact: float = Field(ge=0.0, le=1.0)
    bottleneck: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    needs_strategy: bool = False

    @field_validator("bottleneck")
    @classmethod
    def _non_empty_bottleneck(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("bottleneck must not be empty")
        return value


class QualityAssessor:
    """Deterministic observation scorer.

    The assessor intentionally emits one primary bottleneck. If several signals
    are bad, the highest-priority operational failure wins: errors, retries,
    drift, latency, low output, then missing persistence.
    """

    def __init__(self, config: AssessmentConfig | None = None) -> None:
        self.config = config or AssessmentConfig()

    def assess(self, observation: Observation, baseline: BaselineMetrics | None = None) -> AssessmentResult:
        """Assess one observation against an optional historical baseline."""

        baseline = baseline or BaselineMetrics()
        evidence = self._collect_evidence(observation, baseline)
        category, bottleneck = self._select_category(observation, baseline, evidence)
        quality_score = observation.quality_score if observation.quality_score is not None else self._score(category, evidence)
        severity = self._severity(category, quality_score)
        confidence = self._confidence(category, evidence, baseline)
        expected_impact = self._expected_impact(category, severity, evidence)

        return AssessmentResult(
            observation_id=observation.id,
            category=category,
            severity=severity,
            quality_score=quality_score,
            confidence=confidence,
            expected_impact=expected_impact,
            bottleneck=bottleneck,
            evidence=evidence,
            needs_strategy=category is not AssessmentCategory.HEALTHY or quality_score < self.config.minimum_quality_score,
        )

    def _collect_evidence(self, observation: Observation, baseline: BaselineMetrics) -> dict[str, Any]:
        latency_ratio = None
        if observation.latency_ms is not None and baseline.latency_ms_p50:
            latency_ratio = observation.latency_ms / max(baseline.latency_ms_p50, 1)

        return {
            "event_type": observation.event_type,
            "latency_ms": observation.latency_ms,
            "baseline_latency_ms_p50": baseline.latency_ms_p50,
            "latency_ratio": latency_ratio,
            "retry_count": observation.retry_count,
            "error_count": observation.error_count,
            "intent_drift": observation.intent_drift,
            "output_tokens": observation.output_tokens,
            "quality_score": observation.quality_score,
            "has_context_fingerprint": bool(observation.context_fingerprint),
            "baseline_sample_size": baseline.sample_size,
        }

    def _select_category(
        self,
        observation: Observation,
        baseline: BaselineMetrics,
        evidence: dict[str, Any],
    ) -> tuple[AssessmentCategory, str]:
        if observation.error_count > 0:
            return AssessmentCategory.VALIDATION_FAILURE, "observation contains runtime or validation errors"

        if observation.retry_count >= self.config.retry_loop_threshold:
            return AssessmentCategory.TOOL_RETRY_LOOP, "tool retries exceeded the loop-risk threshold"

        if observation.intent_drift is not None and observation.intent_drift >= self.config.intent_drift_threshold:
            return AssessmentCategory.INTENT_DRIFT, "observed intent drift exceeded threshold"

        latency_ratio = evidence.get("latency_ratio")
        if latency_ratio is not None and latency_ratio >= self.config.latency_regression_factor:
            return AssessmentCategory.LATENCY_REGRESSION, "latency regressed against baseline"

        if observation.latency_ms is not None and observation.latency_ms >= self.config.absolute_latency_ms:
            return AssessmentCategory.LATENCY_REGRESSION, "absolute latency exceeded threshold"

        if observation.output_tokens is not None and observation.output_tokens <= self.config.low_output_tokens_threshold and observation.error_count == 0:
            return AssessmentCategory.LOW_INFORMATION_OUTPUT, "response/output was too small to be useful"

        if not observation.context_fingerprint and observation.payload:
            return AssessmentCategory.MISSING_PERSISTENCE, "payload was present but no context fingerprint was stored"

        return AssessmentCategory.HEALTHY, "no material bottleneck detected"

    def _score(self, category: AssessmentCategory, evidence: dict[str, Any]) -> float:
        score = 1.0
        score -= min(evidence.get("error_count") or 0, 3) * 0.20
        score -= min(evidence.get("retry_count") or 0, 5) * 0.08
        score -= min(evidence.get("intent_drift") or 0.0, 1.0) * 0.30
        latency_ratio = evidence.get("latency_ratio")
        if latency_ratio is not None and latency_ratio > 1.0:
            score -= min((latency_ratio - 1.0) * 0.10, 0.25)
        if category is AssessmentCategory.LOW_INFORMATION_OUTPUT:
            score -= 0.15
        if category is AssessmentCategory.MISSING_PERSISTENCE:
            score -= 0.10
        return max(0.0, min(1.0, score))

    def _severity(self, category: AssessmentCategory, quality_score: float) -> AssessmentSeverity:
        if category is AssessmentCategory.HEALTHY and quality_score >= self.config.minimum_quality_score:
            return AssessmentSeverity.INFO
        if quality_score < 0.45 or category in {AssessmentCategory.VALIDATION_FAILURE, AssessmentCategory.TOOL_RETRY_LOOP}:
            return AssessmentSeverity.HIGH
        if quality_score < 0.65 or category in {AssessmentCategory.INTENT_DRIFT, AssessmentCategory.LATENCY_REGRESSION}:
            return AssessmentSeverity.MEDIUM
        return AssessmentSeverity.LOW

    def _confidence(self, category: AssessmentCategory, evidence: dict[str, Any], baseline: BaselineMetrics) -> float:
        if category is AssessmentCategory.HEALTHY:
            return 0.70 if baseline.sample_size else 0.50
        confidence = 0.55
        if baseline.sample_size >= 20:
            confidence += 0.20
        elif baseline.sample_size >= 5:
            confidence += 0.10
        if category in {AssessmentCategory.VALIDATION_FAILURE, AssessmentCategory.TOOL_RETRY_LOOP}:
            confidence += 0.20
        if evidence.get("latency_ratio") is not None:
            confidence += 0.10
        return max(0.0, min(1.0, confidence))

    def _expected_impact(self, category: AssessmentCategory, severity: AssessmentSeverity, evidence: dict[str, Any]) -> float:
        if category is AssessmentCategory.HEALTHY:
            return 0.0
        base = {
            AssessmentSeverity.LOW: 0.30,
            AssessmentSeverity.MEDIUM: 0.55,
            AssessmentSeverity.HIGH: 0.80,
            AssessmentSeverity.INFO: 0.0,
        }[severity]
        if category is AssessmentCategory.TOOL_RETRY_LOOP:
            base += 0.10
        if category is AssessmentCategory.VALIDATION_FAILURE:
            base += 0.05
        return max(0.0, min(1.0, base))


__all__ = [
    "AssessmentCategory",
    "AssessmentConfig",
    "AssessmentResult",
    "AssessmentSeverity",
    "BaselineMetrics",
    "QualityAssessor",
]
