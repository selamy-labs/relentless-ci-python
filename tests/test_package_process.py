"""Consumer output, errors and import isolation are enforced by native children."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from quality import package_process


def test_environment_strips_checkout_imports(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        os,
        "environ",
        {
            "PYTHONPATH": "checkout",
            "PYTHONHOME": "other-runtime",
            "MYPYPATH": "types",
            "PYTHONOPTIMIZE": "2",
            "PYTHONNOUSERSITE": "0",
            "PYTHONWARNINGS": "ignore",
            "PATH": "tools",
            "KEEP": "value",
        },
    )
    assert package_process.environment() == {
        "PATH": "tools",
        "KEEP": "value",
        "PYTHONNOUSERSITE": "1",
        "PYTHONWARNINGS": "error",
    }


def test_native_output_and_input(tmp_path: Path) -> None:
    package_process.expect(
        [
            sys.executable,
            "-c",
            "import sys; print(sys.stdin.read()); sys.stderr.write('err')",
        ],
        tmp_path,
        "input",
        (0, "input\n", "err"),
    )


def test_expected_nonzero_consumer_result(tmp_path: Path) -> None:
    package_process.expect(
        [sys.executable, "-c", "import sys; sys.stderr.write('invalid'); sys.exit(2)"],
        tmp_path,
        "",
        (2, "", "invalid"),
    )


def test_bounded_structured_process_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[object, dict[str, object]]] = []

    def child(
        arguments: list[str], **options: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append((arguments, options))
        return subprocess.CompletedProcess(arguments, 0, "out", "err")

    monkeypatch.setattr(subprocess, "run", child)
    package_process.expect(
        ["tool", "argument with spaces"], tmp_path, "input", (0, "out", "err")
    )
    assert calls == [
        (
            ["tool", "argument with spaces"],
            {
                "cwd": tmp_path,
                "env": package_process.environment(),
                "input": "input",
                "capture_output": True,
                "text": True,
                "encoding": "utf-8",
                "timeout": 120,
                "check": False,
            },
        )
    ]


@pytest.mark.parametrize(
    "wanted", [(1, "output\n", ""), (0, "wrong", ""), (0, "output\n", "unexpected")]
)
def test_native_output_difference(tmp_path: Path, wanted: tuple[int, str, str]) -> None:
    with pytest.raises(ValueError, match="consumer exit status or output"):
        package_process.expect(
            [sys.executable, "-c", "print('output')"], tmp_path, "", wanted
        )


def test_native_warning_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="consumer exit status or output"):
        package_process.expect(
            [sys.executable, "-c", "import warnings; warnings.warn('bad')"],
            tmp_path,
            "",
            (0, "", ""),
        )


def test_missing_command_cannot_pass(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        package_process.expect([str(tmp_path / "missing")], tmp_path, "", (0, "", ""))


def test_native_timeout_cannot_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(package_process, "TIMEOUT", 0.02)
    with pytest.raises(subprocess.TimeoutExpired):
        package_process.expect(
            [sys.executable, "-c", "import time; time.sleep(1)"],
            tmp_path,
            "",
            (0, "", ""),
        )
