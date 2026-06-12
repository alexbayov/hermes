"""Sandboxed code modification primitives for Hermes self-improvement Phase 4.

This module is deliberately narrow: it can prepare and apply small, explicit
patches inside a sandbox first, validate Python syntax with ``ast.parse``, and
then optionally promote the already-validated sandbox result into the repository.
There is no autonomous strategy selection and no orchestration loop here.
"""

from __future__ import annotations

import ast
import difflib
import os
import shutil
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from selfimprovement.rollback import RollbackManager, RollbackPoint

PatchKind = Literal["python_symbol_replace", "text_replace", "line_replace"]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ModificationStatus(StrEnum):
    """Status for a patch or modification run."""

    PLANNED = "planned"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ModificationRisk(StrEnum):
    """Risk level for a modification plan."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FilePatch(BaseModel):
    """One bounded file patch.

    ``python_symbol_replace`` is the preferred mode for Python code. It replaces
    exactly one top-level function, async function, or class by name after
    validating the replacement with ``ast.parse``. ``text_replace`` and
    ``line_replace`` are last-resort modes and require explicit manager opt-in.
    """

    model_config = ConfigDict(frozen=True)

    path: Path
    kind: PatchKind
    replacement: str
    symbol: str | None = None
    expected_old: str | None = None
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    description: str = ""

    @model_validator(mode="after")
    def _validate_shape(self) -> "FilePatch":
        if self.kind == "python_symbol_replace" and not self.symbol:
            raise ValueError("python_symbol_replace requires symbol")
        if self.kind == "text_replace" and self.expected_old is None:
            raise ValueError("text_replace requires expected_old")
        if self.kind == "line_replace":
            if self.start_line is None or self.end_line is None:
                raise ValueError("line_replace requires start_line and end_line")
            if self.end_line < self.start_line:
                raise ValueError("end_line must be >= start_line")
        return self


class ModificationPlan(BaseModel):
    """A dry-run-first modification plan."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: uuid4().hex)
    created_at: datetime = Field(default_factory=_utc_now)
    patches: tuple[FilePatch, ...]
    risk: ModificationRisk = ModificationRisk.MEDIUM
    dry_run: bool = True
    requires_approval: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("patches")
    @classmethod
    def _patches_not_empty(cls, value: tuple[FilePatch, ...]) -> tuple[FilePatch, ...]:
        if not value:
            raise ValueError("modification plan must contain at least one patch")
        return value


class PatchResult(BaseModel):
    """Result for one file patch."""

    path: Path
    kind: PatchKind
    status: ModificationStatus
    diff: str = ""
    sandbox_path: Path | None = None
    error: str | None = None


