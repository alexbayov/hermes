from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from selfimprovement.modification import FilePatch, ModificationManager, ModificationPlan, ModificationRisk
from selfimprovement.observation import Observation
from selfimprovement.rollback import RollbackManager
from selfimprovement.selfimprovement import (
    SelfImprovementConfig,
    SelfImprovementCycleInput,
    SelfImprovementEngine,
    SelfImprovementMode,
    SelfImprovementStatus,
)
from selfimprovement.validation import ValidationCheck, ValidationReport, ValidationStatus


@pytest.mark.asyncio
async def test_plan_mode_assesses_observation_and_returns_strategies_without_mutation():
    observation = Observation(event_type="tool", retry_count=2)
    engine = SelfImprovementEngine()

    report = await engine.run_cycle(SelfImprovementCycleInput(observation=observation, mode=SelfImprovementMode.PLAN))

    assert report.status is SelfImprovementStatus.PASSED
    assert report.assessment is not None
    assert report.assessment.needs_strategy is True
    assert report.strategies
    assert report.modification_report is None


@pytest.mark.asyncio
async def test_dry_run_mode_requires_explicit_modification_plan(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    engine = SelfImprovementEngine(modification_manager=ModificationManager(repo, tmp_path / "sandbox"))

    report = await engine.run_cycle(
        SelfImprovementCycleInput(observation=Observation(event_type="tool"), mode=SelfImprovementMode.DRY_RUN)
    )

    assert report.status is SelfImprovementStatus.FAILED
    assert "ModificationPlan" in report.errors[0]


@pytest.mark.asyncio
async def test_dry_run_modification_writes_only_to_sandbox_not_repo(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "module.py"
    target.write_text("def greet():\n    return 'old'\n", encoding="utf-8")
    plan = ModificationPlan(
        patches=(
            FilePatch(
                path=Path("module.py"),
                kind="python_symbol_replace",
                symbol="greet",
                replacement="def greet():\n    return 'new'\n",
            ),
        )
    )
    engine = SelfImprovementEngine(modification_manager=ModificationManager(repo, tmp_path / "sandbox"))

    report = await engine.run_cycle(
        SelfImprovementCycleInput(
            observation=Observation(event_type="tool", retry_count=2),
            mode=SelfImprovementMode.DRY_RUN,
            modification_plan=plan,
        )
    )

    assert report.status is SelfImprovementStatus.PASSED
    assert report.modification_report is not None
    assert "return 'old'" in target.read_text(encoding="utf-8")
    sandbox_path = report.modification_report.patch_results[0].sandbox_path
    assert sandbox_path is not None
    assert "return 'new'" in sandbox_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_apply_mode_without_approval_returns_needs_approval(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "module.py").write_text("def greet():\n    return 'old'\n", encoding="utf-8")
    plan = ModificationPlan(
        patches=(
            FilePatch(
                path=Path("module.py"),
                kind="python_symbol_replace",
                symbol="greet",
                replacement="def greet():\n    return 'new'\n",
            ),
        )
    )
    engine = SelfImprovementEngine(
        modification_manager=ModificationManager(repo, tmp_path / "sandbox"),
        config=SelfImprovementConfig(allow_apply=True),
    )

    report = await engine.run_cycle(
        SelfImprovementCycleInput(
            observation=Observation(event_type="tool"),
            mode=SelfImprovementMode.APPLY,
            modification_plan=plan,
            approved=False,
        )
    )

    assert report.status is SelfImprovementStatus.NEEDS_APPROVAL
    assert report.modification_report is None


@pytest.mark.asyncio
async def test_high_risk_modification_plan_is_rejected(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    plan = ModificationPlan(
        risk=ModificationRisk.HIGH,
        patches=(
            FilePatch(
                path=Path("module.py"),
                kind="python_symbol_replace",
                symbol="greet",
                replacement="def greet():\n    return 'new'\n",
            ),
        ),
    )
    engine = SelfImprovementEngine(modification_manager=ModificationManager(repo, tmp_path / "sandbox"))

    report = await engine.run_cycle(
        SelfImprovementCycleInput(
            observation=Observation(event_type="tool"),
            mode=SelfImprovementMode.DRY_RUN,
            modification_plan=plan,
        )
    )

    assert report.status is SelfImprovementStatus.FAILED
    assert "high/critical" in report.errors[0]


class FailingValidator:
    async def validate(self, *, changed_files, run_pytest=True, pytest_args=("-q",)):
        now = datetime.now(UTC)
        return ValidationReport(
            started_at=now,
            finished_at=now,
            status=ValidationStatus.FAILED,
            changed_files=tuple(changed_files),
            checks=(
                ValidationCheck(
                    name="forced_failure",
                    status=ValidationStatus.FAILED,
                    command=None,
                    duration_ms=0,
                    stdout="",
                    stderr="",
                    error="forced",
                ),
            ),
        )


@pytest.mark.asyncio
async def test_validation_failure_after_apply_triggers_rollback(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "module.py"
    target.write_text("def greet():\n    return 'old'\n", encoding="utf-8")
    rollback_manager = RollbackManager(repo, tmp_path / "backups")
    modification_manager = ModificationManager(repo, tmp_path / "sandbox", rollback_manager=rollback_manager)
    plan = ModificationPlan(
        dry_run=False,
        patches=(
            FilePatch(
                path=Path("module.py"),
                kind="python_symbol_replace",
                symbol="greet",
                replacement="def greet():\n    return 'new'\n",
            ),
        ),
    )
    engine = SelfImprovementEngine(
        modification_manager=modification_manager,
        rollback_manager=rollback_manager,
        validator=FailingValidator(),
        config=SelfImprovementConfig(allow_apply=True),
    )

    report = await engine.run_cycle(
        SelfImprovementCycleInput(
            observation=Observation(event_type="tool"),
            mode=SelfImprovementMode.APPLY,
            modification_plan=plan,
            approved=True,
        )
    )

    assert report.status is SelfImprovementStatus.ROLLED_BACK
    assert report.rollback_report is not None
    assert "return 'old'" in target.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_strategy_does_not_generate_modification_plan_automatically():
    observation = Observation(event_type="tool", retry_count=2)
    engine = SelfImprovementEngine()

    report = await engine.run_cycle(SelfImprovementCycleInput(observation=observation, mode=SelfImprovementMode.PLAN))

    assert report.strategies
    assert report.modification_report is None
