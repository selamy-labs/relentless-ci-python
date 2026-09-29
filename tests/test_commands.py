"""Real-process probes for failure propagation and command execution context."""

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from quality import commands
from quality.commands import run


def test_runs_in_requested_directory_with_requested_environment(tmp_path: Path) -> None:
    env = dict(os.environ, RELENTLESS_VALUE="expected")
    script = (
        "import json,os,pathlib; "
        "pathlib.Path('receipt').write_text(os.environ['RELENTLESS_VALUE']); "
        "pathlib.Path('group').write_text(json.dumps([os.getpid(),os.getpgrp()]))"
        if os.name == "posix"
        else (
            "import os,pathlib; "
            "pathlib.Path('receipt').write_text(os.environ['RELENTLESS_VALUE'])"
        )
    )
    run([sys.executable, "-c", script], tmp_path, 5, env)
    assert (tmp_path / "receipt").read_text() == "expected"
    if os.name == "posix":
        pid, group = json.loads((tmp_path / "group").read_text())
        assert pid == group


def test_nonzero_exit_is_a_failed_check(tmp_path: Path) -> None:
    with pytest.raises(subprocess.CalledProcessError) as error:
        run(
            [sys.executable, "-c", "raise SystemExit(3)"], tmp_path, 5, dict(os.environ)
        )
    assert error.value.returncode == 3


def test_missing_tool_is_a_failed_check(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        run([str(tmp_path / "absent-tool")], tmp_path, 5, dict(os.environ))


def test_timeout_is_a_failed_check(tmp_path: Path) -> None:
    with pytest.raises(subprocess.TimeoutExpired):
        run(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            tmp_path,
            0.05,
            dict(os.environ),
        )


def test_bounded_wait_cleans_before_propagating_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    arguments = ["owned-tool", "argument with spaces"]
    fault = subprocess.TimeoutExpired(arguments, 5)
    process = MagicMock(wait=MagicMock(side_effect=fault))
    context = MagicMock(__enter__=MagicMock(return_value=process))
    launch = MagicMock(return_value=context)
    cleanup = MagicMock()
    monkeypatch.setattr(subprocess, "Popen", launch)
    monkeypatch.setattr(commands, "stop", cleanup)
    environment = {"RELENTLESS_VALUE": "expected"}
    with pytest.raises(subprocess.TimeoutExpired) as error:
        run(arguments, tmp_path, 5, environment)
    assert error.value is fault
    cleanup.assert_called_once_with(process)
    process.wait.assert_called_once_with(timeout=5)
    launch.assert_called_once_with(
        arguments, cwd=tmp_path, env=environment, start_new_session=os.name == "posix"
    )


@pytest.mark.parametrize(
    "name,expected",
    [
        ("posix", True),
        ("".join(["po", "six"]), True),
        ("nt", False),
        ("a", False),
        ("z", False),
    ],
)
def test_platform_identifier_is_exact(name: str, expected: bool) -> None:
    assert commands.is_posix(name) is expected


@pytest.mark.parametrize("status", [-15, -1, 1, 3])
def test_signed_nonzero_status_is_a_failed_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    process = MagicMock(wait=MagicMock(return_value=status))
    context = MagicMock(__enter__=MagicMock(return_value=process))
    launch = MagicMock(return_value=context)
    monkeypatch.setattr(subprocess, "Popen", launch)
    with pytest.raises(subprocess.CalledProcessError) as error:
        run(["owned-tool"], tmp_path, 5, {})
    assert error.value.returncode == status
    assert error.value.cmd == ["owned-tool"]
