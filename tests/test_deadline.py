"""Mutation execution cannot turn malformed configuration into an unbounded run."""

import json
from pathlib import Path

import pytest

from quality import mutation
from quality.deadline import read_deadline
from tests.test_mutation_runner import repository


@pytest.mark.parametrize("value", [0.5, 1, 3600])
def test_native_deadline_values(tmp_path: Path, value: float) -> None:
    path = tmp_path / "deadline.json"
    path.write_text(json.dumps(value))
    assert read_deadline(path) == value


@pytest.mark.parametrize(
    "value", [None, True, False, "3600", [], {}, 0, -1, float("nan"), float("inf")]
)
def test_invalid_execution_deadline_stops_before_tools(
    tmp_path: Path, value: object
) -> None:
    repository(tmp_path)
    (tmp_path / "quality/mutation-timeout.json").write_text(json.dumps(value))
    with pytest.raises(ValueError, match="timeout must be"):
        mutation.mutate(tmp_path, 5)
    assert not (tmp_path / ".quality-results").exists()


def test_missing_execution_deadline_stops_before_tools(tmp_path: Path) -> None:
    repository(tmp_path)
    (tmp_path / "quality/mutation-timeout.json").unlink()
    with pytest.raises(FileNotFoundError):
        mutation.mutate(tmp_path, 5)
