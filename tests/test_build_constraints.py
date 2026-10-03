"""Missing, empty and stale build constraints cannot pass a clean export check."""

import runpy
from pathlib import Path

import pytest

from quality import build_constraints


def files(root: Path, expected: bytes, actual: bytes) -> None:
    (root / "quality").mkdir()
    (root / ".quality-results").mkdir()
    (root / "quality/build-constraints.txt").write_bytes(expected)
    (root / ".quality-results/build-constraints.txt").write_bytes(actual)


def test_fresh_native_bytes_match_without_coercion(tmp_path: Path) -> None:
    files(tmp_path, b"b\n", b"b\n")
    build_constraints.verify_build_constraints(tmp_path)


@pytest.mark.parametrize("expected,actual", [(b"b\n", b"b\r\n"), (b"b\r\n", b"b\n")])
def test_fresh_export_allows_windows_line_endings(
    tmp_path: Path, expected: bytes, actual: bytes
) -> None:
    files(tmp_path, expected, actual)
    build_constraints.verify_build_constraints(tmp_path)


@pytest.mark.parametrize("actual", [b"a\n", b"c\n", b"b", b""])
def test_stale_or_altered_export_fails(tmp_path: Path, actual: bytes) -> None:
    files(tmp_path, b"b\n", actual)
    with pytest.raises(ValueError, match="differ from the fresh locked export"):
        build_constraints.verify_build_constraints(tmp_path)


def test_empty_exports_fail(tmp_path: Path) -> None:
    files(tmp_path, b"", b"")
    with pytest.raises(ValueError, match="differ from the fresh locked export"):
        build_constraints.verify_build_constraints(tmp_path)


@pytest.mark.parametrize("missing", ["quality", ".quality-results"])
def test_missing_files_fail(tmp_path: Path, missing: str) -> None:
    files(tmp_path, b"b\n", b"b\n")
    (tmp_path / missing / "build-constraints.txt").unlink()
    with pytest.raises(FileNotFoundError):
        build_constraints.verify_build_constraints(tmp_path)


def test_entry_uses_current_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    received: list[Path] = []
    monkeypatch.setattr(build_constraints, "verify_build_constraints", received.append)
    runpy.run_module("quality.build_constraints_main", run_name="__main__")
    assert received == [Path.cwd()]
