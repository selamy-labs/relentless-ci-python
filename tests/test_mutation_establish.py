"""The coordinator validates every planned selection in owned pristine copies."""

import json
import runpy
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from quality import mutation_pristine as pristine
from quality.mutation_inputs import environment
from quality.owned_commands import OwnedCommand

FIRST, SECOND, THIRD = ["tests/a.py::test_a"], ["tests/b.py::test_b"], ["tests/c.py"]


def shard_root(root: Path, shard: list[list[str]], timeout: str = "7.5") -> Path:
    (root / ".quality-results").mkdir()
    (root / pristine.SHARD).write_text(json.dumps(shard), encoding="utf-8")
    config = f"[cosmic-ray]\ntimeout = {timeout}\n"
    (root / "cosmic-ray.toml").write_text(config, encoding="utf-8")
    return root


def passed(root: Path) -> object:
    return json.loads((root / pristine.PASSED).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "status,stderr,expected",
    [(0, "", True), (1, "", False), (5, "", False), (-9, "", False), (0, "x\n", False)],
)
def test_only_clean_pristine_status_validates_a_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    stderr: str,
    expected: bool,
) -> None:
    seen: list[tuple[list[str], dict[str, object]]] = []

    def run(command: list[str], **options: object) -> subprocess.CompletedProcess[str]:
        seen.append((command, options))
        return subprocess.CompletedProcess(command, status, "", stderr)

    monkeypatch.setattr(subprocess, "run", run)
    pristine.run_shard(shard_root(tmp_path, [FIRST, SECOND]))
    assert passed(tmp_path) == ([FIRST, SECOND] if expected else [])
    options = {"capture_output": True, "text": True, "check": False, "timeout": 7.5}
    prefix = [sys.executable, "-m", "pytest", "-x", "-q", "--color=no"]
    assert seen == [([*prefix, *FIRST], options), ([*prefix, *SECOND], options)]


@pytest.mark.parametrize(
    "error", [subprocess.TimeoutExpired("pytest", 7.5), FileNotFoundError("python")]
)
def test_timed_out_or_unlaunchable_selection_is_not_validated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def run(command: list[str], **_options: object) -> subprocess.CompletedProcess[str]:
        if command[-1] == FIRST[0]:
            raise error
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    pristine.run_shard(shard_root(tmp_path, [FIRST, SECOND], "60"))
    assert passed(tmp_path) == [SECOND]
    assert pristine.trial_limit(tmp_path) == 60.0


def test_shard_entry_point_runs_in_its_own_working_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shard = MagicMock()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pristine, "run_shard", shard)
    runpy.run_module("quality.mutation_pristine_main", run_name="__main__")
    shard.assert_called_once_with(tmp_path)


def test_merged_credit_is_sorted_and_written_only_by_the_coordinator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        pristine, "planned", MagicMock(return_value=[FIRST, SECOND, THIRD])
    )
    monkeypatch.setattr(pristine, "worker_count", lambda: 2)
    monkeypatch.setattr(pristine, "copy_inputs", MagicMock())
    (tmp_path / ".quality-results").mkdir()
    copies = [tmp_path / f".quality-results/mutation-pristine-{n}" for n in (0, 1)]
    shards: list[object] = []

    def run(root: Path, paths: list[Path], timeout: float, env: object) -> None:
        assert (root, paths, timeout, env) == (tmp_path, copies, 9, {"KEEP": "1"})
        shards.extend(json.loads((path / pristine.SHARD).read_text()) for path in paths)
        for path, value in zip(paths, ([THIRD, FIRST], [SECOND]), strict=True):
            (path / pristine.PASSED).write_text(json.dumps(value), encoding="utf-8")

    monkeypatch.setattr(pristine, "run_shards", run)
    encoded = pristine.establish(tmp_path, 9, {"KEEP": "1"})
    assert shards == [[FIRST, THIRD], [SECOND]]
    assert json.loads(encoded) == [FIRST, SECOND, THIRD]
    assert (
        tmp_path / ".quality-results/mutation-pristine.json"
    ).read_bytes() == encoded


def owned_handle(name: str) -> OwnedCommand:
    return OwnedCommand((name,), 1, MagicMock(), Path(name), name, Path(name))


def test_every_started_shard_is_finished_and_every_failure_retained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handles = [owned_handle("a"), owned_handle("b")]
    started = MagicMock(side_effect=[*handles, KeyboardInterrupt()])
    finished = MagicMock(side_effect=[OSError("a"), None])
    monkeypatch.setattr(pristine, "start_owned", started)
    monkeypatch.setattr(pristine, "finish_owned", finished)
    monkeypatch.setattr(pristine, "snapshot", MagicMock(return_value={}))
    copies = [tmp_path / name for name in ("a", "b", "c")]
    with pytest.raises(BaseExceptionGroup) as raised:
        pristine.run_shards(tmp_path, copies, 30, {"KEEP": "1"})
    assert [type(error) for error in raised.value.exceptions] == [
        KeyboardInterrupt,
        OSError,
    ]
    arguments = [sys.executable, "-m", "quality.mutation_pristine_main"]
    assert started.call_args_list == [
        call(arguments, copy, 30, environment(copy, {"KEEP": "1"})) for copy in copies
    ]
    assert finished.call_args_list == [call(handle, 30) for handle in handles]


@pytest.mark.parametrize("changed", [0, 1])
def test_a_shard_that_changes_inputs_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed: int
) -> None:
    copies = [tmp_path / "a", tmp_path / "b"]
    states = {
        tmp_path: {"src/x.py": b"1"},
        **{copy: {"src/x.py": b"1"} for copy in copies},
    }
    states[copies[changed]] = {"src/x.py": b"2"}
    monkeypatch.setattr(pristine, "snapshot", states.__getitem__)
    monkeypatch.setattr(pristine, "start_owned", MagicMock())
    monkeypatch.setattr(pristine, "finish_owned", MagicMock())
    with pytest.raises(ValueError, match="pristine selection inputs changed"):
        pristine.run_shards(tmp_path, copies, 30, {})
    pristine.run_shards(tmp_path, [], 30, {})
