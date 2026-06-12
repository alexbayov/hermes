"""Manual orchestration layer for Hermes self-improvement Phase 5.

The engine coordinates the earlier phases but does not start background work,
expose an API, or generate patches autonomously. Code modification is only
possible when the caller supplies an explicit ``ModificationPlan`` and requests
``APPLY`` mode with approval.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from selfimprovement.assessment import AssessmentResult, BaselineMetrics, QualityAssessor
from selfimprovement.modification import ModificationManager, ModificationPlan, ModificationReport, ModificationRisk
from selfimprovement.observation import Observation
from selfimprovement.rollback import RollbackManager, RollbackReport
from selfimprovement.strategy import ImprovementStrategy, StrategyGenerator
from selfimprovement.validation import ValidationReport, ValidationStatus, Validator


def _utc_now() -> datetime:
    return datetime.now(UTC)


class SelfImprovementMode(StrEnum):
    """Explicit mode for one self-improvement cycle."""

    OBSERVE = "observe"
    PLAN = "plan"
    DRY_RUN = "dry_run"
    APPLY = "apply"


class SelfImprovementStatus(StrEnum):
    """Final status of one self-improvement cycle."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    NEEDS_APPROVAL = "needs_approval"
    ROLLED_BACK = "rolled_back"


class SelfImprovementConfig(BaseModel):
    """Configuration for manual orchestration.

    ``default_mode`` is intentionally PLAN. APPLY is never selected implicitly.
    """

    model_config = ConfigDict(frozen=True)

    default_mode: SelfImprovementMode = SelfImprovementMode.PLAN
    allow_apply: bool = False
    require_apply_approval: bool = True
    reject_high_risk: bool = True
    run_pytest: bool = True
    pytest_args: tuple[str, ...] = ("-q",)
    rollback_on_validation_failure: bool = True


