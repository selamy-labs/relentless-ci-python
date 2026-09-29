"""Native ABI, exact ownership, bounded reaping and signed completion contracts."""

import ctypes
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from quality import owned_process as owned


@pytest.mark.parametrize("status", [0, -1, 1])
def test_native_prctl_abi_and_error_propagation(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    native = MagicMock(return_value=status)
    library = MagicMock(prctl=native)
    load = MagicMock(return_value=library)
    monkeypatch.setattr(ctypes, "CDLL", load)
    monkeypatch.setattr(ctypes, "get_errno", lambda: 13)
    if status:
        with pytest.raises(OSError, match="native process supervision failed") as error:
            owned.prctl(36, 1)
        assert error.value.errno == 13
    else:
        owned.prctl(36, 1)
    load.assert_called_once_with(None, use_errno=True)
    native.assert_called_once_with(36, 1, 0, 0, 0)
    assert native.argtypes == [ctypes.c_int] + [ctypes.c_ulong] * 4
    assert native.restype is ctypes.c_int


@pytest.mark.parametrize(
    "actual,expected", [(0, 1), (1, 1), (2, 1), (257, 257), (256, 257), (258, 257)]
)
def test_readback_checks_native_pointer_value(
    monkeypatch: pytest.MonkeyPatch, actual: int, expected: int
) -> None:
    value = MagicMock(value=int(str(actual)))
    make = MagicMock(return_value=value)
    address = MagicMock(return_value=1234)
    native = MagicMock()
    monkeypatch.setattr(ctypes, "c_int", make)
    monkeypatch.setattr(ctypes, "addressof", address)
    monkeypatch.setattr(owned, "prctl", native)
    if actual == expected:
        owned.readback(37, expected)
    else:
        with pytest.raises(RuntimeError, match="readback disagrees"):
            owned.readback(37, expected)
    make.assert_called_once_with()
    address.assert_called_once_with(value)
    native.assert_called_once_with(37, 1234)


@pytest.mark.parametrize("platform", ["darwin", "win32", "a", "z"])
def test_non_linux_supervision_cannot_claim_capability(
    monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    native = MagicMock()
    monkeypatch.setattr(owned, "prctl", native)
    with pytest.raises(RuntimeError, match="requires Linux"):
        owned.enable()
    native.assert_not_called()


@pytest.mark.parametrize("platform", ["linux", "".join(["li", "nux"])])
@pytest.mark.parametrize("creator", [500, 501, 502])
def test_enable_requires_subreaper_parent_death_readback_and_stable_creator(
    monkeypatch: pytest.MonkeyPatch, creator: int, platform: str
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    parent = MagicMock(side_effect=[501, creator])
    native = MagicMock()
    readback = MagicMock()
    signals = MagicMock()
    monkeypatch.setattr(os, "getppid", parent)
    monkeypatch.setattr(owned, "prctl", native)
    monkeypatch.setattr(owned, "readback", readback)
    monkeypatch.setattr(signal, "signal", signals)
    if creator != 501:
        with pytest.raises(RuntimeError, match="creator changed"):
            owned.enable()
    else:
        owned.enable()
    assert parent.call_count == 2
    assert native.call_args_list == [call(36, 1), call(1, int(signal.SIGTERM))]
    assert readback.call_args_list == [call(37, 1), call(2, int(signal.SIGTERM))]
    assert signals.call_args_list == [
        call(signal.SIGCHLD, signal.SIG_DFL),
        call(signal.SIGTERM, owned.interrupt),
        call(signal.SIGINT, owned.interrupt),
    ]


@pytest.mark.parametrize("signum", [2, 15])
def test_interrupt_raises_through_finally_with_exact_signal_status(signum: int) -> None:
    with pytest.raises(SystemExit) as error:
        owned.interrupt(signum, None)
    assert error.value.code == 128 + signum


@pytest.mark.parametrize("value,expected", [("", []), ("45 67\n", [45, 67])])
def test_children_read_only_the_current_tasks_kernel_inventory(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: list[int]
) -> None:
    def read(path: Path, encoding: str) -> str:
        assert path == Path("/proc/self/task/123/children")
        assert encoding == "utf-8"
        return value

    monkeypatch.setattr(os, "getpid", lambda: 123)
    monkeypatch.setattr(Path, "read_text", read)
    assert owned.children() == expected


@pytest.mark.parametrize("missing", [False, True])
def test_kills_exact_owned_children_and_only_tolerates_already_gone(
    monkeypatch: pytest.MonkeyPatch, missing: bool
) -> None:
    monkeypatch.setattr(owned, "children", lambda: [12, 13])
    native = MagicMock(side_effect=ProcessLookupError() if missing else None)
    monkeypatch.setattr(os, "kill", native)
    owned.kill_children([12, 13])
    assert native.call_args_list == [call(12, signal.SIGKILL), call(13, signal.SIGKILL)]


def test_kill_permission_error_cannot_disappear(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(owned, "children", lambda: [12])
    monkeypatch.setattr(os, "kill", MagicMock(side_effect=PermissionError("denied")))
    with pytest.raises(PermissionError, match="denied"):
        owned.kill_children([12])


@pytest.mark.parametrize("status,expected", [(15, -15), (3 << 8, 3)])
def test_reap_retains_signed_outcomes_and_distinguishes_live_children(
    monkeypatch: pytest.MonkeyPatch, status: int, expected: int
) -> None:
    native = MagicMock(side_effect=[(99, status), (0, 0), ChildProcessError()])
    monkeypatch.setattr(os, "waitpid", native)
    results: list[tuple[int, int]] = []
    assert owned.reap_available(results) is True
    assert results == [(99, expected)]
    assert owned.reap_available(results) is False
    assert native.call_args_list == [call(-1, os.WNOHANG)] * 3


@pytest.mark.parametrize("expires", [False, True])
@pytest.mark.parametrize("overshoot", [0, 0.25])
def test_drain_adopts_all_children_then_reaps_or_fails_its_exact_deadline(
    monkeypatch: pytest.MonkeyPatch, expires: bool, overshoot: float
) -> None:
    signal_set = MagicMock()
    kill = MagicMock()
    sleep = MagicMock()
    monkeypatch.setattr(signal, "signal", signal_set)
    monkeypatch.setattr(owned, "children", MagicMock(side_effect=[[12], [13]]))
    monkeypatch.setattr(owned, "kill_children", kill)
    monkeypatch.setattr(
        owned, "reap_available", MagicMock(side_effect=[True, True, False])
    )
    monkeypatch.setattr(
        time,
        "monotonic",
        MagicMock(side_effect=[10, 12 + overshoot if expires else 11, 11]),
    )
    monkeypatch.setattr(time, "sleep", sleep)
    if expires:
        with pytest.raises(TimeoutError, match="cleanup deadline"):
            owned.drain(2)
        kill.assert_called_once_with([12])
        sleep.assert_not_called()
    else:
        assert owned.drain(2) == owned.Cleanup([12, 13], [])
        assert kill.call_args_list == [call([12]), call([13])]
        assert sleep.call_args_list == [call(0.001), call(0.001)]
    assert signal_set.call_args_list == [
        call(signal.SIGTERM, signal.SIG_IGN),
        call(signal.SIGINT, signal.SIG_IGN),
    ]


@pytest.mark.parametrize("status", [0, 3, -15, None])
def test_execute_preserves_tool_context_timeout_and_actual_reaped_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, status: int | None
) -> None:
    enable = MagicMock()
    cleanup = owned.Cleanup([123, 456], [(123, -9), (456, -9)])
    drain = MagicMock(return_value=cleanup)
    wait = MagicMock(
        return_value=status,
        side_effect=subprocess.TimeoutExpired(["tool"], 7) if status is None else None,
    )
    process = MagicMock(pid=123, wait=wait)
    launch = MagicMock(return_value=process)
    monkeypatch.setattr(owned, "enable", enable)
    monkeypatch.setattr(owned, "drain", drain)
    monkeypatch.setattr(subprocess, "Popen", launch)
    result = owned.execute(
        ["tool", "argument with spaces"], tmp_path, 7, {"EXACT": "value"}
    )
    assert result == owned.Completion(
        -9 if status is None else status, status is None, cleanup
    )
    assert process.returncode == result.returncode
    enable.assert_called_once_with()
    drain.assert_called_once_with(20)
    wait.assert_called_once_with(timeout=7)
    launch.assert_called_once_with(
        ["tool", "argument with spaces"],
        cwd=tmp_path,
        env={"EXACT": "value"},
        start_new_session=True,
    )


def test_launch_failure_still_drains_owned_children(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(owned, "enable", MagicMock())
    monkeypatch.setattr(
        subprocess, "Popen", MagicMock(side_effect=FileNotFoundError("missing tool"))
    )
    drain = MagicMock(return_value=owned.Cleanup([], []))
    monkeypatch.setattr(owned, "drain", drain)
    with pytest.raises(FileNotFoundError, match="missing tool"):
        owned.execute(["absent"], tmp_path, 1, {})
    drain.assert_called_once_with(20)


@pytest.mark.parametrize(
    "pids,message",
    [
        ([0], "must be positive"),
        ([-1], "must be positive"),
        ([-123], "must be positive"),
        ([12, 99], "outside owned children"),
    ],
)
def test_foreign_or_group_selectors_are_rejected_before_signaling(
    monkeypatch: pytest.MonkeyPatch, pids: list[int], message: str
) -> None:
    monkeypatch.setattr(owned, "children", lambda: [12, 13])
    kill = MagicMock()
    monkeypatch.setattr(os, "kill", kill)
    with pytest.raises(ValueError, match=message):
        owned.kill_children(pids)
    kill.assert_not_called()


def test_empty_owned_inventory_needs_no_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(owned, "children", lambda: list[int]())
    kill = MagicMock()
    monkeypatch.setattr(os, "kill", kill)
    owned.kill_children([])
    kill.assert_not_called()


def test_smallest_positive_owned_pid_is_not_a_group_selector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(owned, "children", lambda: [1])
    kill = MagicMock()
    monkeypatch.setattr(os, "kill", kill)

    owned.kill_children([1])

    kill.assert_called_once_with(1, signal.SIGKILL)
