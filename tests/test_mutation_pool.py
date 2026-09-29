"""Complete native execution wiring, all-owner shutdown and restoration checks."""

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from quality import mutation_config as config
from quality import mutation_pool as pool
from quality.mutation_services import Worker
from quality.owned_commands import SupervisionUnproven
from tests.test_mutation_services import instance


def test_execution_config_changes_only_native_transport(tmp_path: Path) -> None:
    original = (
        '[cosmic-ray]\nmodule-path=["src","quality"]\ntimeout=30.0\n'
        'excluded-modules=[]\ntest-command="python -m pytest -x -q"\n'
        '[cosmic-ray.distributor]\nname="local"\n'
    )
    path = tmp_path / "cosmic-ray.toml"
    path.write_text(original)
    derived = config.execution_config(path, ["http://127.0.0.1:123"])
    assert path.read_text() == original
    assert derived.name == "mutation-execution.toml"
    assert 'name = "http"' in derived.read_text()
    assert "timeout = 30.0" in derived.read_text()
    assert 'test-command = "python -m pytest -x -q"' in derived.read_text()


@pytest.mark.parametrize(
    "fault", ["base", "serialization", "changed-low", "changed-high"]
)
def test_configuration_loss_or_replacement_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    path = tmp_path / "cosmic-ray.toml"
    path.write_text(
        '[cosmic-ray]\ntimeout=30\n[cosmic-ray.distributor]\nname="local"\n'
    )
    if fault == "base":
        path.write_text('[cosmic-ray.distributor]\nname="http"\n')

    def serialize(value: object) -> str:
        if fault.startswith("changed"):
            path.write_text(
                {"changed-low": "# changed\n", "changed-high": "changed"}[fault]
            )
            return '[cosmic-ray]\ntimeout=30\n[cosmic-ray.distributor]\nname="http"\n[cosmic-ray.distributor.http]\nworker-urls=["http://127.0.0.1:123"]\n'
        return "[cosmic-ray]\ntimeout=29\n"

    monkeypatch.setattr(
        importlib,
        "import_module",
        MagicMock(return_value=SimpleNamespace(serialize_config=serialize)),
    )
    with pytest.raises(ValueError):
        config.execution_config(path, ["http://127.0.0.1:123"])
    assert not (tmp_path / "mutation-execution.toml").exists()


@pytest.mark.parametrize("fails", [False, True])
def test_execution_has_unchanged_deadline_and_always_shuts_every_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fails: bool
) -> None:
    worker = instance(tmp_path / "worker")
    snapshot = MagicMock(side_effect=[{"source": b"same"} for _ in range(3)])
    monkeypatch.setattr(pool, "snapshot", snapshot)

    def start(
        root: Path, timeout: float, env: dict[str, str], workers: list[Worker]
    ) -> list[str]:
        assert (root, timeout, env) == (tmp_path, 3600, {"EXACT": "value"})
        workers.append(worker)
        return ["http://127.0.0.1:123"]

    monkeypatch.setattr(pool, "start_pool", start)
    derive = MagicMock(return_value=tmp_path / "mutation-execution.toml")
    monkeypatch.setattr(pool, "execution_config", derive)
    error = RuntimeError("coordinator failed")
    run = MagicMock(side_effect=error if fails else None)
    monkeypatch.setattr(pool, "run_owned", run)
    shutdown = MagicMock(return_value=[])
    monkeypatch.setattr(pool, "shutdown", shutdown)
    if fails:
        with pytest.raises(ExceptionGroup) as caught:
            pool.execute_pool(tmp_path, 3600, {"EXACT": "value"})
        assert caught.value.exceptions == (error,)
    else:
        assert pool.execute_pool(tmp_path, 3600, {"EXACT": "value"}) == [worker]
    run.assert_called_once_with(
        [
            sys.executable,
            "-m",
            "quality.mutation_coordinator_main",
            "exec",
            "mutation-execution.toml",
            "mutation.sqlite",
        ],
        tmp_path,
        3600,
        {"EXACT": "value"},
    )
    derive.assert_called_once_with(
        tmp_path / "cosmic-ray.toml", ["http://127.0.0.1:123"]
    )
    shutdown.assert_called_once_with([worker])


@pytest.mark.parametrize(
    "distributor", ['name="http"', 'name="a"', 'name="local"\nextra=1', ""]
)
def test_nonlocal_or_extended_base_distributor_fails_before_loading_sdk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, distributor: str
) -> None:
    path = tmp_path / "cosmic-ray.toml"
    path.write_text("[cosmic-ray.distributor]\n" + distributor + "\n")
    imported = MagicMock(side_effect=AssertionError("SDK loaded before validation"))
    monkeypatch.setattr(importlib, "import_module", imported)

    with pytest.raises(ValueError, match="base distributor"):
        config.execution_config(path, ["http://127.0.0.1:123"])

    imported.assert_not_called()
    assert not (tmp_path / "mutation-execution.toml").exists()


def test_partial_start_failure_keeps_live_owner_in_failure_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker = instance(tmp_path / "worker")
    monkeypatch.setattr(pool, "snapshot", MagicMock(return_value={}))
    startup = TimeoutError("not ready")
    cleanup = SupervisionUnproven(123, tmp_path, "live")

    def start(
        root: Path, timeout: float, env: dict[str, str], workers: list[Worker]
    ) -> list[str]:
        workers.append(worker)
        raise startup

    monkeypatch.setattr(pool, "start_pool", start)
    shutdown = MagicMock(return_value=[cleanup])
    monkeypatch.setattr(pool, "shutdown", shutdown)
    with pytest.raises(ExceptionGroup) as caught:
        pool.execute_pool(tmp_path, 3600, {})
    assert caught.value.exceptions == (startup, cleanup)
    shutdown.assert_called_once_with([worker])


@pytest.mark.parametrize("duplicates", [False, True])
def test_start_registers_every_live_handle_before_readiness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, duplicates: bool
) -> None:
    first, second = instance(tmp_path / "first"), instance(tmp_path / "second")
    launch = MagicMock(side_effect=[first, second])
    monkeypatch.setattr(pool, "worker_count", MagicMock(return_value=2))
    monkeypatch.setattr(pool, "launch", launch)
    workers: list[Worker] = []

    def ready(worker: Worker) -> str:
        assert workers[-1] is worker
        return "http://127.0.0.1:123" if duplicates else str(worker.root)

    monkeypatch.setattr(pool, "ready", ready)
    if duplicates:
        with pytest.raises(ValueError, match="duplicated"):
            pool.start_pool(tmp_path, 3600, {}, workers)
    else:
        assert pool.start_pool(tmp_path, 3600, {}, workers) == [
            str(first.root),
            str(second.root),
        ]
    assert workers == [first, second]


@pytest.mark.parametrize("changed", ["root", "worker"])
def test_every_copy_must_restore_all_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed: str
) -> None:
    worker = instance(tmp_path / "worker")
    values = (
        [{"source": b"different"}]
        if changed == "root"
        else [{"source": b"same"}, {"source": b"different"}]
    )
    monkeypatch.setattr(pool, "snapshot", MagicMock(side_effect=values))
    with pytest.raises(ValueError, match="inputs changed"):
        pool.require_restored(tmp_path, [worker], {"source": b"same"})
