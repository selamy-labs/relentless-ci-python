"""Defect probes for raw mutation status and inventory enforcement."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from quality.mutation_report import Result, verify_results, verify_session

FAILURE = (
    "FAILED tests/test_example.py::test_answer - AssertionError\n1 failed in 0.12s\n"
)


def killed(job_id: str = "one", output: str = FAILURE) -> Result:
    diagnostic = json.dumps({"returncode": 1, "stdout": output, "stderr": ""})
    return Result(job_id, "NORMAL", "KILLED", diagnostic)


def test_accepts_all_planned_test_failures() -> None:
    assert verify_results(["one", "two"], [killed("two"), killed()]) == 2
    assert (
        verify_results(
            ["one"], [killed(output=FAILURE.replace("1 failed", "1 failed, 3 passed"))]
        )
        == 1
    )


@pytest.mark.parametrize("outcome", ["SURVIVED", "INCOMPETENT", "", "unknown"])
def test_rejects_unsuccessful_test_outcomes(outcome: str) -> None:
    with pytest.raises(ValueError, match="worker must finish"):
        verify_results(["one"], [Result("one", "NORMAL", outcome, FAILURE)])


@pytest.mark.parametrize("worker", ["EXCEPTION", "ABNORMAL", "NO_TEST", "SKIPPED", ""])
def test_rejects_inconclusive_workers(worker: str) -> None:
    with pytest.raises(ValueError, match="worker must finish"):
        verify_results(["one"], [Result("one", worker, "KILLED", FAILURE)])


@pytest.mark.parametrize(
    "output", ["timeout", "", "command not found", "1 failed in 0.12s\n"]
)
def test_rejects_kills_without_test_failure_records(output: str) -> None:
    with pytest.raises(ValueError, match="pytest failure record"):
        verify_results(["one"], [killed(output=output)])


@pytest.mark.parametrize(
    "summary",
    [
        "1 error in 0.1s",
        "",
        "1 failed, 1 skipped in 0.1s",
        "1 failed in 0.1s\ntrailing junk",
    ],
)
def test_rejects_errors_or_incomplete_summaries(summary: str) -> None:
    with pytest.raises(ValueError, match="one pytest failure and no errors"):
        verify_results(
            ["one"], [killed(output="FAILED tests/x.py::test_x\n" + summary)]
        )


def test_rejects_one_timeout_among_kills() -> None:
    with pytest.raises(ValueError):
        verify_results(["one", "two"], [killed(), killed("two", "timeout")])


def test_rejects_empty_inventory() -> None:
    with pytest.raises(ValueError, match="inventory is empty"):
        verify_results([], [])


@pytest.mark.parametrize(
    "planned,results",
    [(["one"], []), (["one"], ["two"]), (["one"], ["one", "two"])],
)
def test_rejects_missing_extra_or_unknown_results(
    planned: list[str], results: list[str]
) -> None:
    with pytest.raises(ValueError, match="planned inventory"):
        verify_results(planned, [killed(job_id) for job_id in results])


@pytest.mark.parametrize(
    "planned,results", [(["one", "one"], ["one"]), (["one"], ["one", "one"])]
)
def test_rejects_duplicate_jobs(planned: list[str], results: list[str]) -> None:
    with pytest.raises(ValueError, match="duplicate"):
        verify_results(planned, [killed(job_id) for job_id in results])


DEFAULT_OUTPUT = object()


def create_session(path: Path, output: object = DEFAULT_OUTPUT) -> None:
    if output is DEFAULT_OUTPUT:
        output = killed().output
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE work_items (job_id TEXT)")
        db.execute(
            "CREATE TABLE work_results (job_id TEXT, worker_outcome TEXT, "
            "test_outcome TEXT, output TEXT)"
        )
        db.execute("INSERT INTO work_items VALUES ('one')")
        db.execute(
            "INSERT INTO work_results VALUES ('one', 'NORMAL', 'KILLED', ?)", (output,)
        )


def test_reads_real_sqlite_session(tmp_path: Path) -> None:
    path = tmp_path / "result with spaces.sqlite"
    create_session(path)
    original = path.read_bytes()
    assert verify_session(path) == 1
    assert path.read_bytes() == original


def test_missing_session_fails_without_creating_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.sqlite"
    with pytest.raises(FileNotFoundError):
        verify_session(path)
    assert not path.exists()


def test_malformed_session_fails(tmp_path: Path) -> None:
    path = tmp_path / "result.sqlite"
    create_session(path, None)
    with pytest.raises(ValueError, match="must be strings"):
        verify_session(path)
