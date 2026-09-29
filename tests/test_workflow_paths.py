"""Workflow discovery must not inherit ignore filters or unsupported file kinds."""

from pathlib import Path

import pytest

from quality.workflows import workflow_paths


def directory(root: Path) -> Path:
    target = root / ".github" / "workflows"
    target.mkdir(parents=True)
    return target


def test_collects_both_yaml_extensions_and_ignored_hidden_files(tmp_path: Path) -> None:
    target = directory(tmp_path)
    (tmp_path / ".gitignore").write_text(".github/\n")
    for name in ("z.yml", ".hidden.yaml", "a.yaml"):
        (target / name).write_text("name: Workflow\n")
    assert workflow_paths(tmp_path) == [
        str((target / name).resolve()) for name in (".hidden.yaml", "a.yaml", "z.yml")
    ]


@pytest.mark.parametrize("present", [False, True])
def test_missing_or_empty_collection_fails(tmp_path: Path, present: bool) -> None:
    if present:
        directory(tmp_path)
    with pytest.raises((ValueError, FileNotFoundError)):
        workflow_paths(tmp_path)


@pytest.mark.parametrize("name", ["nested", "source.py", "workflow.YML", "link.yml"])
def test_rejects_unsupported_entries(tmp_path: Path, name: str) -> None:
    target = directory(tmp_path)
    path = target / name
    if name == "nested":
        path.mkdir()
    elif name == "link.yml":
        original = tmp_path / "original.yml"
        original.write_text("name: Workflow\n")
        path.symlink_to(original)
    else:
        path.write_text("name: Workflow\n")
    with pytest.raises(ValueError, match="regular YAML workflows"):
        workflow_paths(tmp_path)


@pytest.mark.parametrize("parent", [False, True])
def test_rejects_linked_workflow_directories(tmp_path: Path, parent: bool) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    if parent:
        (outside / "workflows").mkdir()
        (tmp_path / ".github").symlink_to(outside, target_is_directory=True)
    else:
        (tmp_path / ".github").mkdir()
        (tmp_path / ".github/workflows").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="cannot be a symlink"):
        workflow_paths(tmp_path)
