from pathlib import Path

from selfimprovement.modification import FilePatch, ModificationManager, ModificationPlan, ModificationStatus


def test_symbol_replace_writes_to_sandbox_only_by_default(tmp_path: Path):
    repo = tmp_path / "repo"
    sandbox = tmp_path / "sandbox"
    repo.mkdir()
    target = repo / "module.py"
    target.write_text("def greet():\n    return 'old'\n", encoding="utf-8")
    manager = ModificationManager(repo, sandbox)
    plan = ModificationPlan(
        patches=(
            FilePatch(
                path=Path("module.py"),
                kind="python_symbol_replace",
                symbol="greet",
                replacement="def greet():\n    return 'new'\n",
            ),
        )
    )

    report = manager.apply(plan)

    assert report.status is ModificationStatus.PASSED
    assert report.dry_run is True
    assert target.read_text(encoding="utf-8") == "def greet():\n    return 'old'\n"
    sandbox_file = report.patch_results[0].sandbox_path
    assert sandbox_file is not None
    assert "return 'new'" in sandbox_file.read_text(encoding="utf-8")
    assert "-    return 'old'" in report.patch_results[0].diff


def test_non_dry_run_requires_approval(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "module.py"
    target.write_text("def greet():\n    return 'old'\n", encoding="utf-8")
    manager = ModificationManager(repo, tmp_path / "sandbox")
    plan = ModificationPlan(
        dry_run=False,
        requires_approval=True,
        patches=(
            FilePatch(
                path=Path("module.py"),
                kind="python_symbol_replace",
                symbol="greet",
                replacement="def greet():\n    return 'new'\n",
            ),
        ),
    )

    report = manager.apply(plan, approved=False)

    assert report.status is ModificationStatus.FAILED
    assert "requires approval" in report.errors[0]
    assert "old" in target.read_text(encoding="utf-8")


def test_non_dry_run_promotes_validated_sandbox_result(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "module.py"
    target.write_text("def greet():\n    return 'old'\n", encoding="utf-8")
    manager = ModificationManager(repo, tmp_path / "sandbox")
    plan = ModificationPlan(
        dry_run=False,
        requires_approval=True,
        patches=(
            FilePatch(
                path=Path("module.py"),
                kind="python_symbol_replace",
                symbol="greet",
                replacement="def greet():\n    return 'new'\n",
            ),
        ),
    )

    report = manager.apply(plan, approved=True)

    assert report.status is ModificationStatus.PASSED
    assert "return 'new'" in target.read_text(encoding="utf-8")


def test_invalid_replacement_is_rejected(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "module.py").write_text("def greet():\n    return 'old'\n", encoding="utf-8")
    manager = ModificationManager(repo, tmp_path / "sandbox")
    plan = ModificationPlan(
        patches=(
            FilePatch(
                path=Path("module.py"),
                kind="python_symbol_replace",
                symbol="greet",
                replacement="def broken(:\n",
            ),
        )
    )

    report = manager.apply(plan)

    assert report.status is ModificationStatus.FAILED
    assert "invalid Python syntax" in report.errors[0]


def test_missing_symbol_fails(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "module.py").write_text("def greet():\n    return 'old'\n", encoding="utf-8")
    manager = ModificationManager(repo, tmp_path / "sandbox")
    plan = ModificationPlan(
        patches=(
            FilePatch(
                path=Path("module.py"),
                kind="python_symbol_replace",
                symbol="missing",
                replacement="def missing():\n    return 'new'\n",
            ),
        )
    )

    report = manager.apply(plan)

    assert report.status is ModificationStatus.FAILED
    assert "found 0 times" in report.errors[0]


def test_line_patch_disabled_by_default(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "module.py").write_text("x = 1\n", encoding="utf-8")
    manager = ModificationManager(repo, tmp_path / "sandbox")
    plan = ModificationPlan(
        patches=(
            FilePatch(
                path=Path("module.py"),
                kind="line_replace",
                start_line=1,
                end_line=1,
                replacement="x = 2",
            ),
        )
    )

    report = manager.apply(plan)

    assert report.status is ModificationStatus.FAILED
    assert "line_replace is disabled" in report.errors[0]


def test_rejects_outside_repo_path(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("x = 1\n", encoding="utf-8")
    manager = ModificationManager(repo, tmp_path / "sandbox")
    plan = ModificationPlan(
        patches=(
            FilePatch(
                path=outside,
                kind="python_symbol_replace",
                symbol="x",
                replacement="x = 2\n",
            ),
        )
    )

    report = manager.apply(plan)

    assert report.status is ModificationStatus.FAILED
    assert "outside repository root" in report.errors[0]
