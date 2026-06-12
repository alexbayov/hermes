"""Strategy generation for Hermes self-improvement Phase 2.

Strategies are proposals only. They contain no patches and cannot mutate the
repository or runtime. Later phases may add modification and validation, but this
module remains a deterministic planning layer.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from selfimprovement.assessment import AssessmentCategory, AssessmentResult, AssessmentSeverity


class RiskLevel(StrEnum):
    """Risk level for a proposed improvement strategy."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class StrategyAction(BaseModel):
    """One bounded, non-mutating action inside a strategy."""

    model_config = ConfigDict(frozen=True)

    description: str
    phase: str = "analysis"
    mutates_code: bool = False
    requires_human_approval: bool = False

    @field_validator("description", "phase")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class ImprovementStrategy(BaseModel):
    """A read-only improvement proposal derived from an assessment."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: uuid4().hex)
    assessment_id: str
    category: AssessmentCategory
    title: str
    rationale: str
    actions: tuple[StrategyAction, ...]
    expected_impact: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    effort: float = Field(gt=0.0, le=10.0)
    risk: RiskLevel = RiskLevel.LOW
    dry_run_only: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @computed_field
    @property
    def priority(self) -> float:
        """Priority score: expected impact times confidence divided by effort."""

        return round((self.expected_impact * self.confidence) / max(self.effort, 0.1), 4)

    @computed_field
    @property
    def can_auto_apply(self) -> bool:
        """Phase 2 strategies are never auto-applied."""

        return False

    @field_validator("title", "rationale")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("actions")
    @classmethod
    def _actions_non_empty_and_non_mutating(cls, value: tuple[StrategyAction, ...]) -> tuple[StrategyAction, ...]:
        if not value:
            raise ValueError("strategy must contain at least one action")
        if any(action.mutates_code for action in value):
            raise ValueError("Phase 2 strategies must not mutate code")
        return value


class StrategyGeneratorConfig(BaseModel):
    """Configuration for deterministic strategy generation."""

    model_config = ConfigDict(frozen=True)

    max_strategies: int = Field(default=3, ge=1, le=10)
    min_expected_impact: float = Field(default=0.05, ge=0.0, le=1.0)
    max_autonomous_risk: RiskLevel = RiskLevel.LOW


class StrategyGenerator:
    """Generate bounded dry-run strategies from assessment results."""

    def __init__(self, config: StrategyGeneratorConfig | None = None) -> None:
        self.config = config or StrategyGeneratorConfig()

    def generate(self, assessment: AssessmentResult) -> list[ImprovementStrategy]:
        """Return ranked, non-mutating strategies for *assessment*."""

        if not assessment.needs_strategy or assessment.expected_impact < self.config.min_expected_impact:
            return []

        candidates = self._candidate_templates(assessment)
        candidates.sort(key=lambda strategy: strategy.priority, reverse=True)
        return candidates[: self.config.max_strategies]

    def _candidate_templates(self, assessment: AssessmentResult) -> list[ImprovementStrategy]:
        category = assessment.category
        if category is AssessmentCategory.TOOL_RETRY_LOOP:
            return [self._retry_loop_strategy(assessment), self._instrumentation_strategy(assessment)]
        if category is AssessmentCategory.INTENT_DRIFT:
            return [self._intent_drift_strategy(assessment), self._instrumentation_strategy(assessment)]
        if category is AssessmentCategory.LATENCY_REGRESSION:
            return [self._latency_strategy(assessment), self._instrumentation_strategy(assessment)]
        if category is AssessmentCategory.VALIDATION_FAILURE:
            return [self._validation_failure_strategy(assessment), self._instrumentation_strategy(assessment)]
        if category is AssessmentCategory.LOW_INFORMATION_OUTPUT:
            return [self._low_information_strategy(assessment), self._instrumentation_strategy(assessment)]
        if category is AssessmentCategory.MISSING_PERSISTENCE:
            return [self._persistence_strategy(assessment), self._instrumentation_strategy(assessment)]
        return [self._instrumentation_strategy(assessment)]

    def _base(self, assessment: AssessmentResult, *, title: str, rationale: str, actions: list[str], effort: float, risk: RiskLevel = RiskLevel.LOW) -> ImprovementStrategy:
        return ImprovementStrategy(
            assessment_id=assessment.observation_id,
            category=assessment.category,
            title=title,
            rationale=rationale,
            actions=tuple(StrategyAction(description=action) for action in actions),
            expected_impact=assessment.expected_impact,
            confidence=assessment.confidence,
            effort=effort,
            risk=risk,
            dry_run_only=True,
            metadata={"severity": assessment.severity.value, "bottleneck": assessment.bottleneck},
        )

    def _retry_loop_strategy(self, assessment: AssessmentResult) -> ImprovementStrategy:
        return self._base(
            assessment,
            title="Tighten loopguard thresholds for repeated tool calls",
            rationale="The assessment indicates retry-loop behavior. Phase 2 can only propose threshold/config changes, not apply them.",
            actions=[
                "Inspect recent action fingerprints for identical payload repetition",
                "Lower repeat_limit or stall_limit for the affected task family in a draft config proposal",
                "Add a dry-run alert when retry_count crosses the observed threshold",
            ],
            effort=1.5,
        )

    def _intent_drift_strategy(self, assessment: AssessmentResult) -> ImprovementStrategy:
        return self._base(
            assessment,
            title="Add intent-drift checkpoint before tool execution",
            rationale="The observation drifted from the requested task. The safest response is an explicit dry-run checkpoint before more actions.",
            actions=[
                "Record the user goal fingerprint and compare it with the planned tool action",
                "Emit a dry-run warning when intent_drift exceeds the configured threshold",
                "Require an explicit plan refresh for the next step after drift is detected",
            ],
            effort=2.0,
        )

    def _latency_strategy(self, assessment: AssessmentResult) -> ImprovementStrategy:
        return self._base(
            assessment,
            title="Profile latency regression before changing execution",
            rationale="The observation is slower than baseline. Phase 2 should isolate whether delay comes from tools, retries, or model output length.",
            actions=[
                "Split latency into tool time, model time, and persistence time in future observations",
                "Compare latency against p50 and p95 baseline for the same event_type",
                "Generate a dry-run recommendation only after at least five comparable samples",
            ],
            effort=2.5,
        )

    def _validation_failure_strategy(self, assessment: AssessmentResult) -> ImprovementStrategy:
        return self._base(
            assessment,
            title="Quarantine failing validation path before modification work",
            rationale="The observation contains a failure. Later phases must validate and rollback before any modification is considered.",
            actions=[
                "Classify the failure as test, compile, runtime, persistence, or external-tool failure",
                "Add the failing observation id to the Phase 3 validation backlog",
                "Keep modification disabled until validation can reproduce the failure deterministically",
            ],
            effort=2.0,
            risk=RiskLevel.MEDIUM if assessment.severity is AssessmentSeverity.HIGH else RiskLevel.LOW,
        )

    def _low_information_strategy(self, assessment: AssessmentResult) -> ImprovementStrategy:
        return self._base(
            assessment,
            title="Require minimum useful output evidence",
            rationale="The output appears too small to satisfy the task. The safe strategy is to improve assessment signals before changing generation.",
            actions=[
                "Record expected artifact type and minimum useful fields in observation metadata",
                "Flag low-output observations for human review when no error was reported",
                "Compare output_tokens with task class instead of using a global threshold only",
            ],
            effort=1.5,
        )

    def _persistence_strategy(self, assessment: AssessmentResult) -> ImprovementStrategy:
        return self._base(
            assessment,
            title="Enforce context fingerprint at observation creation",
            rationale="Payload was present without a context fingerprint, which weakens later baseline and recovery logic.",
            actions=[
                "Route observation creation through ObservationRecorder instead of direct model construction",
                "Add a dry-run warning when payload exists without context_fingerprint",
                "Backfill fingerprint only after JSONL and SQLite recovery semantics are validated",
            ],
            effort=1.0,
        )

    def _instrumentation_strategy(self, assessment: AssessmentResult) -> ImprovementStrategy:
        return self._base(
            assessment,
            title="Increase observation granularity for this bottleneck",
            rationale="More structured evidence will make later Phase 3/4 changes safer and more reviewable.",
            actions=[
                "Store event_type-specific counters in observation metadata",
                "Collect at least five comparable observations before proposing code mutation",
                "Keep strategy output dry-run only until validation and rollback are implemented",
            ],
            effort=1.0,
        )


class StrategyGate(BaseModel):
    """Read-only gate for determining whether a strategy may proceed later."""

    model_config = ConfigDict(frozen=True)

    dry_run: bool = True
    max_autonomous_risk: RiskLevel = RiskLevel.LOW
    require_human_approval_for: tuple[RiskLevel, ...] = (RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL)

    def requires_approval(self, strategy: ImprovementStrategy) -> bool:
        """Return whether *strategy* requires human approval."""

        return strategy.risk in self.require_human_approval_for

    def can_auto_apply(self, strategy: ImprovementStrategy) -> bool:
        """Return false in Phase 2; provided for later orchestration compatibility."""

        if self.dry_run:
            return False
        if strategy.dry_run_only:
            return False
        if self.requires_approval(strategy):
            return False
        return strategy.can_auto_apply


__all__ = [
    "ImprovementStrategy",
    "RiskLevel",
    "StrategyAction",
    "StrategyGate",
    "StrategyGenerator",
    "StrategyGeneratorConfig",
]
