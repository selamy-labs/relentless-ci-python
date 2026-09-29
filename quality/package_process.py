"""Bound consumer commands and keep checkout import overrides out of children."""

import os
import subprocess
from pathlib import Path

TIMEOUT = 120


def environment() -> dict[str, str]:
    blocked = {"PYTHONPATH", "PYTHONHOME", "MYPYPATH", "PYTHONOPTIMIZE"}
    env = {key: value for key, value in os.environ.items() if key not in blocked}
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONWARNINGS"] = "error"
    return env


def expect(
    command: list[str], root: Path, document: str, wanted: tuple[int, str, str]
) -> None:
    result = subprocess.run(
        command,
        cwd=root,
        env=environment(),
        input=document,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=TIMEOUT,
        check=False,
    )
    if (result.returncode, result.stdout, result.stderr) != wanted:
        raise ValueError("installed consumer exit status or output differs")
