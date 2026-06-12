import sqlite3
from pathlib import Path

import pytest

from selfimprovement.rollback import RollbackManager, RollbackReport, RollbackStatus


def test_creates_backup_for_existing_file_and_restores_content(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "file.txt"
    target.write_text("before", encoding="utf-8")
    manager = RollbackManager(repo, tmp_path / "backups")

    point = manager.create_point(changed_files=[Path("file.txt")])
    target.write_text("after", encoding="utf-8")

    report = manager.restore(point)

    assert isinstance(report, RollbackReport)
    assert report.status is RollbackStatus.PASSED
    assert target.read_text(encoding="utf-8") == "before"
    assert Path("file.txt") in report.restored_files


def test_rollback_deletes_file_missing_at_rollback_point(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    manager = RollbackManager(repo, tmp_path / "backups")

    point = manager.create_point(changed_files=[Path("created_later.txt")])
    (repo / "created_later.txt").write_text("new", encoding="utf-8")

    report = manager.restore(point)

    assert report.status is RollbackStatus.PASSED
    assert not (repo / "created_later.txt").exists()
    assert Path("created_later.txt") in report.deleted_files
    assert "created_later.txt" in point.metadata["missing_files"]


def test_rejects_path_traversal_and_outside_repo_paths(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    manager = RollbackManager(repo, tmp_path / "backups")

    with pytest.raises(ValueError):
        manager.create_point(changed_files=[Path("../outside.txt")])

    outside = tmp_path / "outside.txt"
    outside.write_text("bad", encoding="utf-8")
    with pytest.raises(ValueError):
        manager.create_point(changed_files=[outside])


def test_snapshots_sqlite_db_and_verifies_integrity(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    db_path = repo / "state.sqlite3"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE items(id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO items(name) VALUES ('before')")
    conn.commit()
    conn.close()
    manager = RollbackManager(repo, tmp_path / "backups")

    point = manager.create_point(sqlite_paths=[Path("state.sqlite3")])
    integrity = manager.verify_integrity(point)

    assert integrity.status is RollbackStatus.PASSED
    assert integrity.sqlite_checks[0].ok
    assert integrity.sqlite_checks[0].message == "ok"


def test_restore_sqlite_snapshot(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    db_path = repo / "state.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE items(id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO items(name) VALUES ('before')")
    conn.commit()
    conn.close()
    manager = RollbackManager(repo, tmp_path / "backups")

    point = manager.create_point(sqlite_paths=[Path("state.db")])
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE items SET name = 'after' WHERE id = 1")
    conn.commit()
    conn.close()

    report = manager.restore(point)

    conn = sqlite3.connect(db_path)
    value = conn.execute("SELECT name FROM items WHERE id = 1").fetchone()[0]
    conn.close()
    assert report.status is RollbackStatus.PASSED
    assert value == "before"
    assert Path("state.db") in report.restored_sqlite
