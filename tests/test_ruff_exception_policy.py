"""Native Ruff checks must reject swallowed exceptions and unsafe finally exits."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMMAND = [
    sys.executable,
    "-m",
    "ruff",
    "check",
    "--stdin-filename",
    "src/relentless_example/exception_probe.py",
    "-",
]


def lint(source: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        COMMAND,
        input=source,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=ROOT,
        timeout=15,
        check=False,
    )


def test_exception_propagation_is_allowed() -> None:
    result = lint(
        "def safe() -> int:\n"
        "    try:\n"
        "        return 1\n"
        "    except ValueError:\n"
        "        raise\n"
    )
    assert result.returncode == 0


@pytest.mark.parametrize(
    ("source", "rule"),
    [
        (
            "def bad() -> None:\n"
            "    try:\n"
            "        raise ValueError\n"
            "    except Exception:\n"
            "        pass\n",
            "S110",
        ),
        (
            "def bad() -> int:\n"
            "    try:\n"
            "        return 1\n"
            "    finally:\n"
            "        return 2\n",
            "B012",
        ),
    ],
)
def test_exception_weakening_is_rejected(source: str, rule: str) -> None:
    result = lint(source)
    assert result.returncode != 0
    assert rule in result.stdout
