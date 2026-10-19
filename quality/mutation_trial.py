"""Retain actual pytest streams and signed status inside the native trial output."""

import json
import subprocess
import sys
from pathlib import Path
from typing import TypedDict

COVERAGE = ".quality-results/mutation-coverage.json"


class Coverage(TypedDict):
    """Pristine sources and test-function indices for each mapped source line."""

    tests: list[str]
    sources: dict[str, str]
    lines: dict[str, dict[str, list[int]]]


def run_trial() -> int:
    """The native Cosmic Ray deadline still bounds this whole process group."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-x", "-q", "--color=no", *selected()],
        capture_output=True,
        text=True,
        check=False,
    )
    print(
        json.dumps(
            {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
    )
    if result.stderr:
        return 2
    return result.returncode


def selected() -> list[str]:
    """No map, no single changed source or any unmapped line keeps every test."""
    if not Path(COVERAGE).is_file():
        return []
    data: Coverage = json.loads(Path(COVERAGE).read_text(encoding="utf-8"))
    changed = [
        name
        for name, text in data["sources"].items()
        if Path(name).read_text(encoding="utf-8") != text
    ]
    if len(changed) != 1:
        return []
    (name,) = changed
    return covering(data, name)


def covering(data: Coverage, name: str) -> list[str]:
    """Union the recorded test functions of every changed original line."""
    current = Path(name).read_text(encoding="utf-8")
    lines = [str(line) for line in changed_lines(data["sources"][name], current)]
    mapped = data["lines"][name]
    if not all(line in mapped for line in lines):
        return []
    indices = sorted({index for line in lines for index in mapped[line]})
    return [data["tests"][index] for index in indices]


def changed_lines(before: str, after: str) -> list[int]:
    """Only same-length edits are located; added or removed lines select all."""
    original, current = before.splitlines(), after.splitlines()
    if len(original) != len(current):
        return []
    numbered = enumerate(original, start=1)
    return [number for number, line in numbered if line != current[number - 1]]
