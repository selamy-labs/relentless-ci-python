"""Native path portability and Python naming probes."""

import subprocess
from pathlib import Path

import pytest

from quality.portable_paths import verify_path_names
from quality.source_scope import verify_sources, verify_tracked


def write(root: Path, name: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("pass\n", encoding="utf-8")
    return path


def git(root: Path, *arguments: str) -> None:
    subprocess.run(["git", *arguments], cwd=root, check=True, capture_output=True)


def test_accepts_portable_shared_directories_and_source_names(tmp_path: Path) -> None:
    paths = [
        "src/sample/_private.py",
        "src/sample/__init__.py",
        "src/sample/__main__.py",
        "tests/test_sample.py",
    ]
    for name in paths:
        write(tmp_path, name)
    assert len(verify_sources(tmp_path)) == 4
    verify_path_names([*paths, "README.md", ".github/workflows/ci.yml"])


@pytest.mark.parametrize(
    "names",
    [
        [],
        ["src/a.py", "src/a.py"],
        ["src/A.py", "src/a.py"],
        ["src/Nested/a.py", "src/nested/b.py"],
        ["docs/é.md", "docs/e\u0301.md"],
        ["src/straße.py", "src/STRASSE.py"],
        ["src/File", "src/file/child.py"],
    ],
)
def test_rejects_duplicate_or_colliding_paths(names: list[str]) -> None:
    with pytest.raises(ValueError, match="duplicated|collide"):
        verify_path_names(names)


@pytest.mark.parametrize(
    "name",
    [
        "/absolute.py",
        "src//file.py",
        "src/./file.py",
        "src/../file.py",
        "src/a<bad.py",
        "src/a\\bad.py",
        "src/a\x00bad.py",
        "src/a\u0085bad.py",
        "src/file.py.",
        "src/file.py ",
        "src/file.py\u00a0",
        "src/CON/file.py",
        "src/lpt³.py",
    ],
)
def test_rejects_nonportable_path_components(name: str) -> None:
    with pytest.raises(ValueError, match="path"):
        verify_path_names([name])


@pytest.mark.parametrize("name", ["src/BadName.py", "src/Bad_Package/file.py"])
def test_rejects_non_snake_case_authored_source(tmp_path: Path, name: str) -> None:
    write(tmp_path, name)
    with pytest.raises(ValueError, match="snake_case"):
        verify_sources(tmp_path)


def test_native_git_inventory_rejects_case_collision(tmp_path: Path) -> None:
    git(tmp_path, "init", "--quiet")
    write(tmp_path, "src/A.py")
    write(tmp_path, "src/a.py")
    git(tmp_path, "add", "src/A.py", "src/a.py")
    with pytest.raises(ValueError, match="collide"):
        verify_tracked(tmp_path)


def test_native_git_inventory_accepts_clean_names(tmp_path: Path) -> None:
    git(tmp_path, "init", "--quiet")
    write(tmp_path, "src/sample.py")
    git(tmp_path, "add", "src/sample.py")
    verify_tracked(tmp_path)


@pytest.mark.parametrize("output", [b"", b"src/sample.py"])
def test_incomplete_git_inventory_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, output: bytes
) -> None:
    def incomplete(*_args: object, **_kwargs: object) -> bytes:
        return output

    monkeypatch.setattr(subprocess, "check_output", incomplete)
    with pytest.raises(ValueError, match="incomplete"):
        verify_tracked(tmp_path)


def test_invalid_utf8_git_inventory_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def invalid(*_args: object, **_kwargs: object) -> bytes:
        return b"\xff\0"

    monkeypatch.setattr(subprocess, "check_output", invalid)
    with pytest.raises(UnicodeDecodeError):
        verify_tracked(tmp_path)
