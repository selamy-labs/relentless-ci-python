"""Retain actual pytest streams and signed status inside the native trial output."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import TypedDict

COVERAGE = ".quality-results/mutation-coverage.json"
PRISTINE = ".quality-results/mutation-pristine.json"


class Coverage(TypedDict):
    """Pristine sources and test-function indices for each mapped source line."""

    tests: list[str]
    sources: dict[str, str]
    lines: dict[str, dict[str, list[int]]]


def run_trial() -> int:
    """The native Cosmic Ray deadline still bounds this whole process group."""
    result = pytest(selected())
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


def command(tests: list[str]) -> list[str]:
    return [sys.executable, "-m", "pytest", "-x", "-q", "--color=no", *tests]


def pytest(tests: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command(tests),
        capture_output=True,
        text=True,
        check=False,
    )


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
    return validated(data, name, covering(data, name))


def validated(data: Coverage, name: str, tests: list[str]) -> list[str]:
    """A narrowed command earns credit only if it also passes on pristine sources."""
    if tests and pristine_passes(data, name, tests):
        return tests
    return []


def pristine_passes(data: Coverage, name: str, tests: list[str]) -> bool:
    """Cache by the exact pristine sources and the exact selected command."""
    encoded = json.dumps([data["sources"], command(tests)]).encode("utf-8")
    key = hashlib.sha256(encoded).hexdigest()
    cache = read_pristine()
    if key not in cache:
        cache[key] = pristine_run(data, name, tests)
        temporary = Path(PRISTINE + ".tmp")
        temporary.write_text(json.dumps(cache), encoding="utf-8")
        temporary.replace(PRISTINE)
    return cache[key]


def read_pristine() -> dict[str, bool]:
    """A missing or unreadable cache is re-established, never trusted."""
    try:
        value: dict[str, bool] = json.loads(Path(PRISTINE).read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return value


def pristine_run(data: Coverage, name: str, tests: list[str]) -> bool:
    """Run the same selection on the restored module, then put the mutant back."""
    path = Path(name)
    mutated = path.read_bytes()
    path.write_text(data["sources"][name], encoding="utf-8")
    try:
        result = pytest(tests)
    except OSError:
        return False
    finally:
        path.write_bytes(mutated)
    return not result.returncode and not result.stderr


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
