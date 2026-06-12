"""Validation checks for Hermes self-improvement Phase 3.

The validator runs fixed safety checks only: Python compilation, pytest, and
SQLite integrity checks for changed database files. It never executes arbitrary
commands from repository data or user-provided shell strings.
"""

from __future__ import annotations

import asyncio
import os
import py_compile
import sqlite3
import sys
import time
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Final
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

_MAX_CAPTURE_CHARS: Final[int] = 20_000
_SQLITE_SUFFIXES: Final[frozenset[str]] = frozenset({".sqlite", ".sqlite3", ".db"})


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _truncate(text: str, *, limit: int = _MAX_CAPTURE_CHARS) -> str:
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return text[:limit] + f"\n...[truncated {omitted} chars]"


class ValidationStatus(StrEnum):
    """Validation check/report status."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ValidationCheck(BaseModel):
    """One validation check result."""

    model_config = ConfigDict(frozen=True)

    name: str
    status: ValidationStatus
    command: tuple[str, ...] | None = None
    duration_ms: int = Field(ge=0)
    stdout: str = ""
    stderr: str = ""
    error: str | None = None

    @field_validator("name")
    @classmethod
    def _name_not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty")
        return value


class ValidationReport(BaseModel):
    """Structured result for a validation run."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: uuid4().hex)
    started_at: datetime
    finished_at: datetime
    status: ValidationStatus
    checks: tuple[ValidationCheck, ...]
    changed_files: tuple[Path, ...]


