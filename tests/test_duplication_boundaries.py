"""Real pinned-scanner probes at token and inclusive-line boundaries."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from quality.duplication import verify_duplication


def boundary_expression(index: int, tokens: int) -> str:
    expression = "alpha + beta + gamma + delta"
    if tokens == 85:
        return expression + " + epsilon + zeta + eta + theta"
    if index < 2:
        expression += " + epsilon"
    return "-" + expression if tokens == 50 and index == 0 else expression


def duplicate_source(lines: int, tokens: int) -> str:
    names = ("first", "second", "third", "fourth", "fifth")
    return (
        "\n".join(
            f"{name} = {boundary_expression(index, tokens)}"
            for index, name in enumerate(names[:lines])
        )
        + "\n"
    )


@pytest.mark.parametrize(
    ("lines", "tokens", "clone"),
    [(4, 85, False), (5, 85, True), (5, 49, False), (5, 50, True)],
)
def test_native_duplicate_boundaries(
    tmp_path: Path, lines: int, tokens: int, clone: bool
) -> None:
    for name in ("mise.toml", "mise.lock"):
        shutil.copy2(Path.cwd() / name, tmp_path / name)
    content = duplicate_source(lines, tokens)
    for name in ("src/a.py", "tests/test_b.py"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    output = tmp_path / ".quality-results/duplication"
    if clone:
        with pytest.raises(subprocess.CalledProcessError):
            verify_duplication(tmp_path)
    else:
        verify_duplication(tmp_path)
        assert (output / "verified.json").is_file()
    report = json.loads((output / "combined/jscpd-report.json").read_text())
    assert bool(report["duplicates"]) is clone
    if clone:
        assert report["duplicates"][0]["tokens"] == tokens
        assert report["duplicates"][0]["lines"] == lines
