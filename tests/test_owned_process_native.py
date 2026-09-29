"""Dedicated native supervisors reap separate-session children without collateral."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from quality.report_data import array, record

BOOTSTRAP = (
    "import dataclasses,json,os,sys; from pathlib import Path; "
    "from quality.owned_process import execute; "
    "value=execute(json.loads(sys.argv[1]),Path(sys.argv[2]),"
    "float(sys.argv[3]),dict(os.environ)); "
    "print(json.dumps(dataclasses.asdict(value)))"
)


def supervise(command: list[str], root: Path, timeout: float) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, "-c", BOOTSTRAP, json.dumps(command), str(root), str(timeout)],
        cwd=Path(__file__).resolve().parents[1],
        env=dict(os.environ),
        start_new_session=True,
        capture_output=True,
        text=True,
        timeout=6,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    return record(json.loads(result.stdout))


@pytest.mark.parametrize("status", [0, 3])
def test_native_signed_completion_and_exact_execution_context(
    tmp_path: Path, status: int
) -> None:
    body = (
        "import os,pathlib,sys; "
        "pathlib.Path('receipt').write_text(os.environ['RELENTLESS_VALUE']); "
        f"sys.exit({status})"
    )
    original = os.environ.get("RELENTLESS_VALUE")
    os.environ["RELENTLESS_VALUE"] = "exact"
    try:
        result = supervise([sys.executable, "-c", body], tmp_path, 2)
    finally:
        if original is None:
            del os.environ["RELENTLESS_VALUE"]
        else:
            os.environ["RELENTLESS_VALUE"] = original
    assert (tmp_path / "receipt").read_text() == "exact"
    assert result == {
        "returncode": status,
        "timed_out": False,
        "cleanup": {"killed": [], "reaped": []},
    }


def test_native_negative_signal_status(tmp_path: Path) -> None:
    result = supervise(
        [sys.executable, "-c", "import os,signal;os.kill(os.getpid(),signal.SIGTERM)"],
        tmp_path,
        2,
    )
    assert result == {
        "returncode": -15,
        "timed_out": False,
        "cleanup": {"killed": [], "reaped": []},
    }


def test_native_dead_adopted_child_is_reaped_without_a_new_kill(tmp_path: Path) -> None:
    body = (
        "import os,pathlib,time; pid=os.fork(); "
        "\nif not pid:\n os.setsid(); os._exit(3)\n"
        "pathlib.Path('dead-child.pid').write_text(str(pid)); time.sleep(0.2)"
    )
    result = supervise([sys.executable, "-c", body], tmp_path, 2)
    pid = int((tmp_path / "dead-child.pid").read_text())
    assert result == {
        "returncode": 0,
        "timed_out": False,
        "cleanup": {"killed": [], "reaped": [[pid, 3]]},
    }
    assert not Path(f"/proc/{pid}").exists()


@pytest.mark.parametrize("parent_exits", [False, True])
def test_native_timeout_or_root_exit_reaps_independent_session_descendant(
    tmp_path: Path, parent_exits: bool
) -> None:
    child = (
        "import os,pathlib,signal,time; "
        "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        "signal.signal(signal.SIGINT,signal.SIG_IGN); "
        "pathlib.Path('child.pid').write_text(str(os.getpid())); "
        "time.sleep(0.8); pathlib.Path('late').write_text('leak'); time.sleep(20)"
    )
    parent = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable,'-c',{child!r}],start_new_session=True); "
        "time.sleep(0.15); " + ("sys.exit(0)" if parent_exits else "time.sleep(20)")
    )
    with subprocess.Popen(
        [sys.executable, "-c", "import time;time.sleep(20)"]
    ) as unrelated:
        try:
            result = supervise([sys.executable, "-c", parent], tmp_path, 0.35)
            assert result["timed_out"] is not parent_exits
            assert result["returncode"] == (0 if parent_exits else -9)
            child_pid = int((tmp_path / "child.pid").read_text())
            cleanup = record(result["cleanup"])
            assert child_pid in array(cleanup["killed"])
            assert [child_pid, -9] in array(cleanup["reaped"])
            assert not Path(f"/proc/{child_pid}").exists()
            assert unrelated.poll() is None
            time.sleep(0.85)
            assert not (tmp_path / "late").exists()
        finally:
            unrelated.terminate()
            unrelated.wait(timeout=2)


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
def test_native_interruption_reaps_owned_sessions_before_failure(
    tmp_path: Path, signum: int
) -> None:
    child = (
        "import os,pathlib,signal,time; "
        "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        "signal.signal(signal.SIGINT,signal.SIG_IGN); "
        "pathlib.Path('child.pid').write_text(str(os.getpid())); time.sleep(20)"
    )
    parent = (
        "import os,pathlib,subprocess,sys,time; "
        "pathlib.Path('parent.pid').write_text(str(os.getpid())); "
        f"subprocess.Popen([sys.executable,'-c',{child!r}],start_new_session=True); "
        "time.sleep(20)"
    )
    with subprocess.Popen(
        [
            sys.executable,
            "-Werror",
            "-c",
            BOOTSTRAP,
            json.dumps([sys.executable, "-c", parent]),
            str(tmp_path),
            "20",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=dict(os.environ),
        start_new_session=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as supervisor:
        deadline = time.monotonic() + 3
        while not (tmp_path / "child.pid").exists():
            assert supervisor.poll() is None
            assert time.monotonic() < deadline
            time.sleep(0.005)
        supervisor.send_signal(signum)
        stdout, stderr = supervisor.communicate(timeout=5)
        assert supervisor.returncode == 128 + signum
        assert stdout == ""
        assert stderr == ""
        for name in ("parent.pid", "child.pid"):
            pid = int((tmp_path / name).read_text())
            assert not Path(f"/proc/{pid}").exists()
