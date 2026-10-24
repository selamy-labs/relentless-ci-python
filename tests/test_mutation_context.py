"""The coverage plugin exports one test's context only while that test runs."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from quality import mutation_context

NAMES = ("COVERAGE_PROCESS_START", "MUTATION_TEST_CONTEXT")


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("MUTATION_COVERAGE_RC", "/work/settings.toml")
    for name in NAMES:
        monkeypatch.delenv(name, raising=False)
    return "/work/settings.toml"


def test_context_is_exported_during_the_test_and_removed_after(settings: str) -> None:
    hook = mutation_context.pytest_runtest_protocol(
        MagicMock(nodeid="tests/test_a.py::test_x[1]")
    )
    next(hook)
    assert os.environ["COVERAGE_PROCESS_START"] == settings
    assert (
        os.environ["MUTATION_TEST_CONTEXT"] == "tests/test_a.py::test_x[1]|subprocess"
    )
    with pytest.raises(StopIteration) as stopped:
        hook.send("outcome")
    assert stopped.value.value == "outcome"
    assert not set(NAMES) & set(os.environ)


def test_context_is_removed_when_the_test_protocol_fails(settings: str) -> None:
    hook = mutation_context.pytest_runtest_protocol(MagicMock(nodeid="t"))
    next(hook)
    assert os.environ["MUTATION_COVERAGE_RC"] == settings
    with pytest.raises(KeyError, match="protocol"):
        hook.throw(KeyError("protocol"))
    assert not set(NAMES) & set(os.environ)


def test_plugin_registers_as_a_pytest_wrapper(tmp_path: Path) -> None:
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    probe = tmp_path / "test_probe.py"
    probe.write_text(
        "import os\n\n\ndef test_env():\n"
        "    assert os.environ['MUTATION_TEST_CONTEXT'] == "
        "'test_probe.py::test_env|subprocess'\n"
        "    assert os.environ['COVERAGE_PROCESS_START'] == '/work/settings.toml'\n"
    )
    env = {
        name: value
        for name, value in os.environ.items()
        if name not in NAMES and not name.startswith("PYTEST_")
    }
    env["MUTATION_COVERAGE_RC"] = "/work/settings.toml"
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            "quality.mutation_context",
            str(probe),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    assert "1 passed" in result.stdout
