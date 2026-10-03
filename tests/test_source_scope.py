"""Physical boundary and scope-bypass probes using actual temporary trees."""

import subprocess
from pathlib import Path

import pytest

from quality.source_scope import GENERATED_ROOTS, verify_sources, verify_tracked


def source(root: Path, name: str, text: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize("ending", ["\n", "\r\n"])
@pytest.mark.parametrize("last_newline", [True, False])
def test_accepts_399_and_rejects_400_physical_lines(
    tmp_path: Path, ending: str, last_newline: bool
) -> None:
    text = ending.join(["# comment", "", *["value = 1"] * 397])
    path = source(tmp_path, "quality/check.py", text + ending * last_newline)
    assert verify_sources(tmp_path) == [path]
    path.write_text(text + ending + "# extra" + ending, encoding="utf-8")
    with pytest.raises(ValueError, match="400 physical lines exceeds 399"):
        verify_sources(tmp_path)


def test_finds_nested_tests_scripts_and_never_imported_code(tmp_path: Path) -> None:
    paths = [
        source(tmp_path, "src/package/unused.py", "unused = 1"),
        source(tmp_path, "tests/nested/example.py", "# a test"),
        source(tmp_path, "quality/script.py", "# a script"),
    ]
    (tmp_path / ".gitignore").write_text("*.py\n")
    assert verify_sources(tmp_path) == sorted(paths)


@pytest.mark.parametrize(
    "name",
    [
        "escape.py",
        "scripts/escape.py",
        "quality/stub.pyi",
        "src/main.pyw",
        "src/UPPER.PY",
    ],
)
def test_rejects_unenrolled_python(tmp_path: Path, name: str) -> None:
    source(tmp_path, name, "# cannot hide from checks")
    with pytest.raises(ValueError, match="outside supported scope"):
        verify_sources(tmp_path)


@pytest.mark.parametrize("generated", sorted(GENERATED_ROOTS))
def test_only_top_level_generated_directories_are_exempt(
    tmp_path: Path, generated: str
) -> None:
    owned = source(tmp_path, "quality/check.py", "pass")
    source(tmp_path, f"{generated}/generated.py", "# generated\n" * 400)
    assert verify_sources(tmp_path) == [owned]
    nested = source(tmp_path, f"quality/{generated}/new.py", "# authored\n" * 400)
    with pytest.raises(ValueError, match="generated directory"):
        verify_sources(tmp_path)
    nested.unlink()


def test_rejects_source_inside_bytecode_cache(tmp_path: Path) -> None:
    source(tmp_path, "quality/__pycache__/hidden.py", "pass")
    with pytest.raises(ValueError, match="cache directory"):
        verify_sources(tmp_path)


@pytest.mark.parametrize("directory", [False, True])
def test_rejects_authored_symlinks(tmp_path: Path, directory: bool) -> None:
    target = tmp_path / "target"
    if directory:
        target.mkdir()
    else:
        target.write_text("pass")
    (tmp_path / "link.py").symlink_to(target, target_is_directory=directory)
    with pytest.raises(ValueError, match="symlinks are unsupported"):
        verify_sources(tmp_path)


def test_empty_discovery_fails(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no authored Python"):
        verify_sources(tmp_path)


def test_invalid_encoding_fails(tmp_path: Path) -> None:
    path = source(tmp_path, "quality/broken.py", "pass")
    path.write_bytes(b"\xff")
    with pytest.raises(UnicodeDecodeError):
        verify_sources(tmp_path)


def git(root: Path, *arguments: str) -> None:
    subprocess.run(["git", *arguments], cwd=root, check=True, capture_output=True)


def test_accepts_untracked_generated_outputs_and_tracked_source(tmp_path: Path) -> None:
    git(tmp_path, "init", "--quiet")
    source(tmp_path, "quality/source.py", "pass")
    source(tmp_path, "dist/output.py", "# generated")
    git(tmp_path, "add", "quality/source.py")
    verify_tracked(tmp_path)


@pytest.mark.parametrize(
    "name",
    ["dist/output.py", ".complexipy_cache/README.md", "quality/__pycache__/hidden.py"],
)
def test_rejects_committed_files_in_generated_exemptions(
    tmp_path: Path, name: str
) -> None:
    git(tmp_path, "init", "--quiet")
    source(tmp_path, name, "# cannot bypass analysis")
    git(tmp_path, "add", "--force", name)
    with pytest.raises(ValueError, match="tracked file in a generated exemption"):
        verify_tracked(tmp_path)


def test_missing_git_repository_is_a_failed_gate(tmp_path: Path) -> None:
    with pytest.raises(subprocess.CalledProcessError):
        verify_tracked(tmp_path)
