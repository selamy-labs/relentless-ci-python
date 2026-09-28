"""Run tools with explicit arguments, no shell, and a bounded execution time."""

import subprocess
from pathlib import Path


def run(
    command: list[str],
    root: Path,
    timeout: float,
    env: dict[str, str],
) -> None:
    """A missing tool, nonzero exit or timeout is a verification failure."""
    subprocess.run(command, cwd=root, env=env, timeout=timeout, check=True)
