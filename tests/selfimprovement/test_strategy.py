import pytest

from selfimprovement.assessment import AssessmentCategory, AssessmentResult, AssessmentSeverity
from selfimprovement.strategy import ImprovementStrategy, RiskLevel, StrategyAction, StrategyGate, StrategyGenerator


def make_assessment(category=AssessmentCategory.TOOL_RETRY_LOOP):
    return AssessmentResult(
        observation_id="obs1",
        category=category,
        severity=AssessmentSeverity.HIGH,
        quality_score=0.4,
        confidence=0.8,
        expected_impact=0.7,
        bottleneck="test bottleneck",
        evidence={"retry_count": 3},
        needs_strategy=True,
    )


def test_generator_returns_ranked_dry_run_strategies():
    strategies = StrategyGenerator().generate(make_assessment())
    assert strategies
    assert strategies == sorted(strategies, key=lambda item: item.priority, reverse=True)
    assert all(strategy.dry_run_only for strategy in strategies)
    assert all(not strategy.can_auto_apply for strategy in strategies)


def test_generator_returns_empty_for_healthy_assessment():
    assessment = make_assessment(AssessmentCategory.HEALTHY).model_copy(update={"needs_strategy": False, "expected_impact": 0.0})
    assert StrategyGenerator().generate(assessment) == []


def test_phase2_strategy_rejects_mutating_actions():
    with pytest.raises(ValueError):
        ImprovementStrategy(
            assessment_id="obs1",
            category=AssessmentCategory.TOOL_RETRY_LOOP,
            title="bad",
            rationale="bad",
            actions=(StrategyAction(description="patch code", mutates_code=True),),
            expected_impact=0.5,
            confidence=0.5,
            effort=1.0,
            risk=RiskLevel.LOW,
        )


def test_gate_never_auto_applies_in_dry_run():
    strategy = StrategyGenerator().generate(make_assessment())[0]
    gate = StrategyGate(dry_run=True)
    assert gate.requires_approval(strategy) is False
    assert gate.can_auto_apply(strategy) is False
