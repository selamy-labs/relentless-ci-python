"""Public README example must execute and fail on changed claims or commands."""

import importlib
import runpy
import shutil
import subprocess
from pathlib import Path

import pytest

from quality import readme_example
from quality.readme_example import expected_example, verify_readme_example


def test_native_example_and_isolation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = Path.cwd()
    readme_example.stage_example(source, tmp_path)
    assert (tmp_path / "src/relentless_example/cli.py").is_file()
    assert (tmp_path / "README.md").read_bytes() == (source / "README.md").read_bytes()
    verify_readme_example(source)
    monkeypatch.chdir(source)
    runpy.run_module("quality.readme_example_main", run_name="__main__")
    assert callable(importlib.import_module("quality.readme_example_main").main)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("## Example behavior", "## Other behavior"),
        ("## Example behavior", "## Example behavior\n## Example behavior"),
        ("uv build", "uv publish"),
        ("```sh", "```bash"),
        ("Output is `[[1,8]]`", "Expected result: `[[1,8]]`"),
        (
            "Output is `[[1,8]]` followed by a newline.",
            "Output is `[[1,8]]` followed by a newline.\n"
            "Output is `[[2,8]]` followed by a newline.",
        ),
    ],
)
def test_changed_readme_fails_before_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, before: str, after: str
) -> None:
    source = Path.cwd()
    shutil.copy2(source / "README.md", tmp_path / "README.md")
    original = (tmp_path / "README.md").read_text(encoding="utf-8")
    (tmp_path / "README.md").write_text(
        original.replace(before, after), encoding="utf-8"
    )

    def cannot_run(_root: Path, _args: list[str], _input: str | None) -> None:
        pytest.fail("changed README was executed")

    monkeypatch.setattr(readme_example, "command", cannot_run)
    with pytest.raises(ValueError, match="README example"):
        verify_readme_example(tmp_path)


def test_claimed_output_is_read_from_readme() -> None:
    text = Path("README.md").read_text(encoding="utf-8")
    assert expected_example(text) == "[[1,8]]\n"
    assert expected_example(text.replace("[[1,8]]", "[[2,8]]")) == "[[2,8]]\n"


def test_example_section_stops_at_next_heading() -> None:
    text = "## Example behavior\nExample\n## Other section\nLater\n"
    assert readme_example.example_section(text) == "Example"


@pytest.mark.parametrize(
    ("build", "run", "error"),
    [
        (1, 0, subprocess.CalledProcessError),
        (0, 1, ValueError),
        (0, 0, ValueError),
    ],
)
def test_native_failure_blocks(
    monkeypatch: pytest.MonkeyPatch,
    build: int,
    run: int,
    error: type[Exception],
) -> None:
    calls = 0

    def fail(
        _root: Path, _args: list[str], _input: str | None
    ) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        code = build if calls == 1 else run
        output = "wrong\n" if calls == 2 else ""
        return subprocess.CompletedProcess(_args, code, output, "native error")

    monkeypatch.setattr(readme_example, "command", fail)
    with pytest.raises(error):
        verify_readme_example(Path.cwd())
    assert calls == (1 if build else 2)


def test_missing_native_tool_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(_root: Path, _args: list[str], _input: str | None) -> None:
        raise FileNotFoundError("mise")

    monkeypatch.setattr(readme_example, "command", missing)
    with pytest.raises(FileNotFoundError, match="mise"):
        verify_readme_example(Path.cwd())


def test_positive_run_failure_blocks_even_with_expected_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failed(
        _root: Path, args: list[str], _input: str | None
    ) -> subprocess.CompletedProcess[str]:
        if args == readme_example.BUILD:
            return subprocess.CompletedProcess(args, 0, "", "")
        return subprocess.CompletedProcess(args, 1, "[[1,8]]\n", "")

    monkeypatch.setattr(readme_example, "command", failed)
    with pytest.raises(ValueError, match="exit status"):
        verify_readme_example(Path.cwd())


def test_negative_build_exit_blocks_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def stopped(
        _root: Path, args: list[str], _input: str | None
    ) -> subprocess.CompletedProcess[str]:
        assert args == readme_example.BUILD
        return subprocess.CompletedProcess(args, -9, "", "signal")

    monkeypatch.setattr(readme_example, "command", stopped)
    with pytest.raises(subprocess.CalledProcessError):
        verify_readme_example(Path.cwd())


def test_negative_run_exit_blocks_even_with_expected_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def stopped(
        _root: Path, args: list[str], _input: str | None
    ) -> subprocess.CompletedProcess[str]:
        code = 0 if args == readme_example.BUILD else -9
        return subprocess.CompletedProcess(args, code, "[[1,8]]\n", "signal")

    monkeypatch.setattr(readme_example, "command", stopped)
    with pytest.raises(ValueError, match="exit status"):
        verify_readme_example(Path.cwd())


def test_lexically_smaller_wrong_output_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def output(
        _root: Path, args: list[str], _input: str | None
    ) -> subprocess.CompletedProcess[str]:
        text = "" if args == readme_example.BUILD else "A\n"
        return subprocess.CompletedProcess(args, 0, text, "")

    monkeypatch.setattr(readme_example, "command", output)
    with pytest.raises(ValueError, match="output differs"):
        verify_readme_example(Path.cwd())


def test_documented_command_has_bounded_native_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def native(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert args == (readme_example.RUN,)
        assert kwargs["cwd"] == tmp_path
        assert kwargs["input"] == readme_example.INPUT
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert kwargs["timeout"] == 120
        assert "shell" not in kwargs
        return subprocess.CompletedProcess(readme_example.RUN, 0, "[[1,8]]\n", "")

    monkeypatch.setattr(subprocess, "run", native)
    result = readme_example.command(tmp_path, readme_example.RUN, readme_example.INPUT)
    assert result.returncode == 0
