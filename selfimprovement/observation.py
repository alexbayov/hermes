"""Observation models and durable sinks for Hermes self-improvement.

Phase 1 is deliberately write-only/observational: it records sanitized runtime
observations to SQLite and JSONL without changing Hermes behavior. Existing
JSONL corruption is strict by default: the corrupt file is rotated aside and an
explicit integrity error is raised instead of silently skipping damaged lines.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import sqlite3
import threading
from collections.abc import Iterable, Iterator, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_SECRET_KEY_PATTERNS: Final[tuple[str, ...]] = (
    r"(?i)(?:^|[_.\-])(?:pass(?:word)?|passwd|pwd)(?:$|[_.\-])",
    r"(?i)(?:^|[_.\-])(?:secret|client[_\-]?secret)(?:$|[_.\-])",
    r"(?i)(?:^|[_.\-])(?:token|api[_\-]?token|access[_\-]?token|refresh[_\-]?token|id[_\-]?token)(?:$|[_.\-])",
    r"(?i)(?:^|[_.\-])(?:api[_\-]?key|apikey|client[_\-]?key|access[_\-]?key)(?:$|[_.\-])",
    r"(?i)(?:^|[_.\-])(?:credential|credentials|cookie|authorization|auth)(?:$|[_.\-])",
)

DEFAULT_VOLATILE_KEY_PATTERNS: Final[tuple[str, ...]] = (
    r"(?i)(?:^|[_.\-])(?:timestamp|time|ts|_ts|created_at|updated_at)(?:$|[_.\-])",
    r"(?i)(?:^|[_.\-])(?:nonce|csrf|xsrf|request[_\-]?id|trace[_\-]?id|span[_\-]?id)(?:$|[_.\-])",
    r"(?i)(?:^|[_.\-])(?:cursor|page[_\-]?token|next[_\-]?page[_\-]?token)(?:$|[_.\-])",
)

REDACTED: Final[str] = "[REDACTED]"


class ObservationIntegrityError(RuntimeError):
    """Base class for observation persistence integrity failures."""


class JsonlIntegrityError(ObservationIntegrityError):
    """Raised when an existing JSONL observation log is malformed in strict mode."""

    def __init__(self, message: str, *, corrupt_path: Path | None = None) -> None:
        super().__init__(message)
        self.corrupt_path = corrupt_path


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _compile_patterns(patterns: Iterable[str]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pattern) for pattern in patterns)


class SecretRedactor:
    """Recursively redact sensitive keys from JSON-compatible payloads.

    The policy is regex-based and configurable so variants such as ``apiToken``,
    ``passwd``, ``client_key`` and ``Authorization`` do not slip through a fixed
    literal list.
    """

    def __init__(
        self,
        key_patterns: Iterable[str] = DEFAULT_SECRET_KEY_PATTERNS,
        *,
        replacement: str = REDACTED,
        max_depth: int = 20,
    ) -> None:
        self._patterns = _compile_patterns(key_patterns)
        self.replacement = replacement
        self.max_depth = max_depth

    def is_secret_key(self, key: str) -> bool:
        """Return true when *key* should be redacted."""

        return any(pattern.search(key) for pattern in self._patterns)

    def redact(self, value: Any) -> Any:
        """Return a sanitized deep copy of *value*."""

        return self._redact(value, depth=0)

    def _redact(self, value: Any, *, depth: int) -> Any:
        if depth > self.max_depth:
            return "[MAX_DEPTH]"

        if isinstance(value, Mapping):
            out: dict[str, Any] = {}
            for raw_key, raw_value in value.items():
                key = str(raw_key)
                out[key] = self.replacement if self.is_secret_key(key) else self._redact(raw_value, depth=depth + 1)
            return out

        if isinstance(value, tuple):
            return [self._redact(item, depth=depth + 1) for item in value]

        if isinstance(value, list):
            return [self._redact(item, depth=depth + 1) for item in value]

        if isinstance(value, set):
            return sorted(self._redact(item, depth=depth + 1) for item in value)

        return value


def _is_volatile_key(key: str, patterns: Sequence[re.Pattern[str]]) -> bool:
    return any(pattern.search(key) for pattern in patterns)


def _canonicalize_for_fingerprint(value: Any, *, volatile_patterns: Sequence[re.Pattern[str]], depth: int = 0) -> Any:
    if depth > 20:
        return "[MAX_DEPTH]"

    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            if _is_volatile_key(key, volatile_patterns):
                continue
            out[key] = _canonicalize_for_fingerprint(raw_value, volatile_patterns=volatile_patterns, depth=depth + 1)
        return {key: out[key] for key in sorted(out)}

    if isinstance(value, (list, tuple)):
        return [_canonicalize_for_fingerprint(item, volatile_patterns=volatile_patterns, depth=depth + 1) for item in value]

    if isinstance(value, set):
        return sorted(_canonicalize_for_fingerprint(item, volatile_patterns=volatile_patterns, depth=depth + 1) for item in value)

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, datetime):
        return value.isoformat()

    return value


def stable_fingerprint(
    value: Any,
    *,
    volatile_key_patterns: Iterable[str] = DEFAULT_VOLATILE_KEY_PATTERNS,
    digest_size: int = 16,
) -> str:
    """Return a stable SHA-256 fingerprint for JSON-like data.

    Volatile fields are excluded before hashing. Defaults exclude timestamps,
    nonces, request IDs, CSRF/XSRF values, and pagination cursors.
    """

    patterns = _compile_patterns(volatile_key_patterns)
    canonical = _canonicalize_for_fingerprint(value, volatile_patterns=patterns)
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:digest_size]


class Observation(BaseModel):
    """A sanitized runtime event used by self-improvement assessment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(default_factory=lambda: uuid4().hex)
    observed_at: datetime = Field(default_factory=_utc_now)
    event_type: str
    source: str = "hermes"
    session_id: str | None = None
    task_id: str | None = None
    turn_id: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    error_count: int = Field(default=0, ge=0)
    retry_count: int = Field(default=0, ge=0)
    intent_drift: float | None = Field(default=None, ge=0.0, le=1.0)
    quality_score: float | None = Field(default=None, ge=0.0, le=1.0)
    context_fingerprint: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    schema_version: int = Field(default=1, ge=1)

    @field_validator("observed_at")
    @classmethod
    def _ensure_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @field_validator("event_type", "source")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    def fingerprint(self) -> str:
        """Return a stable fingerprint of semantically relevant fields."""

        return stable_fingerprint(
            {
                "event_type": self.event_type,
                "source": self.source,
                "session_id": self.session_id,
                "task_id": self.task_id,
                "turn_id": self.turn_id,
                "payload": self.payload,
                "metadata": self.metadata,
            }
        )

    def to_json_line(self) -> str:
        """Serialize the observation as one JSONL record."""

        return self.model_dump_json() + "\n"


