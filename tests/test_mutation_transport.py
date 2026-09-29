"""Native adapters preserve SDK calls, lifecycle, event loops and private stops."""

import asyncio
import importlib
import json
import runpy
import socket
import sys
import time
from collections.abc import Awaitable
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from aiohttp import web

from quality import mutation_coordinator as coordinator
from quality import mutation_worker as worker


async def run_handler(value: Awaitable[web.StreamResponse]) -> web.StreamResponse:
    return await value


def trial_source(root: Path) -> None:
    (root / "quality").mkdir()
    (root / "quality/mutation_trial.py").write_bytes(b"native launcher\n")


def test_native_handler_and_coordinator_bind_pinned_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler = AsyncMock()
    imported = MagicMock(return_value=SimpleNamespace(handle_mutate_and_test=handler))
    monkeypatch.setattr(importlib, "import_module", imported)
    assert worker.native_handler() is handler
    imported.assert_called_once_with("cosmic_ray.distribution.http")


@pytest.mark.parametrize("fails", [False, True])
def test_coordinator_preserves_arguments_and_closes_loop_on_failure(
    monkeypatch: pytest.MonkeyPatch, fails: bool
) -> None:
    loop = MagicMock()
    set_loop = MagicMock()
    failure = RuntimeError("native failure")
    cli = MagicMock(side_effect=failure if fails else None)
    monkeypatch.setattr(asyncio, "new_event_loop", MagicMock(return_value=loop))
    monkeypatch.setattr(asyncio, "set_event_loop", set_loop)
    imported = MagicMock(return_value=SimpleNamespace(cli=cli))
    monkeypatch.setattr(importlib, "import_module", imported)
    arguments = ["exec", "derived.toml", "mutation.sqlite"]
    if fails:
        with pytest.raises(RuntimeError) as caught:
            coordinator.execute(arguments)
        assert caught.value is failure
    else:
        coordinator.execute(arguments)
    cli.assert_called_once_with(arguments, standalone_mode=False)
    imported.assert_called_once_with("cosmic_ray.cli")
    assert set_loop.call_args_list == [call(loop), call(None)]
    loop.close.assert_called_once_with()


@pytest.mark.parametrize("nonce", ["expected", "wrong", "early"])
def test_stop_marker_is_private_and_poll_waits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, nonce: str
) -> None:
    path = tmp_path / "stop.json"

    def write_marker(delay: float) -> None:
        assert delay == 0.05
        path.write_text(json.dumps({"nonce": nonce}))

    sleep = MagicMock(side_effect=write_marker)
    monkeypatch.setattr(time, "sleep", sleep)
    if nonce == "expected":
        worker.wait_stop(path, "expected")
    else:
        with pytest.raises(ValueError, match="nonce differs"):
            worker.wait_stop(path, "expected")
    sleep.assert_called_once_with(0.05)


@pytest.mark.parametrize("payload", ["{", "{}", '{"nonce":false}'])
def test_malformed_stop_is_never_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: str
) -> None:
    path = tmp_path / "stop.json"
    path.write_text(payload)
    monkeypatch.setattr(
        time, "sleep", MagicMock(side_effect=AssertionError("published marker polled"))
    )
    with pytest.raises((ValueError, KeyError)):
        worker.wait_stop(path, "expected")


def test_completed_requests_are_journaled_without_response_changes(
    tmp_path: Path,
) -> None:
    (tmp_path / ".quality-results").mkdir()
    trial_source(tmp_path)
    response = web.Response(status=200)
    handler = AsyncMock(return_value=response)
    payload = {"mutations": [{"module_path": "src/item.py", "occurrence": 7}]}
    request = MagicMock(json=AsyncMock(return_value=payload))
    wrapped = worker.journal_handler(tmp_path, handler)
    assert asyncio.run(run_handler(wrapped(request))) is response
    handler.assert_awaited_once_with(request)
    request.json.assert_awaited_once_with()
    entries = (tmp_path / ".quality-results/worker-jobs.jsonl").read_text().splitlines()
    assert [json.loads(item) for item in entries] == [
        {"request": payload, "status": 200}
    ]