class ModificationReport(BaseModel):
    """Structured report for a modification plan execution."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    plan_id: str
    started_at: datetime
    finished_at: datetime
    status: ModificationStatus
    dry_run: bool
    sandbox_dir: Path
    changed_files: tuple[Path, ...] = ()
    patch_results: tuple[PatchResult, ...] = ()
    rollback_point: RollbackPoint | None = None
    errors: tuple[str, ...] = ()


class SymbolNotFoundError(ValueError):
    """Raised when a requested Python symbol is not found exactly once."""


class ModificationManager:
    """Apply bounded patches through a sandbox-first workflow."""

    def __init__(
        self,
        repo_path: Path,
        sandbox_root: Path,
        *,
        allow_line_patch: bool = False,
        allow_text_patch: bool = False,
        rollback_manager: RollbackManager | None = None,
    ) -> None:
        self.repo_path = repo_path.resolve(strict=False)
        self.sandbox_root = sandbox_root.resolve(strict=False)
        self.allow_line_patch = allow_line_patch
        self.allow_text_patch = allow_text_patch
        self.rollback_manager = rollback_manager
        self.sandbox_root.mkdir(parents=True, exist_ok=True)

    def apply(self, plan: ModificationPlan, *, approved: bool = False) -> ModificationReport:
        """Apply *plan* in a sandbox and optionally promote it to the repository.

        Plans are dry-run by default. A non-dry-run plan with
        ``requires_approval=True`` is rejected unless ``approved`` is true.
        """

        started_at = _utc_now()
        sandbox_dir = self.sandbox_root / plan.id
        sandbox_dir.mkdir(parents=True, exist_ok=True)
        errors: list[str] = []
        patch_results: list[PatchResult] = []
        changed_files: list[Path] = []
        rollback_point: RollbackPoint | None = None

        if not plan.dry_run and plan.requires_approval and not approved:
            return ModificationReport(
                plan_id=plan.id,
                started_at=started_at,
                finished_at=_utc_now(),
                status=ModificationStatus.FAILED,
                dry_run=plan.dry_run,
                sandbox_dir=sandbox_dir,
                errors=("non-dry-run modification requires approval",),
            )

        try:
            self._validate_plan(plan)
        except Exception as exc:
            return ModificationReport(
                plan_id=plan.id,
                started_at=started_at,
                finished_at=_utc_now(),
                status=ModificationStatus.FAILED,
                dry_run=plan.dry_run,
                sandbox_dir=sandbox_dir,
                errors=(str(exc),),
            )

        for patch in plan.patches:
            rel_path = self._relative_path(patch.path)
            try:
                source_path = self.repo_path / rel_path
                if not source_path.exists():
                    raise FileNotFoundError(f"target file does not exist: {rel_path}")
                original = source_path.read_text(encoding="utf-8")
                modified = self._apply_patch_text(original, patch)
                if modified == original:
                    raise ValueError("patch produced no changes")
                if rel_path.suffix == ".py":
                    self._validate_python_source(modified, rel_path)

                sandbox_path = sandbox_dir / rel_path
                sandbox_path.parent.mkdir(parents=True, exist_ok=True)
                sandbox_path.write_text(modified, encoding="utf-8")
                diff = self._make_diff(original, modified, rel_path)
                changed_files.append(rel_path)
                patch_results.append(
                    PatchResult(
                        path=rel_path,
                        kind=patch.kind,
                        status=ModificationStatus.PASSED,
                        diff=diff,
                        sandbox_path=sandbox_path,
                    )
                )
            except Exception as exc:
                message = f"{patch.path}: {exc}"
                errors.append(message)
                patch_results.append(
                    PatchResult(
                        path=Path(patch.path),
                        kind=patch.kind,
                        status=ModificationStatus.FAILED,
                        error=message,
                    )
                )

        if errors:
            status = ModificationStatus.FAILED
        elif plan.dry_run:
            status = ModificationStatus.PASSED
        else:
            try:
                if self.rollback_manager is not None:
                    rollback_point = self.rollback_manager.create_point(
                        changed_files=changed_files,
                        metadata={"modification_plan_id": plan.id, "phase": "phase4"},
                    )
                for rel_path in changed_files:
                    sandbox_file = sandbox_dir / rel_path
                    target_file = self.repo_path / rel_path
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(sandbox_file, target_file)
                status = ModificationStatus.PASSED
            except Exception as exc:
                status = ModificationStatus.FAILED
                errors.append(f"promotion failed: {exc}")

        return ModificationReport(
            plan_id=plan.id,
            started_at=started_at,
            finished_at=_utc_now(),
            status=status,
            dry_run=plan.dry_run,
            sandbox_dir=sandbox_dir,
            changed_files=tuple(dict.fromkeys(changed_files)),
            patch_results=tuple(patch_results),
            rollback_point=rollback_point,
            errors=tuple(errors),
        )

    def _validate_plan(self, plan: ModificationPlan) -> None:
        if plan.risk in {ModificationRisk.HIGH, ModificationRisk.CRITICAL} and not plan.requires_approval:
            raise ValueError("high-risk modifications must require approval")
        for patch in plan.patches:
            rel_path = self._relative_path(patch.path)
            if patch.kind == "line_replace" and not self.allow_line_patch:
                raise ValueError("line_replace is disabled; AST/symbol patches are preferred")
            if patch.kind == "text_replace" and not self.allow_text_patch:
                raise ValueError("text_replace is disabled; AST/symbol patches are preferred")
            if rel_path.suffix == ".py" and patch.kind != "python_symbol_replace":
                if patch.kind == "line_replace" and not self.allow_line_patch:
                    raise ValueError("line patches for Python require explicit opt-in")
                if patch.kind == "text_replace" and not self.allow_text_patch:
                    raise ValueError("text patches for Python require explicit opt-in")

    def _apply_patch_text(self, original: str, patch: FilePatch) -> str:
        if patch.kind == "python_symbol_replace":
            return self._replace_python_symbol(original, patch)
        if patch.kind == "text_replace":
            return self._replace_text(original, patch)
        if patch.kind == "line_replace":
            return self._replace_lines(original, patch)
        raise ValueError(f"unsupported patch kind: {patch.kind}")

    def _replace_python_symbol(self, original: str, patch: FilePatch) -> str:
        self._validate_python_source(patch.replacement, patch.path)
        tree = ast.parse(original)
        matches: list[ast.AST] = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == patch.symbol:
                matches.append(node)
        if len(matches) != 1:
            raise SymbolNotFoundError(f"symbol {patch.symbol!r} found {len(matches)} times")
        node = matches[0]
        if getattr(node, "end_lineno", None) is None:
            raise ValueError("Python AST does not include end_lineno")
        replacement = patch.replacement.rstrip("\n") + "\n"
        lines = original.splitlines(keepends=True)
        start = int(node.lineno) - 1
        end = int(node.end_lineno)
        return "".join(lines[:start]) + replacement + "".join(lines[end:])

    @staticmethod
    def _replace_text(original: str, patch: FilePatch) -> str:
        assert patch.expected_old is not None
        count = original.count(patch.expected_old)
        if count != 1:
            raise ValueError(f"expected_old must match exactly once, found {count}")
        return original.replace(patch.expected_old, patch.replacement, 1)

    @staticmethod
    def _replace_lines(original: str, patch: FilePatch) -> str:
        assert patch.start_line is not None
        assert patch.end_line is not None
        lines = original.splitlines(keepends=True)
        if patch.end_line > len(lines):
            raise ValueError("line range exceeds file length")
        replacement = patch.replacement.rstrip("\n") + "\n"
        return "".join(lines[: patch.start_line - 1]) + replacement + "".join(lines[patch.end_line :])

    @staticmethod
    def _validate_python_source(source: str, path: Path) -> None:
        try:
            ast.parse(source)
        except SyntaxError as exc:
            raise ValueError(f"invalid Python syntax in {path}: {exc.msg} at line {exc.lineno}") from exc

    @staticmethod
    def _make_diff(original: str, modified: str, rel_path: Path) -> str:
        return "".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                modified.splitlines(keepends=True),
                fromfile=f"a/{rel_path.as_posix()}",
                tofile=f"b/{rel_path.as_posix()}",
            )
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


__all__ = [
    "FilePatch",
    "ModificationManager",
    "ModificationPlan",
    "ModificationReport",
    "ModificationRisk",
    "ModificationStatus",
    "PatchKind",
    "PatchResult",
    "SymbolNotFoundError",
]
