"""Integration hooks for Hermes self-improvement.

This module provides a thin, opt-in layer that wraps the self-improvement
pipeline around a standard Hermes tool-execution session.  It is designed to be
used *by the agent itself*, not by the runtime engine.

Recommended usage inside a Hermes turn:

    from selfimprovement import hooks as si

    with si.session() as sess:
        sess.before_step("terminal", {"command": "git status"})
        try:
            result = terminal(...)
        except Exception as exc:
            sess.after_step(None, error=exc)
            raise
        else:
            sess.after_step(result, latency_ms=1200)
        # at end of turn
        report = sess.end_turn()
        if report and report.strategies:
            print(report.strategies)
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from selfimprovement.loopguard import LoopGuard, LoopGuardBlocked
from selfimprovement.observation import (
    JsonlObservationSink,
    Observation,
    ObservationRecorder,
    SQLiteObservationStore,
)
from selfimprovement.selfimprovement import (
    SelfImprovementCycleInput,
    SelfImprovementEngine,
    SelfImprovementMode,
)

_DEFAULT_DB = Path.home() / ".hermes" / "selfimprovement" / "observations.sqlite3"
_DEFAULT_JSONL = Path.home() / ".hermes" / "selfimprovement" / "observations.jsonl"


class StepContext:
    """One self-improvement session context."""

    def __init__(
        self,
        engine: SelfImprovementEngine,
        recorder: ObservationRecorder,
        loop_guard: LoopGuard | None,
        *,
        session_id: str,
        task_id: str,
        turn_id: str,
    ) -> None:
        self.engine = engine
        self.recorder = recorder
        self.loop_guard = loop_guard
        self.session_id = session_id
        self.task_id = task_id
        self.turn_id = turn_id
        self._observations: list[Observation] = []
        self._current_step: int = 0
        self._step_start: float = 0.0
        self._last_tool: str = ""
        self._last_payload: Any = None

    def before_step(self, tool_name: str, payload: Any) -> None:
        """Guard and record intent before executing a tool."""

        self._current_step += 1
        if self.loop_guard is not None:
            decision = self.loop_guard.record(payload, observation_hash=self.turn_id)
            if not decision.allowed:
                raise LoopGuardBlocked(decision)
        self._last_tool = tool_name
        self._last_payload = payload
        self._step_start = time.monotonic()

    def after_step(
        self,
        result: Any,
        *,
        error: Exception | None = None,
        retry_count: int = 0,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        latency_ms: int | None = None,
    ) -> Observation:
        """Record completion of the last tool call."""

        if latency_ms is not None:
            elapsed_ms = latency_ms
        else:
            elapsed_ms = int((time.monotonic() - self._step_start) * 1000)
        result_summary = str(result)[:1000] if result is not None else ""
        obs = self.recorder.record(
            event_type=f"tool:{self._last_tool}",
            context={"payload": self._last_payload, "result_summary": result_summary},
            metadata={
                "step": self._current_step,
                "error_type": type(error).__name__ if error else None,
            },
            session_id=self.session_id,
            task_id=self.task_id,
            turn_id=self.turn_id,
            latency_ms=elapsed_ms,
            error_count=int(error is not None),
            retry_count=retry_count,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        self._observations.append(obs)
        return obs

    def end_turn(self) -> Any | None:
        """Assess the last observation and return strategies (sync wrapper)."""

        if not self._observations:
            return None
        last_obs = self._observations[-1]
        cycle_input = SelfImprovementCycleInput(
            observation=last_obs,
            mode=SelfImprovementMode.PLAN,
        )
        import asyncio
        return asyncio.run(self.engine.run_cycle(cycle_input))

    async def end_turn_async(self) -> Any | None:
        """Async assessment at the end of a turn."""

        if not self._observations:
            return None
        last_obs = self._observations[-1]
        cycle_input = SelfImprovementCycleInput(
            observation=last_obs,
            mode=SelfImprovementMode.PLAN,
        )
        return await self.engine.run_cycle(cycle_input)


def _default_recorder(
    db_path: Path | None = None,
    jsonl_path: Path | None = None,
) -> ObservationRecorder:
    db_path = db_path or _DEFAULT_DB
    jsonl_path = jsonl_path or _DEFAULT_JSONL
    db_path.parent.mkdir(parents=True, exist_ok=True)
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    store = SQLiteObservationStore(db_path)
    sink = JsonlObservationSink(jsonl_path)
    return ObservationRecorder(sqlite_store=store, jsonl_sink=sink)


def session(
    *,
    db_path: Path | None = None,
    jsonl_path: Path | None = None,
    loop_guard: LoopGuard | None = None,
    session_id: str | None = None,
    task_id: str | None = None,
    turn_id: str | None = None,
) -> StepContext:
    """Create and return a new self-improvement session context."""

    sid = session_id or uuid.uuid4().hex[:12]
    tid = task_id or uuid.uuid4().hex[:12]
    rid = turn_id or uuid.uuid4().hex[:12]
    recorder = _default_recorder(db_path, jsonl_path)
    engine = SelfImprovementEngine()
    return StepContext(engine, recorder, loop_guard, session_id=sid, task_id=tid, turn_id=rid)
