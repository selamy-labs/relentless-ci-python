"""Real caller and fresh receipt reject timeouts, signed errors and child leaks."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from quality.owned_commands import SupervisionUnproven, run_owned
from quality.owned_receipt import read_completion


def test_native_caller_interrupt_cancels_supervisor_and_retains_failure(
    tmp_path: Path,
) -> None:
    command = (
        "import os,pathlib,signal,time; "
        "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        "pathlib.Path('child.pid').write_text(str(os.getpid())); time.sleep(20)"
    )
    body = (
        "import json,os,sys; from pathlib import Path; "
        "from quality.owned_commands import run_owned,SupervisionUnproven; "
        f"root=Path({str(tmp_path)!r}); "
        "\ntry:\n"
        f" run_owned([sys.executable,'-c',{command!r}],root,20,dict(os.environ))\n"
        "except SupervisionUnproven as error:\n"
        " (root/'failure.json').write_text(json.dumps({'pid':error.pid,"
        "'directory':str(error.directory),'cause':type(error.__cause__).__name__}))\n"
        " sys.exit(3)\n"
    )
    env = dict(os.environ)
    env["PYTHONWARNINGS"] = "error"
    with subprocess.Popen(
        [sys.executable, "-c", body],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        start_new_session=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as caller:
        deadline = time.monotonic() + 3
        while not (tmp_path / "child.pid").exists():
            assert caller.poll() is None
            assert time.monotonic() < deadline
            time.sleep(0.005)
        caller.send_signal(signal.SIGINT)
        stdout, stderr = caller.communicate(timeout=5)
        assert caller.returncode == 3
        assert stdout == ""
        assert stderr == ""
    failure = json.loads((tmp_path / "failure.json").read_text())
    assert failure["cause"] == "KeyboardInterrupt"
    assert not Path(f"/proc/{failure['pid']}").exists()
    child_pid = int((tmp_path / "child.pid").read_text())
    assert not Path(f"/proc/{child_pid}").exists()
    retained = Path(failure["directory"])
    assert (retained / "request.json").exists()
    assert not (retained / "completion.json").exists()


def last_receipt(root: Path) -> Path:
    receipts = list((root / ".quality-results" / "owned").glob("*/completion.json"))
    assert len(receipts) == 1
    return receipts[0]


def test_real_caller_preserves_context_and_complete_fresh_metadata(
    tmp_path: Path,
) -> None:
    command = [
        sys.executable,
        "-c",
        "import os,pathlib;pathlib.Path('value').write_text(os.environ['EXACT'])",
    ]
    run_owned(command, tmp_path, 2, dict(os.environ, EXACT="expected"))
    assert (tmp_path / "value").read_text() == "expected"
    path = last_receipt(tmp_path)
    request = json.loads((path.parent / "request.json").read_text())
    result = read_completion(path, request["nonce"])
    assert result.returncode == 0
    assert result.timed_out is False
    assert result.cleanup.killed == []
    assert result.cleanup.reaped == []


@pytest.mark.parametrize(
    "body,status",
    [
        ("raise SystemExit(3)", 3),
        ("import os,signal;os.kill(os.getpid(),signal.SIGTERM)", -15),
    ],
)
def test_real_caller_retains_signed_tool_failure(
    tmp_path: Path, body: str, status: int
) -> None:
    command = [sys.executable, "-c", body]
    with pytest.raises(subprocess.CalledProcessError) as error:
        run_owned(command, tmp_path, 2, dict(os.environ))
    assert error.value.returncode == status
    assert error.value.cmd == command
    assert json.loads(last_receipt(tmp_path).read_text())["returncode"] == status


@pytest.mark.parametrize("parent_exits", [False, True])
def test_caller_reaps_separate_session_and_fails_timeout_or_successful_leak(
    tmp_path: Path, parent_exits: bool
) -> None:
    child = (
        "import os,pathlib,signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);"
        "pathlib.Path('child.pid').write_text(str(os.getpid()));"
        "time.sleep(0.8);pathlib.Path('late').write_text('leak');time.sleep(20)"
    )
    parent = (
        "import subprocess,sys,time;"
        f"subprocess.Popen([sys.executable,'-c',{child!r}],start_new_session=True);"
        "time.sleep(0.15);" + ("sys.exit(0)" if parent_exits else "time.sleep(20)")
    )
    command = [sys.executable, "-c", parent]
    with subprocess.Popen(
        [sys.executable, "-c", "import time;time.sleep(20)"]
    ) as foreign:
        try:
            if parent_exits:
                with pytest.raises(RuntimeError, match="leaked owned descendants"):
                    run_owned(command, tmp_path, 0.35, dict(os.environ))
            else:
                with pytest.raises(subprocess.TimeoutExpired) as error:
                    run_owned(command, tmp_path, 0.35, dict(os.environ))
                assert error.value.cmd == command
                assert error.value.timeout == 0.35
            pid = int((tmp_path / "child.pid").read_text())
            assert not Path(f"/proc/{pid}").exists()
            assert foreign.poll() is None
            data = json.loads(last_receipt(tmp_path).read_text())
            assert pid in data["cleanup"]["killed"]
            assert [pid, -9] in data["cleanup"]["reaped"]
            time.sleep(0.85)
            assert not (tmp_path / "late").exists()
        finally:
            foreign.terminate()
            foreign.wait(timeout=2)


def test_failed_supervisor_keeps_request_and_never_claims_cleanup(
    tmp_path: Path,
) -> None:
    with pytest.raises(SupervisionUnproven) as error:
        run_owned([str(tmp_path / "missing")], tmp_path, 2, dict(os.environ))
    assert (error.value.directory / "request.json").is_file()
    assert not (error.value.directory / "completion.json").exists()
    assert error.value.pid > 0
