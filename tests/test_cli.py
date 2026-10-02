"""Check process behavior and the same adapter directly for coverage."""

import io
import subprocess
import sys

import pytest

from interval_normalizer_generated_py.cli import main, run


@pytest.mark.parametrize(
    ("text", "code", "out", "err"),
    [
        ("[[5,8],[1,3],[2,6]]", 0, "[[1,8]]\n", ""),
        ("[]", 0, "[]\n", ""),
        ("bad json", 2, "", "error: invalid JSON\n"),
        ("", 2, "", "error: invalid JSON\n"),
        ("[[1,1]]", 2, "", "error: interval start must be less than end\n"),
    ],
)
def test_adapter(text: str, code: int, out: str, err: str) -> None:
    stdout, stderr = io.StringIO(), io.StringIO()
    assert run(io.StringIO(text), stdout, stderr) == code
    assert stdout.getvalue() == out
    assert stderr.getvalue() == err


def test_main_uses_standard_streams(monkeypatch: pytest.MonkeyPatch) -> None:
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdin", io.StringIO("[]"))
    monkeypatch.setattr(sys, "stdout", stdout)
    assert main() == 0
    assert stdout.getvalue() == "[]\n"


@pytest.mark.parametrize(("text", "code"), [("[[1,2]]", 0), ("null", 2)])
def test_installed_console_script(text: str, code: int) -> None:
    result = subprocess.run(
        ["interval-normalizer-generated-py"],
        input=text,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == code
    if code == 0:
        assert result.stdout == "[[1,2]]\n"
        assert result.stderr == ""
        return
    assert result.stdout == ""
    assert result.stderr == "error: input must be an array of intervals\n"
