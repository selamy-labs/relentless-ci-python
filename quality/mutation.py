"""Always execute mutations in a fresh copy of source and tests."""

import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from quality.commands import run
from quality.mutation_report import verify_session

INPUTS = ("src", "tests", "quality")
CONFIGURATION = ("pyproject.toml", "cosmic-ray.toml", "uv.lock")


def snapshot(root: Path) -> dict[str, bytes]:
    """Bind a run to every authored Python input, including never-imported files."""
    paths = [
        path
        for directory in INPUTS
        for path in (root / directory).rglob("*")
        if path.suffix in {".py", ".json"}
    ]
    paths.extend(root / name for name in CONFIGURATION)
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in paths}


def copy_inputs(root: Path, target: Path) -> None:
    """Copy source and declarative configuration without environments or caches."""
    for directory in INPUTS:
        shutil.copytree(
            root / directory,
            target / directory,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    for name in CONFIGURATION:
        shutil.copy2(root / name, target / name)


def mutate(root: Path, timeout: float) -> int:
    """Fresh initialization and baseline are required; cached outcomes are unused."""
    before = snapshot(root)
    with TemporaryDirectory(prefix="relentless-mutation-") as directory:
        target = Path(directory)
        copy_inputs(root, target)
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join([str(target / "src"), str(target)])
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        commands = (
            ["cosmic-ray", "init", "cosmic-ray.toml", "mutation.sqlite"],
            ["cosmic-ray", "baseline", "cosmic-ray.toml"],
            ["cosmic-ray", "exec", "cosmic-ray.toml", "mutation.sqlite"],
        )
        for command in commands:
            run(command, target, timeout, env)
        output = root / ".quality-results"
        output.mkdir(exist_ok=True)
        latest = output / "mutation-latest.sqlite"
        shutil.copy2(target / "mutation.sqlite", latest)
        count = verify_session(latest)
        if snapshot(target) != before or snapshot(root) != before:
            raise ValueError("mutation inputs changed or were not restored")
        shutil.copy2(latest, output / "mutation.sqlite")
    return count
