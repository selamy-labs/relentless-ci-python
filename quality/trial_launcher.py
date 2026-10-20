"""Reproduce a fixed trial launcher before mutations and protect its exact bytes."""

from pathlib import Path


def launcher_path(root: Path) -> Path:
    """The runtime copy is generated; its authored source remains fully enrolled."""
    return root / ".quality-results" / "mutation-trial.py"


def coverage_path(root: Path) -> Path:
    """The trial reads this relative copy from the worker's working directory."""
    return root / ".quality-results" / "mutation-coverage.json"


def pristine_path(root: Path) -> Path:
    """Selections the coordinator validated on pristine sources before any mutant."""
    return root / ".quality-results" / "mutation-pristine.json"


def selection_paths(root: Path) -> tuple[Path, Path]:
    return coverage_path(root), pristine_path(root)


def require_selection(root: Path, expected: list[bytes]) -> None:
    """Trials may not change the selection or pristine credit of later mutants."""
    if [path.read_bytes() for path in selection_paths(root)] != expected:
        raise ValueError("mutation selection inputs changed")


def prepare_launcher(root: Path) -> bytes:
    """Always replace stale launchers with the current immutable source snapshot."""
    source = (root / "quality" / "mutation_trial.py").read_bytes()
    path = launcher_path(root)
    path.parent.mkdir(exist_ok=True)
    launcher = source + b"\nraise SystemExit(run_trial())\n"
    path.write_bytes(launcher)
    return launcher


def require_launcher(root: Path, expected: bytes) -> None:
    """Neither a candidate nor a test may alter the runner used by later trials."""
    if launcher_path(root).read_bytes() != expected:
        raise ValueError("generated mutation trial launcher changed")
