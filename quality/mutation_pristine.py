"""Establish every narrowed command on pristine sources before any mutant runs."""

import importlib
import json
import sqlite3
import subprocess
import sys
import tomllib
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from subprocess import TimeoutExpired
from typing import Protocol

from quality.mutation_inputs import copy_inputs, environment, snapshot
from quality.mutation_services import worker_count
from quality.mutation_trial import Coverage, command, covering
from quality.owned_commands import OwnedCommand, finish_owned, start_owned
from quality.trial_launcher import coverage_path, pristine_path

SHARD = ".quality-results/pristine-shard.json"
PASSED = ".quality-results/pristine-passed.json"
SPECS = "SELECT module_path, operator_name, operator_args, occurrence"


class Operator(Protocol):
    def __call__(self, **arguments: object) -> object: ...


def establish(root: Path, timeout: float, env: dict[str, str]) -> bytes:
    """Only the coordinator writes credit; workers receive a byte-bound copy."""
    selections = planned(root)
    count = worker_count()
    shards = [selections[index::count] for index in range(count)]
    copies = [prepare(root, index, shard) for index, shard in enumerate(shards)]
    run_shards(root, copies, timeout, env)
    passed = [tests for copy in copies for tests in read_passed(copy)]
    encoded = json.dumps(sorted(passed)).encode("utf-8")
    pristine_path(root).write_bytes(encoded)
    return encoded


def planned(root: Path) -> list[list[str]]:
    """Apply each native mutation in memory and keep its distinct narrowing."""
    data: Coverage = json.loads(coverage_path(root).read_text(encoding="utf-8"))
    mutate = mutator()
    selections: set[tuple[str, ...]] = set()
    with closing(sqlite3.connect(root / "mutation.sqlite")) as database:
        rows: list[tuple[str, str, str, int]] = database.execute(
            f"{SPECS} FROM mutation_specs"
        ).fetchall()
    for name, operator, arguments, occurrence in rows:
        mutated = mutate(data["sources"][name], operator, arguments, occurrence)
        selections.add(tuple(covering(data, name, mutated)))
    return sorted(list(tests) for tests in selections if tests)


def mutator() -> Callable[[str, str, str, int], str]:
    """The pinned SDK owns operator lookup, arguments and occurrence order."""
    plugins = importlib.import_module("cosmic_ray.plugins")
    mutating = importlib.import_module("cosmic_ray.mutating")
    lookup: Callable[[str], Operator] = plugins.get_operator
    mutate_code: Callable[[str, object, int], object] = mutating.mutate_code

    def mutate(code: str, name: str, stored: str, occurrence: int) -> str:
        """An inapplicable mutation leaves the code unchanged, selecting nothing."""
        # The native database stores JSON-encoded argument text in a JSON column.
        arguments: dict[str, object] = json.loads(json.loads(stored))
        mutated = mutate_code(code, lookup(name)(**arguments), occurrence)
        if isinstance(mutated, str):
            return mutated
        return code

    return mutate


def prepare(root: Path, index: int, shard: list[list[str]]) -> Path:
    target = root / ".quality-results" / f"mutation-pristine-{index}"
    target.mkdir()
    copy_inputs(root, target)
    (target / ".quality-results").mkdir()
    (target / SHARD).write_text(json.dumps(shard), encoding="utf-8")
    return target


def run_shards(
    root: Path, copies: list[Path], timeout: float, env: dict[str, str]
) -> None:
    """Start every shard before waiting; retain every failure and live handle."""
    before = snapshot(root)
    owned: list[OwnedCommand] = []
    errors: list[BaseException] = []
    start_shards(copies, timeout, env, owned, errors)
    for handle in owned:
        capture_finish(handle, timeout, errors)
    if errors:
        raise BaseExceptionGroup("pristine selection validation failed", errors)
    if any(snapshot(copy) != before for copy in copies):
        raise ValueError("pristine selection inputs changed or were not restored")


def start_shards(
    copies: list[Path],
    timeout: float,
    env: dict[str, str],
    owned: list[OwnedCommand],
    errors: list[BaseException],
) -> None:
    """A failed start stops later starts but keeps every started handle."""
    try:
        for copy in copies:
            owned.append(start_shard(copy, timeout, env))
    except BaseException as error:
        errors.append(error)


def start_shard(copy: Path, timeout: float, env: dict[str, str]) -> OwnedCommand:
    arguments = [sys.executable, "-m", "quality.mutation_pristine_main"]
    return start_owned(arguments, copy, timeout, environment(copy, env))


def capture_finish(
    handle: OwnedCommand, timeout: float, errors: list[BaseException]
) -> None:
    try:
        finish_owned(handle, timeout)
    except BaseException as error:
        errors.append(error)


def read_passed(copy: Path) -> list[list[str]]:
    value: list[list[str]] = json.loads((copy / PASSED).read_text(encoding="utf-8"))
    return value


def run_shard(root: Path) -> None:
    """Runs inside an isolated pristine copy, exactly as a worker trial would."""
    shard: list[list[str]] = json.loads((root / SHARD).read_text(encoding="utf-8"))
    limit = trial_limit(root)
    passed = [tests for tests in shard if passes(tests, limit)]
    (root / PASSED).write_text(json.dumps(passed), encoding="utf-8")


def trial_limit(root: Path) -> float:
    """Pristine validation shares the native per-trial deadline."""
    config = tomllib.loads((root / "cosmic-ray.toml").read_text(encoding="utf-8"))
    return float(config["cosmic-ray"]["timeout"])


def passes(tests: list[str], limit: float) -> bool:
    """Only pytest status 0 with empty stderr validates a narrowed command."""
    try:
        result = subprocess.run(
            command(tests), capture_output=True, text=True, check=False, timeout=limit
        )
    except (OSError, TimeoutExpired):
        return False
    return not result.returncode and not result.stderr
