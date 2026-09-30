"""Isolation, fresh-session and restoration probes for mutation orchestration."""

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from quality import mutation
from quality.mutation_services import Worker

FAILURE = (
    "FAILED tests/test_example.py::test_answer - AssertionError\n1 failed in 0.12s\n"
)


@pytest.fixture(autouse=True)
def isolated_transport(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Synthetic SQLite isolates orchestration; native pool has separate probes."""

    def execute(root: Path, timeout: float, env: dict[str, str]) -> list[Worker]:
        mutation.run(
            ["cosmic-ray", "exec", "cosmic-ray.toml", "mutation.sqlite"],
            root,
            timeout,
            env,
        )
        return []

    monkeypatch.setattr(mutation, "execute_pool", execute)
    journal = MagicMock()
    monkeypatch.setattr(mutation, "verify_journals", journal)
    return journal


def repository(root: Path) -> None:
    for directory in ("src", "tests", "quality"):
        (root / directory).mkdir()
        (root / directory / "sample.py").write_text("value = 1\n")
    (root / "src" / "__pycache__").mkdir()
    (root / "src" / "__pycache__" / "junk").write_text("cache")
    for name in (
        "pyproject.toml",
        "cosmic-ray.toml",
        "uv.lock",
        "mise.toml",
        "mise.lock",
    ):
        (root / name).write_text("# configuration\n")
    (root / "quality" / "mutation-timeout.json").write_text("7")
    (root / "quality" / "mutation_trial.py").write_text("raise SystemExit(0)\n")


def session(path: Path) -> None:
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE work_items (job_id TEXT)")
        db.execute(
            "CREATE TABLE work_results (job_id TEXT, worker_outcome TEXT, "
            "test_outcome TEXT, output TEXT)"
        )
        db.execute("INSERT INTO work_items VALUES ('one')")
        db.execute(
            "INSERT INTO work_results VALUES ('one', 'NORMAL', 'KILLED', ?)",
            (json.dumps({"returncode": 1, "stdout": FAILURE, "stderr": ""}),),
        )


def test_mutates_an_isolated_copy_with_fresh_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_transport: MagicMock
) -> None:
    repository(tmp_path)
    received: list[list[str]] = []
    targets: list[Path] = []

    def run(
        arguments: list[str], target: Path, timeout: float, env: dict[str, str]
    ) -> None:
        assert target != tmp_path
        assert timeout == (7 if arguments[1] == "exec" else 5)
        assert env["PYTHONPATH"] == os.pathsep.join([str(target / "src"), str(target)])
        assert env["PYTHONDONTWRITEBYTECODE"] == "1"
        assert env["PYTEST_DEBUG_TEMPROOT"] == str(target / ".quality-results")
        assert mutation.snapshot(target) == mutation.snapshot(tmp_path)
        assert not (target / "src" / "__pycache__").exists()
        received.append(arguments)
        targets.append(target)
        if arguments == ["cosmic-ray", "exec", "cosmic-ray.toml", "mutation.sqlite"]:
            session(target / "mutation.sqlite")

    monkeypatch.setattr(mutation, "run", run)
    assert mutation.mutate(tmp_path, 5) == 1
    isolated_transport.assert_called_once_with(targets[-1], [])
    assert received == [
        ["cosmic-ray", "init", "cosmic-ray.toml", "mutation.sqlite"],
        ["cosmic-ray", "baseline", "cosmic-ray.toml"],
        ["cosmic-ray", "exec", "cosmic-ray.toml", "mutation.sqlite"],
    ]
    assert (tmp_path / ".quality-results" / "mutation.sqlite").is_file()
    assert all(not target.exists() for target in targets)


def change_input(root: Path, target: Path, changed: str) -> None:
    directory = target if changed.startswith("copy") else root
    path = directory / "src" / "sample.py"
    if changed.endswith("policy"):
        path = directory / "cosmic-ray.toml"
    if changed.endswith("timeout"):
        path = directory / "quality" / "mutation-timeout.json"
    path.write_text("changed\n")


@pytest.mark.parametrize(
    "changed",
    [
        "copy",
        "original",
        "copy-policy",
        "original-policy",
        "copy-timeout",
        "original-timeout",
    ],
)
def test_rejects_changed_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed: str
) -> None:
    repository(tmp_path)

    def run(
        arguments: list[str], target: Path, timeout: float, env: dict[str, str]
    ) -> None:
        if arguments[1] == "exec":
            session(target / "mutation.sqlite")
            change_input(tmp_path, target, changed)

    monkeypatch.setattr(mutation, "run", run)
    with pytest.raises(ValueError, match="inputs changed"):
        mutation.mutate(tmp_path, 5)
    assert not (tmp_path / ".quality-results" / "mutation.sqlite").exists()
    assert (tmp_path / ".quality-results" / "mutation-latest.sqlite").exists()


def test_missing_results_cannot_reuse_previous_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository(tmp_path)
    (tmp_path / ".quality-results").mkdir()
    session(tmp_path / ".quality-results" / "mutation.sqlite")

    def no_results(*_arguments: object) -> None:
        return

    monkeypatch.setattr(mutation, "run", no_results)
    with pytest.raises(FileNotFoundError):
        mutation.mutate(tmp_path, 5)


def test_snapshot_includes_never_imported_code_and_policy(tmp_path: Path) -> None:
    repository(tmp_path)
    (tmp_path / "quality" / "unused.py").write_text("unused = 42\n")
    (tmp_path / "quality" / "checks.json").write_text("[]")
    (tmp_path / "quality" / "security.yml").write_text("rules: []")
    files = mutation.snapshot(tmp_path)
    assert files["quality/unused.py"] == b"unused = 42\n"
    assert files["quality/checks.json"] == b"[]"
    assert files["cosmic-ray.toml"] == b"# configuration\n"
    assert files["quality/security.yml"] == b"rules: []"
    assert files["quality/mutation-timeout.json"] == b"7"
    assert len(files) == 13
