"""Asynchronous services retain the same request and complete cleanup contract."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from quality import owned_commands as owned
from quality.owned_process import Cleanup, Completion


def test_asynchronous_start_does_not_wait_and_freezes_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    process = MagicMock(pid=123)
    monkeypatch.setattr(subprocess, "Popen", MagicMock(return_value=process))
    arguments = ["worker", "private"]
    handle = owned.start_owned(arguments, tmp_path, 3660, {})
    arguments.append("changed-after-launch")
    assert handle.command == ("worker", "private")
    assert handle.timeout == 3660
    assert handle.process is process
    assert handle.receipt == handle.directory / "completion.json"
    process.wait.assert_not_called()
    assert (handle.directory / "request.json").exists()


def test_service_stop_wait_has_a_separate_bound_without_changing_tool_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    process = MagicMock(pid=123)
    handle = owned.OwnedCommand(
        ("worker",), 3660, process, tmp_path, "nonce", tmp_path / "receipt"
    )
    wait = MagicMock()
    read = MagicMock(return_value=Completion(0, False, Cleanup([], [])))
    success = MagicMock()
    monkeypatch.setattr(owned, "wait_supervisor", wait)
    monkeypatch.setattr(owned, "read_completion", read)
    monkeypatch.setattr(owned, "require_success", success)
    owned.finish_owned(handle, 39)
    wait.assert_called_once_with(process, 39, tmp_path)
    read.assert_called_once_with(handle.receipt, "nonce")
    success.assert_called_once_with(
        Completion(0, False, Cleanup([], [])), ["worker"], 3660
    )


def test_invalid_service_stop_bound_cannot_accept_a_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    process = MagicMock(pid=123)
    handle = owned.OwnedCommand(
        ("worker",), 3660, process, tmp_path, "nonce", tmp_path / "receipt"
    )
    read = MagicMock()
    monkeypatch.setattr(owned, "read_completion", read)
    with pytest.raises(ValueError):
        owned.finish_owned(handle, float("nan"))
    process.wait.assert_not_called()
    read.assert_not_called()
