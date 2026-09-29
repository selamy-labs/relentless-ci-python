"""The dedicated entry writes signed completion only after the runtime returns."""

import json
import os
import runpy
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from quality import owned_entry
from quality.owned_entry import supervise
from quality.owned_process import Cleanup, Completion


def request(root: Path, command: object = None) -> Path:
    path = root / "request.json"
    path.write_text(
        json.dumps(
            {
                "command": ["tool", "argument"] if command is None else command,
                "root": str(root),
                "timeout": "7.5",
                "nonce": "fresh",
                "receipt": str(root / "completion.json"),
            }
        )
    )
    return path


def test_entry_binds_native_execution_to_fresh_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = Completion(-9, True, Cleanup([123], [(123, -9)]))
    execute = MagicMock(return_value=result)
    monkeypatch.setattr(owned_entry, "execute", execute)
    supervise(request(tmp_path))
    execute.assert_called_once_with(
        ["tool", "argument"], tmp_path, 7.5, dict(os.environ)
    )
    assert json.loads((tmp_path / "completion.json").read_text()) == {
        "nonce": "fresh",
        "returncode": -9,
        "timed_out": True,
        "cleanup": {"killed": [123], "reaped": [[123, -9]]},
    }


def test_empty_command_fails_before_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    execute = MagicMock()
    monkeypatch.setattr(owned_entry, "execute", execute)
    with pytest.raises(ValueError, match="command is empty"):
        supervise(request(tmp_path, []))
    execute.assert_not_called()
    assert not (tmp_path / "completion.json").exists()


def test_runtime_failure_cannot_write_success_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        owned_entry, "execute", MagicMock(side_effect=RuntimeError("cleanup failed"))
    )
    with pytest.raises(RuntimeError, match="cleanup failed"):
        supervise(request(tmp_path))
    assert not (tmp_path / "completion.json").exists()


def test_main_passes_exact_request_path(monkeypatch: pytest.MonkeyPatch) -> None:
    call = MagicMock()
    monkeypatch.setattr(owned_entry, "supervise", call)
    monkeypatch.setattr(sys, "argv", ["supervisor", "request.json"])
    runpy.run_module("quality.owned_main", run_name="__main__")
    call.assert_called_once_with(Path("request.json"))
