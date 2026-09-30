"""Worker startup, private endpoints and all-stop cleanup failure contracts."""

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from quality import mutation_services as services
from quality.mutation_inputs import environment
from quality.mutation_services import Worker
from quality.owned_commands import OwnedCommand, SupervisionUnproven


def instance(root: Path, status: int | None = None) -> Worker:
    (root / ".quality-results").mkdir(parents=True, exist_ok=True)
    process = MagicMock(pid=123, poll=MagicMock(return_value=status))
    handle = OwnedCommand(("worker",), 3780, process, root, "request", root / "receipt")
    return Worker(root, "private", handle)


@pytest.mark.parametrize(
    "count,expected", [(None, 1), (0, 1), (1, 1), (2, 2), (8, 8), (16, 8)]
)
def test_worker_count_is_bounded(
    monkeypatch: pytest.MonkeyPatch, count: int | None, expected: int
) -> None:
    monkeypatch.setattr(os, "cpu_count", MagicMock(return_value=count))
    assert services.worker_count() == expected


@pytest.mark.parametrize("port", [1, 65535])
def test_accepts_bare_private_loopback_url_at_port_boundaries(port: int) -> None:
    url = f"http://127.0.0.1:{port}"

    assert services.loopback_url(url) == url


@pytest.mark.parametrize("preexisting", [False, True])
def test_launch_copies_inputs_and_binds_own_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, preexisting: bool
) -> None:
    copied = MagicMock()
    launch = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(services, "copy_inputs", copied)
    monkeypatch.setattr(services, "start_owned", launch)
    if preexisting:
        (tmp_path / ".quality-results").mkdir()
    inherited = {
        "KEEP": "value",
        "PYTHONPATH": "foreign",
        "PYTEST_DEBUG_TEMPROOT": "foreign-temporary-root",
    }
    worker = services.launch(tmp_path, 3, 3600, inherited)
    target = tmp_path / ".quality-results/mutation-worker-3"
    copied.assert_called_once_with(tmp_path, target)
    launch.assert_called_once_with(
        [sys.executable, "-m", "quality.mutation_worker_main", worker.nonce],
        target,
        3780,
        environment(target, inherited),
    )
    assert worker.root == target
    assert worker.owned is launch.return_value
    assert inherited == {
        "KEEP": "value",
        "PYTHONPATH": "foreign",
        "PYTEST_DEBUG_TEMPROOT": "foreign-temporary-root",
    }
    assert environment(target, inherited)["PYTHONPATH"] == os.pathsep.join(
        [str(target / "src"), str(target)]
    )
    assert environment(target, inherited)["PYTHONDONTWRITEBYTECODE"] == "1"
    assert environment(target, inherited)["PYTEST_DEBUG_TEMPROOT"] == str(
        target / ".quality-results"
    )
    assert environment(tmp_path, inherited)["PYTEST_DEBUG_TEMPROOT"] == str(
        tmp_path / ".quality-results"
    )


@pytest.mark.parametrize(
    "fault", ["wrong-nonce", "early-nonce", "extra", "missing", "malformed", "dead"]
)
def test_unbound_or_dead_readiness_never_passes(tmp_path: Path, fault: str) -> None:
    worker = instance(tmp_path, 0 if fault == "dead" else None)
    value = {
        "nonce": {"wrong-nonce": "wrong", "early-nonce": "early"}.get(fault, "private"),
        "url": "http://127.0.0.1:12345",
    }
    if fault == "extra":
        value["extra"] = "unexpected"
    if fault == "missing":
        del value["url"]
    path = tmp_path / ".quality-results/worker-ready.json"
    path.write_text("{" if fault == "malformed" else json.dumps(value))
    with pytest.raises((ValueError, SupervisionUnproven)):
        services.ready(worker)


@pytest.mark.parametrize("elapsed", [10, 10.25])
def test_startup_wait_is_bounded_and_checks_actual_handle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, elapsed: float
) -> None:
    worker = instance(tmp_path)
    monkeypatch.setattr(time, "monotonic", MagicMock(side_effect=[0, 9, elapsed]))
    sleep = MagicMock()
    monkeypatch.setattr(time, "sleep", sleep)
    with pytest.raises(TimeoutError, match="readiness"):
        services.ready(worker)
    sleep.assert_called_once_with(0.01)
    assert isinstance(worker.owned.process, MagicMock)
    assert worker.owned.process.poll.call_count == 2


def test_readiness_after_wait_checks_private_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker = instance(tmp_path)

    def publish(delay: float) -> None:
        assert delay == 0.01
        (tmp_path / ".quality-results/worker-ready.json").write_text(
            json.dumps({"nonce": "private", "url": "http://127.0.0.1:12345"})
        )

    monkeypatch.setattr(time, "sleep", publish)
    assert services.ready(worker) == "http://127.0.0.1:12345"
    assert isinstance(worker.owned.process, MagicMock)
    assert worker.owned.process.poll.call_count == 2


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:123",
        "http://localhost:123",
        "http://user@127.0.0.1:123",
        "http://user:password@127.0.0.1:123",
        "http://127.0.0.1:123/",
        "http://127.0.0.1:123?x",
        "http://127.0.0.1:123#x",
        "http://127.0.0.1",
        "http://127.0.0.1:0",
        "http://127.0.0.1:99999",
        "http://127.0.0.1:bad",
    ],
)
def test_only_private_bare_positive_port_urls_are_accepted(url: str) -> None:
    with pytest.raises(ValueError):
        services.loopback_url(url)


def test_stop_publishes_nonce_atomically(tmp_path: Path) -> None:
    worker = instance(tmp_path)
    services.stop(worker)
    assert json.loads((tmp_path / ".quality-results/worker-stop.json").read_text()) == {
        "nonce": "private"
    }
    assert not (tmp_path / ".quality-results/worker-stop.tmp").exists()


def test_all_stops_precede_waits_and_all_failures_are_retained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workers = [instance(tmp_path / "first"), instance(tmp_path / "second")]
    events: list[tuple[str, Path]] = []
    stop_error = OSError("disk")
    finish_error = SupervisionUnproven(123, tmp_path, "live")

    def stop(worker: Worker) -> None:
        events.append(("stop", worker.root))
        if worker is workers[0]:
            raise stop_error

    def finish(owned: OwnedCommand, timeout: float) -> None:
        assert timeout == 39
        events.append(("finish", owned.directory))
        if owned is workers[0].owned:
            raise finish_error

    monkeypatch.setattr(services, "stop", stop)
    monkeypatch.setattr(services, "finish_owned", finish)
    assert services.shutdown(workers) == [stop_error, finish_error]
    assert events == [
        ("stop", workers[0].root),
        ("stop", workers[1].root),
        ("finish", workers[0].root),
        ("finish", workers[1].root),
    ]
