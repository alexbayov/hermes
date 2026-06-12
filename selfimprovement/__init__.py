"""Hermes self-improvement package.

Production-ready observe → assess → strategize → modify → validate → rollback
pipeline.  All mutation is sandboxed, all strategies are dry-run by default, and
all modification requires explicit approval.

Recommended entry point for runtime integration:
    from selfimprovement import hooks as si
    with si.session() as sess:
        sess.before_step(tool_name, payload)
        result = run_tool()
        sess.after_step(result)
        report = sess.end_turn()
"""

from selfimprovement.assessment import (
    AssessmentCategory,
    AssessmentConfig,
    AssessmentResult,
    AssessmentSeverity,
    BaselineMetrics,
    QualityAssessor,
)
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
from selfimprovement.modification import (
    FilePatch,
    ModificationManager,
    ModificationPlan,
    ModificationReport,
    ModificationRisk,
    ModificationStatus,
    PatchKind,
    PatchResult,
    SymbolNotFoundError,
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
from selfimprovement.rollback import (
    RollbackIntegrityReport,
    RollbackManager,
    RollbackPoint,
    RollbackReport,
    RollbackStatus,
    SQLiteIntegrityResult,
)
from selfimprovement.selfimprovement import (
    SelfImprovementConfig,
    SelfImprovementCycleInput,
    SelfImprovementCycleReport,
    SelfImprovementEngine,
    SelfImprovementMode,
    SelfImprovementStatus,
)
from selfimprovement.strategy import (
    ImprovementStrategy,
    RiskLevel,
    StrategyAction,
    StrategyGate,
    StrategyGenerator,
    StrategyGeneratorConfig,
)
from selfimprovement.validation import (
    ValidationCheck,
    ValidationReport,
    ValidationStatus,
    Validator,
)

__all__ = [
    # loopguard (Phase 1)
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitState",
    "LoopGuard",
    "LoopGuardBlocked",
    "LoopGuardConfig",
    "LoopGuardDecision",
    "LoopGuardReason",
    "LoopGuardTimeout",
    # observation (Phase 1)
    "JsonlIntegrityError",
    "JsonlObservationSink",
    "Observation",
    "ObservationIntegrityError",
    "ObservationRecorder",
    "SecretRedactor",
    "SQLiteObservationStore",
    "stable_fingerprint",
    # assessment (Phase 2)
    "AssessmentCategory",
    "AssessmentConfig",
    "AssessmentResult",
    "AssessmentSeverity",
    "BaselineMetrics",
    "QualityAssessor",
    # strategy (Phase 2)
    "ImprovementStrategy",
    "RiskLevel",
    "StrategyAction",
    "StrategyGate",
    "StrategyGenerator",
    "StrategyGeneratorConfig",
    # rollback (Phase 3)
    "RollbackIntegrityReport",
    "RollbackManager",
    "RollbackPoint",
    "RollbackReport",
    "RollbackStatus",
    "SQLiteIntegrityResult",
    # validation (Phase 3)
    "ValidationCheck",
    "ValidationReport",
    "ValidationStatus",
    "Validator",
    # modification (Phase 4)
    "FilePatch",
    "ModificationManager",
    "ModificationPlan",
    "ModificationReport",
    "ModificationRisk",
    "ModificationStatus",
    "PatchKind",
    "PatchResult",
    "SymbolNotFoundError",
    # orchestration (Phase 5)
    "SelfImprovementConfig",
    "SelfImprovementCycleInput",
    "SelfImprovementCycleReport",
    "SelfImprovementEngine",
    "SelfImprovementMode",
    "SelfImprovementStatus",
]
