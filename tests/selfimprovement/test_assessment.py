from selfimprovement.assessment import AssessmentCategory, AssessmentSeverity, BaselineMetrics, QualityAssessor
from selfimprovement.observation import Observation


def test_assessor_detects_retry_loop():
    obs = Observation(event_type="after_step", retry_count=3, context_fingerprint="abc")
    result = QualityAssessor().assess(obs)
    assert result.category is AssessmentCategory.TOOL_RETRY_LOOP
    assert result.severity is AssessmentSeverity.HIGH
    assert result.needs_strategy


def test_assessor_detects_latency_regression_against_baseline():
    obs = Observation(event_type="after_step", latency_ms=3000, context_fingerprint="abc")
    baseline = BaselineMetrics(latency_ms_p50=1000, sample_size=20)
    result = QualityAssessor().assess(obs, baseline)
    assert result.category is AssessmentCategory.LATENCY_REGRESSION
    assert result.confidence >= 0.75


def test_assessor_reports_healthy_observation():
    obs = Observation(event_type="after_step", output_tokens=100, context_fingerprint="abc")
    result = QualityAssessor().assess(obs)
    assert result.category is AssessmentCategory.HEALTHY
    assert not result.needs_strategy
