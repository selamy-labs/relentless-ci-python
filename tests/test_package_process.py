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
            "GITHUB_TOKEN": "private",
        },
    )
    assert package_process.environment() == {
        "PATH": "tools",
        "PYTHONNOUSERSITE": "1",
        "PYTHONWARNINGS": "error",
    }
    consumer = package_process.environment(Path("/consumer"))
    assert consumer["HOME"] == "/consumer"
    assert consumer["TMPDIR"] == "/consumer"
    assert consumer["RLCI_CONSUMER_ROOT"] == "/consumer"
    assert "GITHUB_TOKEN" not in consumer


@pytest.mark.parametrize("platform", ["posix", "nt"])
def test_guard_installs_in_the_consumer_site_and_refuses_replacement(
    tmp_path: Path, platform: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    site = package_process.site_packages(tmp_path, platform)
    site.mkdir(parents=True)
    monkeypatch.setattr(
        package_process, "os", type("Platform", (), {"name": platform})()
    )
    package_process.install_guard(tmp_path)
    assert (site / "sitecustomize.py").read_text() == package_process.GUARD
    with pytest.raises(ValueError, match="already owns sitecustomize"):
        package_process.install_guard(tmp_path)


def test_missing_consumer_site_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="site-packages is missing"):
        package_process.install_guard(tmp_path)


@pytest.mark.parametrize(
    ("program", "message"),
    [
        ("print('clean')", "clean"),
        ("import socket; socket.socket()", "network or child process denied"),
        (
            "import socket; socket.create_connection(('127.0.0.1', 9))",
            "network or child process denied",
        ),
        (
            "import subprocess; subprocess.run(['true'])",
            "network or child process denied",
        ),
        ("import os; os.system('true')", "network or child process denied"),
        (
            "from pathlib import Path; Path('../outside').write_text('bad')",
            "write outside temporary root denied",
        ),
        (
            "import os; os.open('../outside', os.O_CREAT | os.O_WRONLY)",
            "write outside temporary root denied",
        ),
        ("import os; os.mkdir('../outside')", "write outside temporary root denied"),
        (
            "from pathlib import Path; Path('inside').write_text('ok'); print('ok')",
            "ok",
        ),
    ],
)
def test_native_guard_blocks_network_children_and_outside_writes(
    tmp_path: Path, program: str, message: str
) -> None:
    virtual = tmp_path / "environment"
    subprocess.run(
        [
            "uv",
            "venv",
            str(virtual),
            "--python",
            sys.executable,
            "--no-python-downloads",
        ],
        check=True,
        capture_output=True,
    )
    package_process.install_guard(virtual)
    python = virtual / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    result = subprocess.run(
        [str(python), "-I", "-c", program],
        cwd=tmp_path,
        env=package_process.environment(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    if message in {"clean", "ok"}:
        assert result.returncode == 0 and result.stdout.strip() == message
        assert result.stderr == ""
    else:
        assert result.returncode != 0 and message in result.stderr


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
                "env": package_process.environment(tmp_path),
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