class SelfImprovementCycleInput(BaseModel):
    """Input for one manual orchestration cycle."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    observation: Observation
    baseline: BaselineMetrics | None = None
    mode: SelfImprovementMode | None = None
    modification_plan: ModificationPlan | None = None
    approved: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class SelfImprovementCycleReport(BaseModel):
    """Structured report for one self-improvement cycle."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str = Field(default_factory=lambda: uuid4().hex)
    started_at: datetime
    finished_at: datetime
    mode: SelfImprovementMode
    status: SelfImprovementStatus
    observation_id: str
    assessment: AssessmentResult | None = None
    strategies: tuple[ImprovementStrategy, ...] = ()
    modification_report: ModificationReport | None = None
    validation_report: ValidationReport | None = None
    rollback_report: RollbackReport | None = None
    errors: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("started_at", "finished_at")
    @classmethod
    def _ensure_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class SelfImprovementEngine:
    """Manual coordinator for Phases 1-5.

    The engine can assess an observation, generate read-only strategies, execute
    a caller-supplied modification plan in dry-run/apply mode, run validation,
    and roll back on validation failure. It never derives patches from strategy
    text and never starts a daemon, scheduler, API server, or background loop.
    """

    def __init__(
        self,
        *,
        assessor: QualityAssessor | None = None,
        strategy_generator: StrategyGenerator | None = None,
        modification_manager: ModificationManager | None = None,
        validator: Validator | None = None,
        rollback_manager: RollbackManager | None = None,
        config: SelfImprovementConfig | None = None,
    ) -> None:
        self.assessor = assessor or QualityAssessor()
        self.strategy_generator = strategy_generator or StrategyGenerator()
        self.modification_manager = modification_manager
        self.validator = validator
        self.rollback_manager = rollback_manager
        self.config = config or SelfImprovementConfig()

    async def run_cycle(self, cycle_input: SelfImprovementCycleInput) -> SelfImprovementCycleReport:
        """Run exactly one explicit self-improvement cycle."""

        started_at = _utc_now()
        mode = cycle_input.mode or self.config.default_mode
        assessment: AssessmentResult | None = None
        strategies: tuple[ImprovementStrategy, ...] = ()
        modification_report: ModificationReport | None = None
        validation_report: ValidationReport | None = None
        rollback_report: RollbackReport | None = None
        errors: list[str] = []
        status = SelfImprovementStatus.PASSED

        if mode is SelfImprovementMode.OBSERVE:
            return self._report(
                started_at=started_at,
                mode=mode,
                status=SelfImprovementStatus.PASSED,
                cycle_input=cycle_input,
            )

        assessment = self.assessor.assess(cycle_input.observation, cycle_input.baseline)
        strategies = tuple(self.strategy_generator.generate(assessment))

        if mode is SelfImprovementMode.PLAN:
            return self._report(
                started_at=started_at,
                mode=mode,
                status=SelfImprovementStatus.PASSED,
                cycle_input=cycle_input,
                assessment=assessment,
                strategies=strategies,
            )

        if cycle_input.modification_plan is None:
            return self._report(
                started_at=started_at,
                mode=mode,
                status=SelfImprovementStatus.FAILED,
                cycle_input=cycle_input,
                assessment=assessment,
                strategies=strategies,
                errors=("dry_run/apply mode requires an explicit ModificationPlan",),
            )

        risk_error = self._risk_error(cycle_input.modification_plan)
        if risk_error is not None:
            return self._report(
                started_at=started_at,
                mode=mode,
                status=SelfImprovementStatus.FAILED,
                cycle_input=cycle_input,
                assessment=assessment,
                strategies=strategies,
                errors=(risk_error,),
            )

        if self.modification_manager is None:
            return self._report(
                started_at=started_at,
                mode=mode,
                status=SelfImprovementStatus.FAILED,
                cycle_input=cycle_input,
                assessment=assessment,
                strategies=strategies,
                errors=("ModificationManager is required for dry_run/apply mode",),
            )

        if mode is SelfImprovementMode.APPLY:
            if not self.config.allow_apply:
                return self._report(
                    started_at=started_at,
                    mode=mode,
                    status=SelfImprovementStatus.NEEDS_APPROVAL,
                    cycle_input=cycle_input,
                    assessment=assessment,
                    strategies=strategies,
                    errors=("apply mode is disabled by configuration",),
                )
            if self.config.require_apply_approval and not cycle_input.approved:
                return self._report(
                    started_at=started_at,
                    mode=mode,
                    status=SelfImprovementStatus.NEEDS_APPROVAL,
                    cycle_input=cycle_input,
                    assessment=assessment,
                    strategies=strategies,
                    errors=("apply mode requires approved=True",),
                )

        plan = self._plan_for_mode(cycle_input.modification_plan, mode)
        modification_report = self.modification_manager.apply(plan, approved=cycle_input.approved and mode is SelfImprovementMode.APPLY)
        if modification_report.status.value == "failed":
            return self._report(
                started_at=started_at,
                mode=mode,
                status=SelfImprovementStatus.FAILED,
                cycle_input=cycle_input,
                assessment=assessment,
                strategies=strategies,
                modification_report=modification_report,
                errors=modification_report.errors,
            )

        if mode is SelfImprovementMode.DRY_RUN:
            return self._report(
                started_at=started_at,
                mode=mode,
                status=SelfImprovementStatus.PASSED,
                cycle_input=cycle_input,
                assessment=assessment,
                strategies=strategies,
                modification_report=modification_report,
            )

        if self.validator is not None:
            validation_report = await self.validator.validate(
                changed_files=modification_report.changed_files,
                run_pytest=self.config.run_pytest,
                pytest_args=self.config.pytest_args,
            )
            if validation_report.status is ValidationStatus.FAILED:
                errors.append("validation failed after apply")
                if (
                    self.config.rollback_on_validation_failure
                    and self.rollback_manager is not None
                    and modification_report.rollback_point is not None
                ):
                    rollback_report = self.rollback_manager.restore(modification_report.rollback_point)
                    status = SelfImprovementStatus.ROLLED_BACK
                else:
                    status = SelfImprovementStatus.FAILED
            else:
                status = SelfImprovementStatus.PASSED

        return self._report(
            started_at=started_at,
            mode=mode,
            status=status,
            cycle_input=cycle_input,
            assessment=assessment,
            strategies=strategies,
            modification_report=modification_report,
            validation_report=validation_report,
            rollback_report=rollback_report,
            errors=tuple(errors),
        )

    def _risk_error(self, plan: ModificationPlan) -> str | None:
        if self.config.reject_high_risk and plan.risk in {ModificationRisk.HIGH, ModificationRisk.CRITICAL}:
            return "high/critical risk ModificationPlan is rejected by orchestration policy"
        return None

    @staticmethod
    def _plan_for_mode(plan: ModificationPlan, mode: SelfImprovementMode) -> ModificationPlan:
        if mode is SelfImprovementMode.DRY_RUN:
            return plan.model_copy(update={"dry_run": True, "requires_approval": plan.requires_approval})
        if mode is SelfImprovementMode.APPLY:
            return plan.model_copy(update={"dry_run": False, "requires_approval": True})
        return plan

    @staticmethod
    def _report(
        *,
        started_at: datetime,
        mode: SelfImprovementMode,
        status: SelfImprovementStatus,
        cycle_input: SelfImprovementCycleInput,
        assessment: AssessmentResult | None = None,
        strategies: Sequence[ImprovementStrategy] = (),
        modification_report: ModificationReport | None = None,
        validation_report: ValidationReport | None = None,
        rollback_report: RollbackReport | None = None,
        errors: Sequence[str] = (),
    ) -> SelfImprovementCycleReport:
        return SelfImprovementCycleReport(
            started_at=started_at,
            finished_at=_utc_now(),
            mode=mode,
            status=status,
            observation_id=cycle_input.observation.id,
            assessment=assessment,
            strategies=tuple(strategies),
            modification_report=modification_report,
            validation_report=validation_report,
            rollback_report=rollback_report,
            errors=tuple(errors),
            metadata=dict(cycle_input.metadata),
        )


__all__ = [
    "SelfImprovementConfig",
    "SelfImprovementCycleInput",
    "SelfImprovementCycleReport",
    "SelfImprovementEngine",
    "SelfImprovementMode",
    "SelfImprovementStatus",
]
