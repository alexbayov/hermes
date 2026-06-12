import asyncio
import sqlite3
from pathlib import Path

import pytest

from selfimprovement.validation import ValidationStatus, Validator


def run(coro):
    return asyncio.run(coro)


def test_valid_changed_py_file_passes_compile_check(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    py_file = repo / "ok.py"
    py_file.write_text("x = 1\n", encoding="utf-8")

    report = run(Validator(repo).validate(changed_files=[Path("ok.py")], run_pytest=False))

    compile_check = next(check for check in report.checks if check.name == "compile_python_files")
    assert compile_check.status is ValidationStatus.PASSED
    assert report.status is ValidationStatus.PASSED


def test_invalid_changed_py_file_fails_compile_without_traceback(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    py_file = repo / "bad.py"
    py_file.write_text("def broken(:\n", encoding="utf-8")

    report = run(Validator(repo).validate(changed_files=[Path("bad.py")], run_pytest=False))

    compile_check = next(check for check in report.checks if check.name == "compile_python_files")
    assert compile_check.status is ValidationStatus.FAILED
    assert compile_check.error == "Python compilation failed"
    assert "Traceback" not in compile_check.stderr
    assert report.status is ValidationStatus.FAILED


def test_no_tests_directory_makes_pytest_skipped(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()

    report = run(Validator(repo).validate(changed_files=[], run_pytest=True))

    pytest_check = next(check for check in report.checks if check.name == "pytest")
    assert pytest_check.status is ValidationStatus.SKIPPED
    assert report.status is ValidationStatus.SKIPPED


def test_sqlite_integrity_check_passes_on_valid_db(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    db_path = repo / "state.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE items(id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    report = run(Validator(repo).validate(changed_files=[Path("state.sqlite")], run_pytest=False))

    sqlite_check = next(check for check in report.checks if check.name == "sqlite_integrity")
    assert sqlite_check.status is ValidationStatus.PASSED
    assert "state.sqlite: ok" in sqlite_check.stdout
    assert report.status is ValidationStatus.PASSED


def test_outside_repo_path_is_rejected(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("x = 1\n", encoding="utf-8")

    with pytest.raises(ValueError):
        run(Validator(repo).validate(changed_files=[outside], run_pytest=False))


def test_report_aggregation_skipped_when_all_checks_skipped(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()

    report = run(Validator(repo).validate(changed_files=[], run_pytest=False))

    assert report.status is ValidationStatus.SKIPPED
    assert all(check.status is ValidationStatus.SKIPPED for check in report.checks)
