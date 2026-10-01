"""Exercise native repository hygiene with real indexed and disk defects."""

import os
import subprocess
from pathlib import Path

import pytest

import quality.repository_hygiene as hygiene
from quality.repository_hygiene import (
    disk_files,
    git_paths,
    verify_repository,
    verify_text,
    verify_text_kind,
)


def repository(root: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "README.md").write_text("Clean public documentation.\n")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
    return root


def test_clean_index_and_untracked_text(tmp_path: Path) -> None:
    root = repository(tmp_path)
    (root / "notes.md").write_text("Ignored or untracked text is still read.\n")
    assert git_paths(root) == ["README.md"]
    assert sorted(disk_files(root, root)) == ["README.md", "notes.md"]
    verify_repository(root)


@pytest.mark.parametrize("data", [b"", b"README.md", b"README.md\0extra"])
def test_missing_or_incomplete_git_inventory_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, data: bytes
) -> None:
    def output(_: list[str], *, cwd: Path) -> bytes:
        return data

    monkeypatch.setattr(subprocess, "check_output", output)
    with pytest.raises(ValueError, match="inventory"):
        git_paths(tmp_path)


def test_generated_roots_and_bytecode_caches_are_narrow(tmp_path: Path) -> None:
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "binary.so").write_bytes(b"\0")
    (tmp_path / ".coverage").write_bytes(b"\0")
    (tmp_path / "src" / "__pycache__").mkdir(parents=True)
    (tmp_path / "src" / "__pycache__" / "module.pyc").write_bytes(b"\0")
    (tmp_path / "src" / "module.py").write_text("value = 1\n")
    assert disk_files(tmp_path, tmp_path) == ["src/module.py"]


def test_authored_symlink_and_fifo_fail(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("okay")
    (tmp_path / "link.md").symlink_to("README.md")
    with pytest.raises(ValueError, match="symlink"):
        disk_files(tmp_path, tmp_path)
    (tmp_path / "link.md").unlink()
    os.mkfifo(tmp_path / "channel")
    with pytest.raises(ValueError, match="file kind"):
        disk_files(tmp_path, tmp_path)


@pytest.mark.parametrize("name", ["image.png", "script.sh", "README"])
def test_unknown_authored_file_types_fail(name: str) -> None:
    with pytest.raises(ValueError, match="unsupported authored text type"):
        verify_text_kind(name)


@pytest.mark.parametrize(
    "name", ["src/module.py", "README.md", "LICENSE", ".github/CODEOWNERS"]
)
def test_enrolled_text_types_pass(name: str) -> None:
    verify_text_kind(name)


@pytest.mark.parametrize(
    "marker", ["<<<<<<< HEAD", "=======", ">>>>>>> branch", "||||||| ancestor"]
)
def test_conflict_markers_fail_whole_repository(tmp_path: Path, marker: str) -> None:
    root = repository(tmp_path)
    (root / "README.md").write_text("ordinary text\n" + marker + "\n")
    with pytest.raises(ValueError, match="conflict markers"):
        verify_repository(root)


def test_nonmarkers_and_crlf_are_text() -> None:
    verify_text(b"A < marker\r\n==== heading\r\ncomplete\n")
    with pytest.raises(ValueError, match="conflict markers"):
        verify_text(b"<<<<<<< HEAD\r\n")


def test_binary_and_invalid_utf8_fail(tmp_path: Path) -> None:
    root = repository(tmp_path)
    (root / "README.md").write_bytes(b"prefix\0suffix")
    with pytest.raises(ValueError, match="binary data"):
        verify_repository(root)
    (root / "README.md").write_bytes(b"\xff")
    with pytest.raises(UnicodeDecodeError):
        verify_repository(root)


def test_ignored_conflict_and_missing_indexed_file_fail(tmp_path: Path) -> None:
    root = repository(tmp_path)
    (root / "notes.md").write_text("<<<<<<< HEAD\n")
    with pytest.raises(ValueError, match="conflict markers"):
        verify_repository(root)
    (root / "notes.md").unlink()
    (root / "README.md").unlink()
    with pytest.raises(FileNotFoundError):
        verify_repository(root)


def test_case_colliding_disk_paths_fail(tmp_path: Path) -> None:
    root = repository(tmp_path)
    (root / "readme.md").write_text("other spelling")
    with pytest.raises(ValueError, match="collide"):
        verify_repository(root)


def test_duplicate_native_index_cannot_be_hidden_by_disk_union(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repository(tmp_path)

    def duplicate_paths(_: Path) -> list[str]:
        return ["README.md", "README.md"]

    monkeypatch.setattr(hygiene, "git_paths", duplicate_paths)
    with pytest.raises(ValueError, match="duplicated"):
        verify_repository(root)
