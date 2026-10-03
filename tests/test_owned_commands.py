"""Only proven terminal cleanup permits completion; metadata is never reused."""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from quality import owned_commands
from quality.owned_commands import SupervisionUnproven, run_owned, wait_supervisor
from quality.owned_process import Cleanup, Completion


def finished_process() -> MagicMock:
    """A supervisor that exited successfully and has no live child."""
    return MagicMock(
        pid=123, wait=MagicMock(return_value=0), poll=MagicMock(return_value=0)
    )


@pytest.mark.parametrize("retry", [False, True])
def test_wait_preserves_tool_deadline_and_gracefully_bounds_cleanup(
    tmp_path: Path, retry: bool
) -> None:
    wait = MagicMock(
        return_value=0,
        side_effect=(
            [subprocess.TimeoutExpired(["supervisor"], 28), 0] if retry else None
        ),
    )
    process = MagicMock(pid=123, wait=wait, poll=MagicMock(return_value=0))
    wait_supervisor(process, 7, tmp_path)
    assert wait.call_args_list == (
        [call(timeout=28), call(timeout=21)] if retry else [call(timeout=28)]
    )
    assert process.terminate.call_count == int(retry)
    process.kill.assert_not_called()
    process.poll.assert_called_once_with()


def test_stuck_supervisor_is_not_hard_killed_and_metadata_remains(
    tmp_path: Path,
) -> None:
    (tmp_path / "marker").write_text("retain")
    process = MagicMock(
        pid=123,
        wait=MagicMock(side_effect=subprocess.TimeoutExpired(["supervisor"], 28)),
    )
    with pytest.raises(SupervisionUnproven, match="cleanup remains live") as error:
        wait_supervisor(process, 7, tmp_path)
    assert error.value.pid == 123
    assert error.value.directory == tmp_path
    assert "PID 123" in str(error.value)
    assert str(tmp_path) in str(error.value)
    assert (tmp_path / "marker").read_text() == "retain"
    assert process.wait.call_args_list == [call(timeout=28), call(timeout=21)]
    process.terminate.assert_called_once_with()
    process.kill.assert_not_called()


@pytest.mark.parametrize(
    "status,message", [(None, "remains live"), (-15, "failed"), (1, "failed")]
)
def test_missing_or_nonzero_supervisor_completion_fails(
    tmp_path: Path, status: int | None, message: str
) -> None:
    process = MagicMock(
        pid=123, wait=MagicMock(return_value=0), poll=MagicMock(return_value=status)
    )
    with pytest.raises(SupervisionUnproven, match=message):
        wait_supervisor(process, 7, tmp_path)


def test_fresh_requests_bind_cwd_env_command_and_independent_receipts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    process = MagicMock(
        pid=123, wait=MagicMock(return_value=0), poll=MagicMock(return_value=0)
    )
    launch = MagicMock(return_value=process)
    received: list[Path] = []
    nonces: list[str] = []

    def read(path: Path, nonce: str) -> Completion:
        request = json.loads((path.parent / "request.json").read_text())
        assert request == {
            "command": ["tool", "argument with spaces"],
            "root": str(tmp_path.resolve()),
            "timeout": "7",
            "nonce": nonce,
            "receipt": str(path.resolve()),
        }
        assert path.name == "completion.json"
        assert not path.exists()
        received.append(path)
        nonces.append(nonce)
        return Completion(0, False, Cleanup([], []))

    monkeypatch.setattr(subprocess, "Popen", launch)
    monkeypatch.setattr(owned_commands, "read_completion", read)
    env = {"EXACT": "value"}
    for _ in range(2):
        run_owned(["tool", "argument with spaces"], tmp_path, 7, env)
    assert len(set(received)) == 2
    assert len(set(nonces)) == 2
    assert all((path.parent / "request.json").is_file() for path in received)
    for invocation, receipt in zip(launch.call_args_list, received, strict=True):
        arguments = invocation.args[0]
        assert arguments == [
            sys.executable,
            "-m",
            "quality.owned_main",
            str((receipt.parent / "request.json").resolve()),
        ]
        assert invocation.kwargs == {
            "cwd": Path(owned_commands.__file__).resolve().parents[1],
            "env": env,
            "start_new_session": True,
        }


@pytest.mark.parametrize(
    "fault", [FileNotFoundError("missing"), ValueError("malformed")]
)
def test_missing_or_corrupt_receipt_is_unproven_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: Exception
) -> None:
    process = finished_process()
    monkeypatch.setattr(subprocess, "Popen", MagicMock(return_value=process))
    monkeypatch.setattr(owned_commands, "read_completion", MagicMock(side_effect=fault))
    with pytest.raises(SupervisionUnproven, match="receipt is incomplete") as error:
        run_owned(["tool"], tmp_path, 7, {})
    assert error.value.__cause__ is fault
    assert (error.value.directory / "request.json").is_file()


def test_valid_receipt_tool_failure_keeps_actual_status_and_raw_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    process = finished_process()
    monkeypatch.setattr(subprocess, "Popen", MagicMock(return_value=process))
    monkeypatch.setattr(
        owned_commands,
        "read_completion",
        MagicMock(return_value=Completion(-15, False, Cleanup([], []))),
    )
    with pytest.raises(subprocess.CalledProcessError) as error:
        run_owned(["tool"], tmp_path, 7, {})
    assert error.value.returncode == -15
    assert error.value.cmd == ["tool"]
    assert (
        len(list((tmp_path / ".quality-results" / "owned").glob("*/request.json"))) == 1
    )


def test_invalid_timeout_does_not_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launch = MagicMock()
    monkeypatch.setattr(subprocess, "Popen", launch)
    with pytest.raises(ValueError):
        run_owned(["tool"], tmp_path, float("nan"), {})
    launch.assert_not_called()
    assert not (tmp_path / ".quality-results").exists()


@pytest.mark.parametrize("cleanup_stuck", [False, True])
def test_interrupted_caller_requests_graceful_cleanup_and_keeps_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cleanup_stuck: bool
) -> None:
    interruption = KeyboardInterrupt()
    cleanup_failure = subprocess.TimeoutExpired(["supervisor"], 21)
    process = MagicMock(
        pid=123,
        wait=MagicMock(side_effect=cleanup_failure if cleanup_stuck else None),
    )
    monkeypatch.setattr(subprocess, "Popen", MagicMock(return_value=process))
    monkeypatch.setattr(
        owned_commands, "wait_supervisor", MagicMock(side_effect=interruption)
    )
    read = MagicMock()
    monkeypatch.setattr(owned_commands, "read_completion", read)
    with pytest.raises(SupervisionUnproven) as caught:
        run_owned(["tool"], tmp_path, 7, {})
    assert caught.value.__cause__ is (
        cleanup_failure if cleanup_stuck else interruption
    )
    assert caught.value.pid == 123
    assert (caught.value.directory / "request.json").exists()
    process.terminate.assert_called_once_with()
    process.wait.assert_called_once_with(timeout=21)
    process.kill.assert_not_called()
    read.assert_not_called()


def test_existing_unproven_cleanup_is_not_retried_or_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    failure = SupervisionUnproven(123, tmp_path, "live")
    process = MagicMock(pid=123)
    monkeypatch.setattr(subprocess, "Popen", MagicMock(return_value=process))
    monkeypatch.setattr(
        owned_commands, "wait_supervisor", MagicMock(side_effect=failure)
    )
    with pytest.raises(SupervisionUnproven) as caught:
        run_owned(["tool"], tmp_path, 7, {})
    assert caught.value is failure
    process.terminate.assert_not_called()
    process.wait.assert_not_called()
    process.kill.assert_not_called()
