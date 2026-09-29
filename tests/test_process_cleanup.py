"""Native tree termination and bounded reaping precede temporary cleanup."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from quality import commands


@pytest.mark.parametrize("platform", [True, False])
@pytest.mark.parametrize("status", [None, -9])
def test_stop_uses_platform_tree_and_reaps(
    monkeypatch: pytest.MonkeyPatch, platform: bool, status: int | None
) -> None:
    process = MagicMock(spec=subprocess.Popen)
    process.pid = 123
    process.poll = MagicMock(return_value=status)
    group = MagicMock()
    native = MagicMock()
    monkeypatch.setattr(commands, "POSIX", platform)
    monkeypatch.setattr(commands, "kill_group", group)
    monkeypatch.setattr(subprocess, "run", native)
    commands.stop(process)
    if platform:
        group.assert_called_once_with(123)
        native.assert_not_called()
    elif status is None:
        native.assert_called_once_with(
            ["taskkill", "/PID", "123", "/T", "/F"],
            check=True,
            timeout=20,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    else:
        native.assert_not_called()
    assert process.kill.call_count == int(status is None)
    process.wait.assert_called_once_with(timeout=20)


@pytest.mark.parametrize("missing", [False, True])
def test_group_termination_tolerates_only_already_gone_group(
    monkeypatch: pytest.MonkeyPatch, missing: bool
) -> None:
    kill = MagicMock(side_effect=ProcessLookupError() if missing else None)
    monkeypatch.setattr(os, "killpg", kill, raising=False)
    monkeypatch.setattr(signal, "SIGKILL", 9, raising=False)
    commands.kill_group(123)
    kill.assert_called_once_with(123, 9)


def test_kill_failure_still_reaps_and_cannot_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = MagicMock(spec=subprocess.Popen)
    process.poll = MagicMock(return_value=None)
    fault = MagicMock(side_effect=PermissionError("tree termination denied"))
    monkeypatch.setattr(commands, "stop_tree", fault)
    with pytest.raises(PermissionError, match="tree termination denied"):
        commands.stop(process)
    process.kill.assert_called_once_with()
    process.wait.assert_called_once_with(timeout=20)


def test_native_timeout_terminates_descendant_before_it_writes(tmp_path: Path) -> None:
    late = tmp_path / "late"
    ready = tmp_path / "ready"
    child = (
        "import pathlib,time; time.sleep(1); pathlib.Path('late').write_text('leak')"
    )
    parent = (
        "import pathlib,subprocess,sys,time; "
        f"subprocess.Popen([sys.executable,'-c',{child!r}]); "
        "pathlib.Path('ready').write_text('started'); time.sleep(60)"
    )
    with pytest.raises(subprocess.TimeoutExpired):
        commands.run([sys.executable, "-c", parent], tmp_path, 0.3, dict(os.environ))
    assert ready.read_text() == "started"
    time.sleep(1.1)
    assert not late.exists()


def test_group_access_failure_is_not_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    kill = MagicMock(side_effect=PermissionError("group access denied"))
    monkeypatch.setattr(os, "killpg", kill, raising=False)
    monkeypatch.setattr(signal, "SIGKILL", 9, raising=False)
    with pytest.raises(PermissionError, match="group access denied"):
        commands.kill_group(123)
