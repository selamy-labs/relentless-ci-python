"""Trial diagnostics preserve status and streams without changing test selection."""

import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

from quality.trial_launcher import launcher_path, prepare_launcher, require_launcher
from quality.trial_report import trial_stdout

FAILURE = "FAILED tests/x.py::test_x\n1 failed in 0.12s\n"


@pytest.mark.parametrize("status", [0, 1, 2, -9])
@pytest.mark.parametrize("stderr", ["", "runtime diagnostic\n"])
def test_trial_retains_actual_signed_status_and_both_streams(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    status: int,
    stderr: str,
) -> None:
    def completed(
        command: list[str], *, capture_output: bool, text: bool, check: bool
    ) -> subprocess.CompletedProcess[str]:
        assert command == [sys.executable, "-m", "pytest", "-x", "-q", "--color=no"]
        assert capture_output is True
        assert text is True
        assert check is False
        return subprocess.CompletedProcess(command, status, "actual stdout\n", stderr)

    monkeypatch.setattr(subprocess, "run", completed)

    from quality import mutation_trial

    exit_status = mutation_trial.run_trial()

    assert exit_status == (2 if stderr else status)
    captured = capsys.readouterr()
    assert captured.err == ""
    assert (
        captured.out
        == json.dumps(
            {"returncode": status, "stdout": "actual stdout\n", "stderr": stderr}
        )
        + "\n"
    )


def test_trial_launch_error_cannot_emit_a_completed_record(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def unavailable(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError("pytest executable unavailable")

    monkeypatch.setattr(subprocess, "run", unavailable)

    from quality import mutation_trial

    with pytest.raises(FileNotFoundError, match="executable unavailable"):
        mutation_trial.run_trial()

    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("status", [0, 1, 2, -9])
def test_trial_entry_propagates_exact_adapter_status(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    def completed(
        command: list[str], **_options: bool
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, status, "", "")

    monkeypatch.setattr(subprocess, "run", completed)
    monkeypatch.delitem(sys.modules, "quality.mutation_trial", raising=False)

    from quality.trial_launcher import prepare_launcher

    root = Path(__file__).resolve().parents[1]
    prepare_launcher(root)
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(launcher_path(root)), run_name="__main__")

    assert stopped.value.code == status


@pytest.mark.parametrize("name", ["A", "quality.mutation_trial"])
def test_importing_trial_module_has_no_process_or_output_side_effects(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    name: str,
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("importing a library must not launch pytest")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.delitem(sys.modules, "quality.mutation_trial", raising=False)

    namespace = runpy.run_module("quality.mutation_trial", run_name=name)

    assert callable(namespace["run_trial"])
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def diagnostic(**changes: object) -> str:
    value: dict[str, object] = {"returncode": 1, "stdout": FAILURE, "stderr": ""}
    value.update(changes)
    return json.dumps(value)


def test_trial_record_preserves_the_complete_original_stdout() -> None:
    assert trial_stdout(diagnostic()) == FAILURE
    assert trial_stdout(diagnostic(stdout="")) == ""


@pytest.mark.parametrize("status", [0, 2, -1, -9, True, False, 1.0, "1", None])
def test_trial_record_rejects_non_failure_or_malformed_status(status: object) -> None:
    with pytest.raises(ValueError):
        trial_stdout(diagnostic(returncode=status))


@pytest.mark.parametrize("stderr", ["warning\n", " ", 0, False, None, []])
def test_trial_record_rejects_diagnostics_or_malformed_stderr(stderr: object) -> None:
    with pytest.raises(ValueError):
        trial_stdout(diagnostic(stderr=stderr))


@pytest.mark.parametrize("stdout", [0, False, None, []])
def test_trial_record_rejects_malformed_stdout(stdout: object) -> None:
    with pytest.raises(ValueError, match="streams must be strings"):
        trial_stdout(diagnostic(stdout=stdout))


@pytest.mark.parametrize("field", ["returncode", "stdout", "stderr"])
def test_trial_record_requires_every_diagnostic_field(field: str) -> None:
    value = json.loads(diagnostic())
    del value[field]

    with pytest.raises(ValueError, match="fields are incomplete"):
        trial_stdout(json.dumps(value))


@pytest.mark.parametrize(
    "output", ["timeout", "", "{}", "[]", "null", "1", '"raw pytest output"']
)
def test_trial_record_rejects_missing_or_unstructured_output(output: str) -> None:
    with pytest.raises(ValueError):
        trial_stdout(output)


def test_trial_record_rejects_unknown_fields_and_duplicate_json_keys() -> None:
    with pytest.raises(ValueError, match="fields are incomplete"):
        trial_stdout(diagnostic(extra="unaccounted"))
    duplicate = diagnostic()[:-1] + ',"returncode":1}'
    with pytest.raises(ValueError, match="duplicate"):
        trial_stdout(duplicate)
    with pytest.raises(ValueError):
        trial_stdout(diagnostic() + "unaccounted trailing text")


@pytest.mark.parametrize("preexisting", [False, True])
def test_launcher_is_reproduced_from_current_source_and_replaces_stale_bytes(
    tmp_path: Path, preexisting: bool
) -> None:
    (tmp_path / "quality").mkdir()
    source = tmp_path / "quality/mutation_trial.py"
    source.write_bytes(b"current source\n")
    if preexisting:
        launcher_path(tmp_path).parent.mkdir()
        launcher_path(tmp_path).write_bytes(b"stale launcher\n")

    expected = prepare_launcher(tmp_path)

    assert expected == b"current source\n\nraise SystemExit(run_trial())\n"
    assert launcher_path(tmp_path).read_bytes() == expected
    require_launcher(tmp_path, expected)
    source.write_bytes(b"candidate mutation\n")
    require_launcher(tmp_path, expected)
    launcher_path(tmp_path).write_bytes(b"tampered launcher\n")
    with pytest.raises(ValueError, match="launcher changed"):
        require_launcher(tmp_path, expected)
    launcher_path(tmp_path).unlink()
    with pytest.raises(FileNotFoundError):
        require_launcher(tmp_path, expected)


def test_missing_launcher_source_cannot_reuse_existing_runtime_copy(
    tmp_path: Path,
) -> None:
    launcher_path(tmp_path).parent.mkdir()
    launcher_path(tmp_path).write_bytes(b"stale launcher\n")

    with pytest.raises(FileNotFoundError):
        prepare_launcher(tmp_path)
