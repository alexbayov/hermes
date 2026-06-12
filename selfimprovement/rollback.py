"""Rollback primitives for Hermes self-improvement Phase 3.

The manager creates explicit rollback points for files and SQLite databases before
later phases are allowed to mutate anything. It is intentionally conservative:
all paths must resolve under the configured repository root and reports are
structured Pydantic models rather than free-form strings.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

RollbackKind = Literal["files", "sqlite", "config", "git"]
_MISSING_SENTINEL = "__MISSING_BEFORE_ROLLBACK__"


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RollbackStatus(StrEnum):
    """Overall rollback operation status."""

    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"


class RollbackPoint(BaseModel):
    """Snapshot metadata needed to restore repository state."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str = Field(default_factory=lambda: uuid4().hex)
    created_at: datetime = Field(default_factory=_utc_now)
    repo_path: Path
    backup_dir: Path
    changed_files: tuple[Path, ...] = ()
    file_backups: dict[str, Path] = Field(default_factory=dict)
    sqlite_snapshots: dict[str, Path] = Field(default_factory=dict)
    git_commit: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("created_at")
    @classmethod
    def _ensure_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class RollbackFileResult(BaseModel):
    """Result for one restored or deleted path."""

    path: Path
    kind: RollbackKind
    restored: bool = False
    deleted: bool = False
    error: str | None = None