class SQLiteObservationStore:
    """SQLite-backed observation store.

    Writes are idempotent by observation id. The schema stores the full sanitized
    payload as JSON while indexing fields needed by later assessment phases.
    """

    def __init__(self, path: str | Path, *, timeout_s: float = 30.0) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, timeout=timeout_s, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS observations (
                    id TEXT PRIMARY KEY,
                    observed_at TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    session_id TEXT,
                    task_id TEXT,
                    turn_id TEXT,
                    fingerprint TEXT NOT NULL,
                    latency_ms INTEGER,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    error_count INTEGER NOT NULL DEFAULT 0,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    intent_drift REAL,
                    quality_score REAL,
                    payload_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_observations_observed_at ON observations(observed_at);
                CREATE INDEX IF NOT EXISTS idx_observations_event_type ON observations(event_type);
                CREATE INDEX IF NOT EXISTS idx_observations_session ON observations(session_id, observed_at);
                CREATE INDEX IF NOT EXISTS idx_observations_task ON observations(task_id, observed_at);
                CREATE INDEX IF NOT EXISTS idx_observations_fingerprint ON observations(fingerprint);
                """
            )
            self._conn.commit()

    def append(self, observation: Observation) -> None:
        """Insert or update *observation* by id."""

        payload = observation.model_dump(mode="json")
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO observations (
                    id, observed_at, event_type, source, session_id, task_id, turn_id,
                    fingerprint, latency_ms, input_tokens, output_tokens, error_count,
                    retry_count, intent_drift, quality_score, payload_json, metadata_json,
                    schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    observed_at = excluded.observed_at,
                    event_type = excluded.event_type,
                    source = excluded.source,
                    session_id = excluded.session_id,
                    task_id = excluded.task_id,
                    turn_id = excluded.turn_id,
                    fingerprint = excluded.fingerprint,
                    latency_ms = excluded.latency_ms,
                    input_tokens = excluded.input_tokens,
                    output_tokens = excluded.output_tokens,
                    error_count = excluded.error_count,
                    retry_count = excluded.retry_count,
                    intent_drift = excluded.intent_drift,
                    quality_score = excluded.quality_score,
                    payload_json = excluded.payload_json,
                    metadata_json = excluded.metadata_json,
                    schema_version = excluded.schema_version
                """,
                (
                    observation.id,
                    observation.observed_at.isoformat(),
                    observation.event_type,
                    observation.source,
                    observation.session_id,
                    observation.task_id,
                    observation.turn_id,
                    observation.fingerprint(),
                    observation.latency_ms,
                    observation.input_tokens,
                    observation.output_tokens,
                    observation.error_count,
                    observation.retry_count,
                    observation.intent_drift,
                    observation.quality_score,
                    json.dumps(payload, sort_keys=True, ensure_ascii=False),
                    json.dumps(observation.metadata, sort_keys=True, ensure_ascii=False, default=str),
                    observation.schema_version,
                ),
            )
            self._conn.commit()

    async def append_async(self, observation: Observation) -> None:
        """Async wrapper for append, suitable for event-loop callers."""

        await asyncio.to_thread(self.append, observation)

    def get(self, observation_id: str) -> Observation | None:
        """Return one observation by id, if present."""

        with self._lock:
            row = self._conn.execute("SELECT payload_json FROM observations WHERE id = ?", (observation_id,)).fetchone()
        if row is None:
            return None
        return Observation.model_validate_json(row["payload_json"])

    def list_recent(self, *, limit: int = 100, event_type: str | None = None) -> list[Observation]:
        """Return recent observations ordered newest first."""

        if limit < 1:
            raise ValueError("limit must be positive")
        with self._lock:
            if event_type is None:
                rows = self._conn.execute(
                    "SELECT payload_json FROM observations ORDER BY observed_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT payload_json FROM observations WHERE event_type = ? ORDER BY observed_at DESC LIMIT ?",
                    (event_type, limit),
                ).fetchall()
        return [Observation.model_validate_json(row["payload_json"]) for row in rows]

    def close(self) -> None:
        """Close the SQLite connection."""

        with self._lock:
            self._conn.close()


