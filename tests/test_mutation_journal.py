"""Missing/extra/duplicated jobs and changed worker trial policy cannot pass."""

import json
import sqlite3
from contextlib import closing
from http import HTTPStatus
from pathlib import Path

import pytest

from quality.mutation_journal import (
    request_signatures,
    require_unique_plan,
    signature,
    verify_journals,
    worker_requests,
)
from tests.test_mutation_services import instance


def request(module: str = "src/product.py", occurrence: int = 7) -> dict[str, object]:
    return {
        "status": 200,
        "request": {
            "test_command": "python -m pytest -x -q",
            "timeout": 30,
            "mutations": [
                {
                    "module_path": module,
                    "operator": "native-operator",
                    "occurrence": occurrence,
                }
            ],
        },
    }


@pytest.mark.parametrize("fault", ["status", "command", "deadline", "empty"])
def test_changed_policy_or_empty_mutations_fail(fault: str) -> None:
    fields: dict[str, object] = {
        "test_command": "changed" if fault == "command" else "python -m pytest -x -q",
        "timeout": 29 if fault == "deadline" else 30,
        "mutations": (
            []
            if fault == "empty"
            else [
                {
                    "module_path": "src/product.py",
                    "operator": "native-operator",
                    "occurrence": 7,
                }
            ]
        ),
    }
    value = {"status": 201 if fault == "status" else 200, "request": fields}
    with pytest.raises(ValueError):
        request_signatures(value, "python -m pytest -x -q", 30)


@pytest.mark.parametrize("value", [True, 7.5, "7"])
def test_occurrence_cannot_be_coerced(value: object) -> None:
    with pytest.raises(ValueError):
        signature(
            {
                "module_path": "src/product.py",
                "operator": "native-operator",
                "occurrence": value,
            }
        )


def test_http_status_enum_has_the_same_numeric_semantics() -> None:
    value = request()
    value["status"] = HTTPStatus.OK
    assert request_signatures(value, "python -m pytest -x -q", 30) == [
        ("src/product.py", "native-operator", 7)
    ]


@pytest.mark.parametrize("status", [199, 201])
def test_every_non_success_status_fails_on_both_sides(status: int) -> None:
    value = request()
    value["status"] = status

    with pytest.raises(ValueError, match="not successful"):
        request_signatures(value, "python -m pytest -x -q", 30)


@pytest.mark.parametrize("command", ["a", "z"])
def test_different_trial_command_fails_on_both_sides(command: str) -> None:
    value: dict[str, object] = {
        "status": 200,
        "request": {"test_command": command, "timeout": 30, "mutations": []},
    }

    with pytest.raises(ValueError, match="trial policy"):
        request_signatures(value, "python -m pytest -x -q", 30)


@pytest.mark.parametrize("timeout", [29, 31])
def test_different_trial_deadline_fails_on_both_sides(timeout: int) -> None:
    value: dict[str, object] = {
        "status": 200,
        "request": {
            "test_command": "python -m pytest -x -q",
            "timeout": timeout,
            "mutations": [],
        },
    }

    with pytest.raises(ValueError, match="trial policy"):
        request_signatures(value, "python -m pytest -x -q", 30)


def test_equal_independently_constructed_trial_values_pass() -> None:
    command = "".join(["python", " -m pytest -x -q"])

    assert request_signatures(request(), command, float("30")) == [
        ("src/product.py", "native-operator", 7)
    ]


@pytest.mark.parametrize("signatures", [[], [("src/a.py", "op", 1)] * 2])
def test_native_plan_signatures_must_be_nonempty_and_unique(
    signatures: list[tuple[str, str, int]],
) -> None:
    with pytest.raises(ValueError, match="complete native plan"):
        require_unique_plan(signatures)


def test_large_complete_native_inventory_has_value_equality(tmp_path: Path) -> None:
    worker = instance(tmp_path / "worker")
    (tmp_path / "cosmic-ray.toml").write_text(
        '[cosmic-ray]\ntest-command="python -m pytest -x -q"\ntimeout=30\n'
    )
    with closing(sqlite3.connect(tmp_path / "mutation.sqlite")) as db, db:
        db.execute("CREATE TABLE mutation_specs(module_path,operator_name,occurrence)")
        db.executemany(
            "INSERT INTO mutation_specs VALUES(?,?,?)",
            [("src/product.py", "native-operator", index) for index in range(257)],
        )
    (worker.root / ".quality-results/worker-jobs.jsonl").write_text(
        "".join(json.dumps(request(occurrence=index)) + "\n" for index in range(257))
    )
    verify_journals(tmp_path, [worker])


def test_missing_or_empty_journal_fails(tmp_path: Path) -> None:
    worker = instance(tmp_path)
    with pytest.raises(FileNotFoundError):
        worker_requests(worker, "python -m pytest -x -q", 30)
    (tmp_path / ".quality-results/worker-jobs.jsonl").write_text("")
    with pytest.raises(ValueError, match="empty"):
        worker_requests(worker, "python -m pytest -x -q", 30)


@pytest.mark.parametrize("fault", ["clean", "duplicate", "missing", "extra", "no-plan"])
def test_exact_complete_native_plan_is_required(tmp_path: Path, fault: str) -> None:
    first, second = instance(tmp_path / "first"), instance(tmp_path / "second")
    (tmp_path / "cosmic-ray.toml").write_text(
        '[cosmic-ray]\ntest-command="python -m pytest -x -q"\ntimeout=30\n'
    )
    create_plan(tmp_path / "mutation.sqlite", fault != "no-plan")
    variants = {
        "clean": ([request()], [request(occurrence=8)]),
        "duplicate": ([request()], [request()]),
        "missing": ([request(occurrence=6)], [request()]),
        "extra": ([request()], [request(occurrence=8), request(occurrence=9)]),
        "no-plan": ([request()], [request(occurrence=8)]),
    }
    one, two = variants[fault]
    for worker, rows in ((first, one), (second, two)):
        (worker.root / ".quality-results/worker-jobs.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows)
        )
    if fault == "clean":
        verify_journals(tmp_path, [first, second])
    else:
        with pytest.raises(ValueError, match="complete native plan"):
            verify_journals(tmp_path, [first, second])


def create_plan(path: Path, populated: bool) -> None:
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE mutation_specs(module_path,operator_name,occurrence)")
        if populated:
            db.executemany(
                "INSERT INTO mutation_specs VALUES(?,?,?)",
                [
                    ("src/product.py", "native-operator", 7),
                    ("src/product.py", "native-operator", 8),
                ],
            )