class RollbackReport(BaseModel):
    """Structured result of a rollback restore operation."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    rollback_point_id: str
    started_at: datetime = Field(default_factory=_utc_now)
    finished_at: datetime
    status: RollbackStatus
    restored_files: tuple[Path, ...] = ()
    deleted_files: tuple[Path, ...] = ()
    restored_sqlite: tuple[Path, ...] = ()
    results: tuple[RollbackFileResult, ...] = ()
    errors: tuple[str, ...] = ()


class SQLiteIntegrityResult(BaseModel):
    """SQLite snapshot integrity-check result."""

    path: Path
    ok: bool
    message: str


class RollbackIntegrityReport(BaseModel):
    """Structured verification report for a rollback point."""

    rollback_point_id: str
    status: RollbackStatus
    missing_file_backups: tuple[Path, ...] = ()
    sqlite_checks: tuple[SQLiteIntegrityResult, ...] = ()
    errors: tuple[str, ...] = ()


class RollbackManager:
    """Create and restore file/SQLite rollback points under one repository root."""

    def __init__(self, repo_path: Path, backup_dir: Path) -> None:
        self.repo_path = repo_path.resolve(strict=False)
        self.backup_dir = backup_dir.resolve(strict=False)
        self.repo_path.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_point(
        self,
        *,
        changed_files: Iterable[Path] = (),
        sqlite_paths: Iterable[Path] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> RollbackPoint:
        """Create a rollback point for files and SQLite databases.

        Missing changed files are recorded explicitly. If they appear later,
        restore deletes them to return to the captured state.
        """

        point_id = uuid4().hex
        point_dir = self.backup_dir / point_id
        file_dir = point_dir / "files"
        sqlite_dir = point_dir / "sqlite"
        file_dir.mkdir(parents=True, exist_ok=True)
        sqlite_dir.mkdir(parents=True, exist_ok=True)

        changed_rel = tuple(dict.fromkeys(self._relative_path(path) for path in changed_files))
        sqlite_rel = tuple(dict.fromkeys(self._relative_path(path) for path in sqlite_paths))
        file_backups: dict[str, Path] = {}
        missing_files: list[str] = []

        for rel_path in changed_rel:
            source = self.repo_path / rel_path
            rel_key = rel_path.as_posix()
            if not source.exists():
                file_backups[rel_key] = Path(_MISSING_SENTINEL)
                missing_files.append(rel_key)
                continue

            destination = file_dir / rel_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            self._copy_path(source, destination)
            file_backups[rel_key] = destination

        sqlite_snapshots: dict[str, Path] = {}
        for rel_path in sqlite_rel:
            source = self.repo_path / rel_path
            if not source.exists():
                continue
            destination = sqlite_dir / rel_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            self._snapshot_sqlite(source, destination)
            sqlite_snapshots[rel_path.as_posix()] = destination

        combined_metadata = dict(metadata or {})
        combined_metadata["missing_files"] = missing_files
        combined_metadata["sqlite_paths"] = [path.as_posix() for path in sqlite_rel]

        return RollbackPoint(
            id=point_id,
            repo_path=self.repo_path,
            backup_dir=point_dir,
            changed_files=changed_rel,
            file_backups=file_backups,
            sqlite_snapshots=sqlite_snapshots,
            git_commit=None,
            metadata=combined_metadata,
        )

    def restore(self, point: RollbackPoint) -> RollbackReport:
        """Restore files and SQLite databases captured by *point*."""

        started_at = _utc_now()
        errors: list[str] = []
        results: list[RollbackFileResult] = []
        restored_files: list[Path] = []
        deleted_files: list[Path] = []
        restored_sqlite: list[Path] = []
        missing_files = set(str(item) for item in point.metadata.get("missing_files", []))

        self._validate_point(point)

        for rel_path in point.changed_files:
            try:
                rel = self._relative_path(rel_path)
                rel_key = rel.as_posix()
                target = self.repo_path / rel

                if rel_key in missing_files:
                    if target.exists() or target.is_symlink():
                        self._remove_path(target)
                        deleted_files.append(rel)
                        results.append(RollbackFileResult(path=rel, kind="files", deleted=True))
                    else:
                        results.append(RollbackFileResult(path=rel, kind="files"))
                    continue

                backup = point.file_backups.get(rel_key)
                if backup is None:
                    raise FileNotFoundError(f"No backup recorded for {rel_key}")
                backup_path = self._backup_path(backup, point)
                if not backup_path.exists():
                    raise FileNotFoundError(f"Backup does not exist for {rel_key}: {backup_path}")

                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() or target.is_symlink():
                    self._remove_path(target)
                self._copy_path(backup_path, target)
                restored_files.append(rel)
                results.append(RollbackFileResult(path=rel, kind="files", restored=True))
            except Exception as exc:
                message = f"failed to restore {rel_path}: {exc}"
                errors.append(message)
                results.append(RollbackFileResult(path=Path(rel_path), kind="files", error=message))

        for rel_key, snapshot in point.sqlite_snapshots.items():
            try:
                rel = self._relative_path(Path(rel_key))
                snapshot_path = self._backup_path(snapshot, point)
                target = self.repo_path / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                self._restore_sqlite(snapshot_path, target)
                restored_sqlite.append(rel)
                results.append(RollbackFileResult(path=rel, kind="sqlite", restored=True))
            except Exception as exc:
                message = f"failed to restore sqlite {rel_key}: {exc}"
                errors.append(message)
                results.append(RollbackFileResult(path=Path(rel_key), kind="sqlite", error=message))

        if errors and (restored_files or deleted_files or restored_sqlite):
            status = RollbackStatus.PARTIAL
        elif errors:
            status = RollbackStatus.FAILED
        else:
            status = RollbackStatus.PASSED

        return RollbackReport(
            rollback_point_id=point.id,
            started_at=started_at,
            finished_at=_utc_now(),
            status=status,
            restored_files=tuple(restored_files),
            deleted_files=tuple(deleted_files),
            restored_sqlite=tuple(restored_sqlite),
            results=tuple(results),
            errors=tuple(errors),
        )

    def verify_integrity(self, point: RollbackPoint) -> RollbackIntegrityReport:
        """Verify file backups and SQLite snapshot integrity for *point*."""

        self._validate_point(point)
        errors: list[str] = []
        missing_file_backups: list[Path] = []
        sqlite_checks: list[SQLiteIntegrityResult] = []
        missing_files = set(str(item) for item in point.metadata.get("missing_files", []))

        for rel_key, backup in point.file_backups.items():
            if rel_key in missing_files or str(backup) == _MISSING_SENTINEL:
                continue
            try:
                backup_path = self._backup_path(backup, point)
                if not backup_path.exists():
                    missing_file_backups.append(Path(rel_key))
            except Exception as exc:
                missing_file_backups.append(Path(rel_key))
                errors.append(str(exc))

        for rel_key, snapshot in point.sqlite_snapshots.items():
            try:
                snapshot_path = self._backup_path(snapshot, point)
                message = self._sqlite_integrity_message(snapshot_path)
                sqlite_checks.append(SQLiteIntegrityResult(path=Path(rel_key), ok=message == "ok", message=message))
                if message != "ok":
                    errors.append(f"SQLite snapshot {rel_key} failed integrity check: {message}")
            except Exception as exc:
                sqlite_checks.append(SQLiteIntegrityResult(path=Path(rel_key), ok=False, message=str(exc)))
                errors.append(str(exc))

        status = RollbackStatus.PASSED if not errors and not missing_file_backups else RollbackStatus.FAILED
        return RollbackIntegrityReport(
            rollback_point_id=point.id,
            status=status,
            missing_file_backups=tuple(missing_file_backups),
            sqlite_checks=tuple(sqlite_checks),
            errors=tuple(errors),
        )

    def _validate_point(self, point: RollbackPoint) -> None:
        if point.repo_path.resolve(strict=False) != self.repo_path:
            raise ValueError("rollback point belongs to a different repository root")
        point_backup_dir = point.backup_dir.resolve(strict=False)
        if not self._is_relative_to(point_backup_dir, self.backup_dir):
            raise ValueError("rollback point backup directory is outside configured backup root")

    def _relative_path(self, path: Path) -> Path:
        raw_path = Path(path)
        candidate = raw_path if raw_path.is_absolute() else self.repo_path / raw_path
        resolved = candidate.resolve(strict=False)
        if not self._is_relative_to(resolved, self.repo_path):
            raise ValueError(f"path is outside repository root: {path}")
        return resolved.relative_to(self.repo_path)

    def _backup_path(self, path: Path, point: RollbackPoint) -> Path:
        if str(path) == _MISSING_SENTINEL:
            return Path(_MISSING_SENTINEL)
        resolved = Path(path).resolve(strict=False)
        if not self._is_relative_to(resolved, point.backup_dir.resolve(strict=False)):
            raise ValueError(f"backup path is outside rollback point directory: {path}")
        return resolved

    @staticmethod
    def _is_relative_to(path: Path, root: Path) -> bool:
        try:
            return os.path.commonpath([str(path), str(root)]) == str(root)
        except ValueError:
            return False

    @staticmethod
    def _copy_path(source: Path, destination: Path) -> None:
        if source.is_dir() and not source.is_symlink():
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination, follow_symlinks=False)

    @staticmethod
    def _remove_path(path: Path) -> None:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)

    @staticmethod
    def _snapshot_sqlite(source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        source_conn = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
        try:
            dest_conn = sqlite3.connect(destination)
            try:
                source_conn.backup(dest_conn)
            finally:
                dest_conn.close()
        finally:
            source_conn.close()

    @staticmethod
    def _restore_sqlite(snapshot: Path, target: Path) -> None:
        source_conn = sqlite3.connect(f"file:{snapshot}?mode=ro", uri=True)
        try:
            dest_conn = sqlite3.connect(target)
            try:
                source_conn.backup(dest_conn)
            finally:
                dest_conn.close()
        finally:
            source_conn.close()

    @staticmethod
    def _sqlite_integrity_message(path: Path) -> str:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
            return str(row[0]) if row else "missing integrity_check result"
        finally:
            conn.close()


__all__ = [
    "RollbackIntegrityReport",
    "RollbackKind",
    "RollbackManager",
    "RollbackPoint",
    "RollbackReport",
    "RollbackStatus",
    "SQLiteIntegrityResult",
]
