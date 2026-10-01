"""The required stability command varies order/environment and never retries."""

import os
import runpy
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from quality.stability import VARIANTS, run_all, run_variant
from quality.test_order import pytest_collection_modifyitems, shuffled


def test_seeded_collection_is_reproducible_and_nonmutating() -> None:
    original = list(range(10))
    assert shuffled(original, 41) == [0, 9, 8, 2, 4, 7, 1, 3, 5, 6]
    assert shuffled(original, 73) == [5, 0, 6, 2, 3, 8, 9, 7, 1, 4]
    assert original == list(range(10))


def test_pytest_plugin_requires_seed_and_shuffles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    items: list[pytest.Item] = []
    monkeypatch.setenv("RLCI_TEST_ORDER_SEED", "73")
    pytest_collection_modifyitems(items)
    assert items == []
    monkeypatch.delenv("RLCI_TEST_ORDER_SEED")
    with pytest.raises(KeyError):
        pytest_collection_modifyitems(items)
    monkeypatch.setenv("RLCI_TEST_ORDER_SEED", "invalid")
    with pytest.raises(ValueError):
        pytest_collection_modifyitems(items)


def test_variant_runs_full_suite_with_bound_environment(tmp_path: Path) -> None:
    with patch("quality.stability.subprocess.run") as child:
        run_variant(tmp_path, VARIANTS[1])
    child.assert_called_once()
    args, kwargs = child.call_args
    assert args == ([sys.executable, "-m", "pytest", "-p", "quality.test_order", "-q"],)
    assert kwargs["cwd"] == tmp_path
    assert kwargs["check"] is True and kwargs["timeout"] == 600
    assert kwargs["env"]["PYTHONHASHSEED"] == "73"
    assert kwargs["env"]["RLCI_TEST_ORDER_SEED"] == "73"
    assert kwargs["env"]["TZ"] == "UTC-14"
    assert kwargs["env"]["LC_ALL"] == "C.UTF-8"
    assert kwargs["env"]["PATH"] == os.environ["PATH"]


def test_failure_stops_before_second_attempt(tmp_path: Path) -> None:
    failure = subprocess.CalledProcessError(1, ["pytest"])
    with patch("quality.stability.subprocess.run", side_effect=failure) as child:
        with pytest.raises(subprocess.CalledProcessError):
            run_all(tmp_path)
    assert child.call_count == 1


def test_variant_labels_flush_before_each_child(tmp_path: Path) -> None:
    with patch("builtins.print") as label, patch("quality.stability.subprocess.run"):
        run_all(tmp_path)
    assert label.call_count == 2
    assert [call.kwargs["flush"] for call in label.call_args_list] == [True, True]


def test_full_gate_and_registered_entrypoint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with patch("quality.stability.subprocess.run") as child:
        run_all(tmp_path)
    assert child.call_count == 2
    assert capsys.readouterr().out.splitlines() == [
        "stability seed=41 timezone=UTC0 locale=C",
        "stability seed=73 timezone=UTC-14 locale=C.UTF-8",
    ]
    with patch("subprocess.run") as entry_child:
        runpy.run_path(
            str(Path(__file__).resolve().parents[1] / "quality/stability.py"),
            run_name="__main__",
        )
    assert entry_child.call_count == 2


def test_nonmain_module_name_never_runs_the_suite() -> None:
    path = Path(__file__).resolve().parents[1] / "quality/stability.py"
    with patch("subprocess.run") as child, patch("builtins.print") as label:
        runpy.run_path(str(path), run_name="!not-main")
    child.assert_not_called()
    label.assert_not_called()


def test_check_registry_enrolls_stability() -> None:
    import json

    checks = json.loads(
        (Path(__file__).resolve().parents[1] / "quality/checks.json").read_text()
    )
    assert ["python", "-m", "quality.stability"] in checks