@pytest.mark.parametrize("timing", ["before", "after"])
@pytest.mark.parametrize("damage", ["changed", "missing"])
def test_launcher_damage_stops_requests_before_journal_credit(
    tmp_path: Path, timing: str, damage: str
) -> None:
    trial_source(tmp_path)
    launcher = tmp_path / ".quality-results/mutation-trial.py"

    def corrupt() -> None:
        if damage == "missing":
            launcher.unlink()
        else:
            launcher.write_bytes(b"candidate changed the test runner\n")

    async def native(_request: web.Request) -> web.Response:
        corrupt()
        return web.Response(status=200)

    handler = AsyncMock(side_effect=native)
    wrapped = worker.journal_handler(tmp_path, handler)
    if timing == "before":
        corrupt()
    request = MagicMock(json=AsyncMock())

    with pytest.raises((ValueError, FileNotFoundError)):
        asyncio.run(run_handler(wrapped(request)))

    assert handler.await_count == int(timing == "after")
    request.json.assert_not_awaited()
    assert not (tmp_path / ".quality-results/worker-jobs.jsonl").exists()


@pytest.mark.parametrize("fails", [False, True])
@pytest.mark.parametrize("preexisting", [False, True])
def test_readiness_follows_listener_and_always_cleans_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fails: bool, preexisting: bool
) -> None:
    trial_source(tmp_path)
    if preexisting:
        (tmp_path / ".quality-results").mkdir()
    application = MagicMock()
    runner = MagicMock(setup=AsyncMock(), cleanup=AsyncMock())
    site = MagicMock(start=AsyncMock())
    listener = MagicMock(getsockname=MagicMock(return_value=("127.0.0.1", 12345)))
    context = MagicMock(__enter__=MagicMock(return_value=listener))

    async def cleanup() -> None:
        context.__exit__.assert_not_called()

    runner.cleanup = AsyncMock(side_effect=cleanup)
    monkeypatch.setattr(
        worker,
        "socket",
        SimpleNamespace(
            socket=MagicMock(return_value=context),
            AF_INET=socket.AF_INET,
            SOCK_STREAM=socket.SOCK_STREAM,
        ),
    )
    monkeypatch.setattr(web, "Application", MagicMock(return_value=application))
    build = MagicMock(return_value=runner)
    monkeypatch.setattr(web, "AppRunner", build)
    sock_site = MagicMock(return_value=site)
    monkeypatch.setattr(web, "SockSite", sock_site)
    native = AsyncMock()
    monkeypatch.setattr(worker, "native_handler", MagicMock(return_value=native))

    def stop(path: Path, nonce: str) -> None:
        site.start.assert_awaited_once_with()
        assert path == tmp_path / ".quality-results/worker-stop.json"
        assert nonce == "private"
        ready = json.loads((path.parent / "worker-ready.json").read_text())
        assert ready == {"nonce": "private", "url": "http://127.0.0.1:12345"}
        if fails:
            raise RuntimeError("stop failed")

    monkeypatch.setattr(worker, "wait_stop", stop)
    if fails:
        with pytest.raises(RuntimeError, match="stop failed"):
            asyncio.run(worker.serve(tmp_path, "private"))
    else:
        asyncio.run(worker.serve(tmp_path, "private"))
    listener.bind.assert_called_once_with(("127.0.0.1", 0))
    sock_site.assert_called_once_with(runner, listener)
    build.assert_called_once_with(application)
    runner.setup.assert_awaited_once_with()
    runner.cleanup.assert_awaited_once_with()
    context.__exit__.assert_called_once()


def test_worker_runner_and_root_adapters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve = AsyncMock()
    monkeypatch.setattr(worker, "serve", serve)
    worker.worker(tmp_path, "nonce")
    serve.assert_awaited_once_with(tmp_path, "nonce")
    invoked = MagicMock()
    monkeypatch.setattr(worker, "worker", invoked)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["worker", "nonce"])
    runpy.run_module("quality.mutation_worker_main", run_name="__main__")
    invoked.assert_called_once_with(tmp_path, "nonce")
    native = MagicMock()
    monkeypatch.setattr(coordinator, "execute", native)
    monkeypatch.setattr(sys, "argv", ["coordinator", "exec", "config", "db"])
    runpy.run_module("quality.mutation_coordinator_main", run_name="__main__")
    native.assert_called_once_with(["exec", "config", "db"])