class JsonlObservationSink:
    """Append-only JSONL sink with strict recovery and backup rotation."""

    def __init__(
        self,
        path: str | Path,
        *,
        strict: bool = True,
        max_bytes: int = 10 * 1024 * 1024,
        fsync: bool = True,
    ) -> None:
        if max_bytes < 1024:
            raise ValueError("max_bytes must be at least 1024")
        self.path = Path(path)
        self.strict = strict
        self.max_bytes = max_bytes
        self.fsync = fsync
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, observation: Observation) -> None:
        """Validate existing log, rotate if needed, and append one observation."""

        with self._lock:
            self._validate_or_rotate_corrupt()
            self._rotate_if_large()
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(observation.to_json_line())
                fh.flush()
                if self.fsync:
                    os.fsync(fh.fileno())

    async def append_async(self, observation: Observation) -> None:
        """Async wrapper for append, suitable for event-loop callers."""

        await asyncio.to_thread(self.append, observation)

    def iter_observations(self) -> Iterator[Observation]:
        """Yield observations from the current JSONL file."""

        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as fh:
            for line_number, line in enumerate(fh, start=1):
                if not line.strip():
                    continue
                try:
                    yield Observation.model_validate_json(line)
                except Exception as exc:
                    if self.strict:
                        raise JsonlIntegrityError(f"Malformed JSONL at {self.path}:{line_number}: {exc}") from exc

    def _validate_or_rotate_corrupt(self) -> None:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return

        with self.path.open("r", encoding="utf-8") as fh:
            for line_number, line in enumerate(fh, start=1):
                if not line.strip():
                    continue
                try:
                    json.loads(line)
                except json.JSONDecodeError as exc:
                    corrupt_path = self._rotate_corrupt()
                    message = f"Malformed JSONL at {self.path}:{line_number}; rotated to {corrupt_path}"
                    if self.strict:
                        raise JsonlIntegrityError(message, corrupt_path=corrupt_path) from exc
                    return

    def _rotate_corrupt(self) -> Path:
        timestamp = _utc_now().strftime("%Y%m%dT%H%M%S%fZ")
        corrupt_path = self.path.with_name(f"{self.path.name}.corrupt.{timestamp}")
        shutil.move(str(self.path), corrupt_path)
        return corrupt_path

    def _rotate_if_large(self) -> None:
        if not self.path.exists() or self.path.stat().st_size < self.max_bytes:
            return
        timestamp = _utc_now().strftime("%Y%m%dT%H%M%S%fZ")
        rotated = self.path.with_name(f"{self.path.name}.{timestamp}.bak")
        shutil.move(str(self.path), rotated)


