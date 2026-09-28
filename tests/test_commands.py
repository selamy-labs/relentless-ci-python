"""Real-process probes for failure propagation and command execution context."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from quality.commands import run


def test_runs_in_requested_directory_with_requested_environment(tmp_path: Path) -> None:
    env = dict(os.environ, RELENTLESS_VALUE="expected")
    script = (
        "import os,pathlib; "
        "pathlib.Path('receipt').write_text(os.environ['RELENTLESS_VALUE'])"
    )
    run([sys.executable, "-c", script], tmp_path, 5, env)
    assert (tmp_path / "receipt").read_text() == "expected"


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