class Validator:
    """Run fixed validation checks inside one repository root."""

    def __init__(self, repo_path: Path, timeout_s: float = 60.0) -> None:
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        self.repo_path = repo_path.resolve(strict=False)
        self.timeout_s = timeout_s

    async def validate(
        self,
        *,
        changed_files: Iterable[Path],
        run_pytest: bool = True,
        pytest_args: Sequence[str] = ("-q",),
    ) -> ValidationReport:
        """Run compile, pytest, and SQLite integrity checks for changed files."""

        started_at = _utc_now()
        rel_changed_files = tuple(dict.fromkeys(self._relative_path(path) for path in changed_files))
        checks = [
            self._compile_python_files(rel_changed_files),
            await self._run_pytest(run_pytest=run_pytest, pytest_args=pytest_args),
            self._check_sqlite_integrity(rel_changed_files),
        ]
        return ValidationReport(
            started_at=started_at,
            finished_at=_utc_now(),
            status=self._aggregate_status(checks),
            checks=tuple(checks),
            changed_files=rel_changed_files,
        )

    def _relative_path(self, path: Path) -> Path:
        raw_path = Path(path)
        candidate = raw_path if raw_path.is_absolute() else self.repo_path / raw_path
        resolved = candidate.resolve(strict=False)
        if not self._is_relative_to(resolved, self.repo_path):
            raise ValueError(f"path is outside repository root: {path}")
        return resolved.relative_to(self.repo_path)

    @staticmethod
    def _is_relative_to(path: Path, root: Path) -> bool:
        try:
            return os.path.commonpath([str(path), str(root)]) == str(root)
        except ValueError:
            return False

    def _compile_python_files(self, changed_files: Sequence[Path]) -> ValidationCheck:
        started = time.monotonic()
        py_files = [path for path in changed_files if path.suffix == ".py"]
        command = (sys.executable, "-m", "py_compile", *[path.as_posix() for path in py_files]) if py_files else None
        if not py_files:
            return ValidationCheck(
                name="compile_python_files",
                status=ValidationStatus.SKIPPED,
                command=command,
                duration_ms=self._duration_ms(started),
                stdout="",
                stderr="",
                error="no changed Python files",
            )

        errors: list[str] = []
        compiled: list[str] = []
        for rel_path in py_files:
            absolute = self.repo_path / rel_path
            try:
                py_compile.compile(str(absolute), doraise=True)
                compiled.append(rel_path.as_posix())
            except py_compile.PyCompileError as exc:
                errors.append(f"{rel_path}: {exc.msg}")
            except Exception as exc:
                errors.append(f"{rel_path}: {exc}")

        if errors:
            return ValidationCheck(
                name="compile_python_files",
                status=ValidationStatus.FAILED,
                command=command,
                duration_ms=self._duration_ms(started),
                stdout="\n".join(compiled),
                stderr=_truncate("\n".join(errors)),
                error="Python compilation failed",
            )

        return ValidationCheck(
            name="compile_python_files",
            status=ValidationStatus.PASSED,
            command=command,
            duration_ms=self._duration_ms(started),
            stdout="\n".join(compiled),
            stderr="",
            error=None,
        )

    async def _run_pytest(self, *, run_pytest: bool, pytest_args: Sequence[str]) -> ValidationCheck:
        started = time.monotonic()
        command = (sys.executable, "-m", "pytest", *tuple(str(arg) for arg in pytest_args))
        tests_dir = self.repo_path / "tests"
        if not run_pytest:
            return ValidationCheck(
                name="pytest",
                status=ValidationStatus.SKIPPED,
                command=command,
                duration_ms=self._duration_ms(started),
                error="pytest disabled",
            )
        if not tests_dir.exists():
            return ValidationCheck(
                name="pytest",
                status=ValidationStatus.SKIPPED,
                command=command,
                duration_ms=self._duration_ms(started),
                error="tests directory not found",
            )

        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=self.repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=self.timeout_s)
        except TimeoutError:
            process.kill()
            stdout_bytes, stderr_bytes = await process.communicate()
            return ValidationCheck(
                name="pytest",
                status=ValidationStatus.FAILED,
                command=command,
                duration_ms=self._duration_ms(started),
                stdout=_truncate(stdout_bytes.decode("utf-8", errors="replace")),
                stderr=_truncate(stderr_bytes.decode("utf-8", errors="replace")),
                error=f"pytest timed out after {self.timeout_s}s",
            )

        stdout = _truncate(stdout_bytes.decode("utf-8", errors="replace"))
        stderr = _truncate(stderr_bytes.decode("utf-8", errors="replace"))
        if process.returncode == 0:
            status = ValidationStatus.PASSED
            error = None
        else:
            status = ValidationStatus.FAILED
            error = f"pytest exited with status {process.returncode}"

        return ValidationCheck(
            name="pytest",
            status=status,
            command=command,
            duration_ms=self._duration_ms(started),
            stdout=stdout,
            stderr=stderr,
            error=error,
        )

    def _check_sqlite_integrity(self, changed_files: Sequence[Path]) -> ValidationCheck:
        started = time.monotonic()
        sqlite_files = [path for path in changed_files if path.suffix.lower() in _SQLITE_SUFFIXES]
        if not sqlite_files:
            return ValidationCheck(
                name="sqlite_integrity",
                status=ValidationStatus.SKIPPED,
                command=None,
                duration_ms=self._duration_ms(started),
                error="no changed SQLite files",
            )

        ok_messages: list[str] = []
        errors: list[str] = []
        for rel_path in sqlite_files:
            absolute = self.repo_path / rel_path
            try:
                conn = sqlite3.connect(f"file:{absolute}?mode=ro", uri=True)
                try:
                    row = conn.execute("PRAGMA integrity_check").fetchone()
                finally:
                    conn.close()
                message = str(row[0]) if row else "missing integrity_check result"
                if message == "ok":
                    ok_messages.append(f"{rel_path}: ok")
                else:
                    errors.append(f"{rel_path}: {message}")
            except sqlite3.Error as exc:
                errors.append(f"{rel_path}: {exc}")

        if errors:
            return ValidationCheck(
                name="sqlite_integrity",
                status=ValidationStatus.FAILED,
                command=None,
                duration_ms=self._duration_ms(started),
                stdout="\n".join(ok_messages),
                stderr=_truncate("\n".join(errors)),
                error="SQLite integrity check failed",
            )

        return ValidationCheck(
            name="sqlite_integrity",
            status=ValidationStatus.PASSED,
            command=None,
            duration_ms=self._duration_ms(started),
            stdout="\n".join(ok_messages),
            stderr="",
            error=None,
        )

    @staticmethod
    def _aggregate_status(checks: Sequence[ValidationCheck]) -> ValidationStatus:
        if any(check.status is ValidationStatus.FAILED for check in checks):
            return ValidationStatus.FAILED
        if any(check.status is ValidationStatus.PASSED for check in checks):
            return ValidationStatus.PASSED
        return ValidationStatus.SKIPPED

    @staticmethod
    def _duration_ms(started: float) -> int:
        return max(0, int((time.monotonic() - started) * 1000))


__all__ = [
    "ValidationCheck",
    "ValidationReport",
    "ValidationStatus",
    "Validator",
]