class ObservationRecorder:
    """High-level recorder that sanitizes context and dual-writes observations."""

    def __init__(
        self,
        *,
        sqlite_store: SQLiteObservationStore | None = None,
        jsonl_sink: JsonlObservationSink | None = None,
        redactor: SecretRedactor | None = None,
    ) -> None:
        self.sqlite_store = sqlite_store
        self.jsonl_sink = jsonl_sink
        self.redactor = redactor or SecretRedactor()

    def record(
        self,
        event_type: str,
        *,
        context: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
        source: str = "hermes",
        session_id: str | None = None,
        task_id: str | None = None,
        turn_id: str | None = None,
        latency_ms: int | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        error_count: int = 0,
        retry_count: int = 0,
        intent_drift: float | None = None,
        quality_score: float | None = None,
    ) -> Observation:
        """Create, sanitize, persist, and return an observation."""

        sanitized_context = self.redactor.redact(dict(context or {}))
        sanitized_metadata = self.redactor.redact(dict(metadata or {}))
        observation = Observation(
            event_type=event_type,
            source=source,
            session_id=session_id,
            task_id=task_id,
            turn_id=turn_id,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            error_count=error_count,
            retry_count=retry_count,
            intent_drift=intent_drift,
            quality_score=quality_score,
            context_fingerprint=stable_fingerprint(sanitized_context),
            payload=sanitized_context,
            metadata=sanitized_metadata,
        )
        if self.jsonl_sink is not None:
            self.jsonl_sink.append(observation)
        if self.sqlite_store is not None:
            self.sqlite_store.append(observation)
        return observation

    async def record_async(self, event_type: str, **kwargs: Any) -> Observation:
        """Async wrapper for record, suitable for event-loop callers."""

        return await asyncio.to_thread(self.record, event_type, **kwargs)


__all__ = [
    "DEFAULT_SECRET_KEY_PATTERNS",
    "DEFAULT_VOLATILE_KEY_PATTERNS",
    "JsonlIntegrityError",
    "JsonlObservationSink",
    "Observation",
    "ObservationIntegrityError",
    "ObservationRecorder",
    "SecretRedactor",
    "SQLiteObservationStore",
    "stable_fingerprint",
]
