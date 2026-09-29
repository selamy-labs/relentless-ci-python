"""Registry and entry-point failure probes; checks cannot silently disappear."""

import json
import os
import runpy
import subprocess
from pathlib import Path

import pytest

from quality import pipeline


def scope(root: Path) -> list[Path]:
    return [root]


def tracked(_root: Path) -> None:
    return


def registry(root: Path, value: object) -> None:
    (root / "quality").mkdir(exist_ok=True)
    (root / "quality" / "checks.json").write_text(json.dumps(value))
    (root / "quality" / "timeout.json").write_text("5")


@pytest.mark.parametrize("value", [None, {}, [], True, "text"])
def test_rejects_invalid_registries(tmp_path: Path, value: object) -> None:
    registry(tmp_path, value)
    with pytest.raises(ValueError, match="nonempty array"):
        pipeline.checks(tmp_path)


@pytest.mark.parametrize("value", [None, {}, [], True, "text"])
def test_rejects_invalid_commands(tmp_path: Path, value: object) -> None:
    registry(tmp_path, [value])
    with pytest.raises(ValueError, match="argument array"):
        pipeline.checks(tmp_path)


@pytest.mark.parametrize("value", [None, {}, [], True, "", 1])
def test_rejects_invalid_arguments(tmp_path: Path, value: object) -> None:
    registry(tmp_path, [["tool", value]])
    with pytest.raises(ValueError, match="nonempty strings"):
        pipeline.checks(tmp_path)


def test_missing_registry_is_a_failed_check(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        pipeline.checks(tmp_path)


@pytest.mark.parametrize(
    "timeout", [True, None, "5", 0, -1, float("inf"), float("nan")]
)
def test_rejects_unbounded_or_invalid_timeouts(tmp_path: Path, timeout: object) -> None:
    registry(tmp_path, [["first"]])
    (tmp_path / "quality" / "timeout.json").write_text(json.dumps(timeout))
    with pytest.raises(ValueError, match="timeout must be"):
        pipeline.verify(tmp_path)


@pytest.mark.parametrize("timeout", [0.5, 5])
def test_runs_every_command_in_order_then_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, timeout: float
) -> None:
    registry(tmp_path, [["first", "argument with spaces"], ["second"]])
    (tmp_path / "quality" / "timeout.json").write_text(json.dumps(timeout))
    received: list[list[str]] = []
    expected_timeout = timeout

    def command(
        arguments: list[str], root: Path, timeout: float, env: dict[str, str]
    ) -> None:
        assert root == tmp_path
        assert timeout == expected_timeout
        assert env == dict(os.environ)
        received.append(arguments)

    def results(root: Path, sources: list[Path]) -> None:
        assert root == tmp_path
        assert sources == [tmp_path]
        received.append(["test-results"])

    def prepare(root: Path) -> None:
        assert root == tmp_path
        received.append(["prepare-tests"])

    def security(root: Path, timeout: float) -> None:
        assert root == tmp_path
        assert timeout == expected_timeout
        received.append(["security"])

    def mutation(root: Path, timeout: float) -> int:
        assert root == tmp_path
        assert timeout == expected_timeout
        received.append(["mutation"])
        return 1

    monkeypatch.setattr(pipeline, "verify_sources", scope)
    monkeypatch.setattr(pipeline, "verify_tracked", tracked)
    monkeypatch.setattr(pipeline, "run", command)
    monkeypatch.setattr(pipeline, "verify_security", security)
    monkeypatch.setattr(pipeline, "mutate", mutation)
    monkeypatch.setattr(pipeline, "prepare_tests", prepare)
    monkeypatch.setattr(pipeline, "verify_tests", results)
    pipeline.verify(tmp_path)
    assert received == [
        ["prepare-tests"],
        ["first", "argument with spaces"],
        ["second"],
        ["test-results"],
        ["security"],
        ["mutation"],
    ]


def test_failed_command_prevents_later_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry(tmp_path, [["first"], ["second"]])
    received: list[list[str]] = []

    def failure(
        arguments: list[str], root: Path, timeout: float, env: dict[str, str]
    ) -> None:
        received.append(arguments)
        raise subprocess.CalledProcessError(2, arguments)

    monkeypatch.setattr(pipeline, "verify_sources", scope)
    monkeypatch.setattr(pipeline, "verify_tracked", tracked)
    monkeypatch.setattr(pipeline, "run", failure)
    with pytest.raises(subprocess.CalledProcessError):
        pipeline.verify(tmp_path)
    assert received == [["first"]]


def test_module_entry_point_invokes_the_current_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: list[Path] = []
    monkeypatch.setattr(pipeline, "verify", received.append)
    runpy.run_module("quality.verify", run_name="__main__")
    assert received == [Path.cwd()]


def test_invalid_source_scope_prevents_tool_execution(tmp_path: Path) -> None:
    registry(tmp_path, [["absent-tool"]])
    with pytest.raises(ValueError, match="no authored Python"):
        pipeline.verify(tmp_path)
