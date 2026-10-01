"""The installed API, registered CLI and native typing consumer are all required."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from quality import package_consumer


@pytest.mark.parametrize(
    ("platform", "relative"), [("posix", "bin/tool"), ("nt", "Scripts/tool.exe")]
)
def test_portable_executable(tmp_path: Path, platform: str, relative: str) -> None:
    assert (
        package_consumer.executable(tmp_path, "tool", platform) == tmp_path / relative
    )


def test_unknown_platform_cannot_guess_an_executable(tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        package_consumer.executable(tmp_path, "tool", "unknown")


def test_isolated_consumer_commands_and_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheel = tmp_path / "package.whl"
    received: list[list[str]] = []
    roots: list[Path] = []
    probes: list[tuple[list[str], str, tuple[int, str, str]]] = []
    guards: list[Path] = []

    def command(
        arguments: list[str], root: Path, timeout: float, env: dict[str, str]
    ) -> None:
        roots.append(root)
        received.append(arguments)
        assert timeout == 120
        assert env["PYTHONWARNINGS"] == "error"
        assert "PYTHONPATH" not in env
        if arguments[1:3] == ["-m", "mypy"]:
            assert (root / "consumer.py").read_text() == (
                "from typing import assert_type\n"
                "from relentless_example import normalize\n"
                "assert_type(normalize([[0, 1]]), list[list[int]])\n"
            )

    def probe(
        arguments: list[str], root: Path, document: str, wanted: tuple[int, str, str]
    ) -> None:
        assert root == roots[0]
        probes.append((arguments, document, wanted))

    monkeypatch.setattr(package_consumer, "run", command)
    monkeypatch.setattr(package_consumer, "expect", probe)
    monkeypatch.setattr(package_consumer, "install_guard", guards.append)
    package_consumer.installed_consumer(wheel)
    root = roots[0]
    python = str(package_consumer.executable(root / "environment", "python", os.name))
    cli = [
        str(
            package_consumer.executable(
                root / "environment", "relentless-example", os.name
            )
        )
    ]
    assert received == [
        [
            "uv",
            "venv",
            str(root / "environment"),
            "--python",
            sys.executable,
            "--no-python-downloads",
        ],
        [
            "uv",
            "pip",
            "install",
            "--offline",
            "--no-deps",
            "--python",
            python,
            str(wheel),
        ],
        [
            sys.executable,
            "-m",
            "mypy",
            "--strict",
            "--no-incremental",
            "--python-executable",
            python,
            str(root / "consumer.py"),
        ],
    ]
    assert probes == [
        (
            [python, "-I", "-W", "error", "-c", package_consumer.API_PROGRAM],
            "[[3,5],[0,2],[2,4],[8,10]]",
            (0, "[[0,5],[8,10]]\n", ""),
        ),
        (cli, "[[3,5],[0,2],[2,4],[8,10]]", (0, "[[0,5],[8,10]]\n", "")),
        (cli, "{", (2, "", "error: invalid JSON\n")),
        (
            cli,
            "[[0,1000001]]",
            (2, "", "error: endpoints must be between -1000000 and 1000000\n"),
        ),
    ]
    assert all(item == root for item in roots)
    assert guards == [root / "environment"]
    assert not root.exists()


def test_failed_install_stops_probes_and_cleans_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roots: list[Path] = []

    def failure(
        arguments: list[str], root: Path, _timeout: float, _env: dict[str, str]
    ) -> None:
        roots.append(root)
        raise subprocess.CalledProcessError(1, arguments)

    monkeypatch.setattr(package_consumer, "run", failure)
    with pytest.raises(subprocess.CalledProcessError):
        package_consumer.installed_consumer(tmp_path / "archive.whl")
    assert len(roots) == 1
    assert not roots[0].exists()
