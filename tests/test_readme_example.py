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
