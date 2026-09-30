"""Source completeness and suppression probes for duplication scanning."""

from pathlib import Path

import pytest

from quality.duplication_inputs import duplication_inputs, stage_inputs, verify_inputs


def write(root: Path, name: str, content: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_reads_nested_ignored_and_never_imported_source(tmp_path: Path) -> None:
    write(tmp_path, ".gitignore", "*.py\n")
    first = write(tmp_path, "src/sample/module.py", "value = 1\n")
    second = write(tmp_path, "tests/nested/test_unused.py", "assert True\n")
    inputs = duplication_inputs(tmp_path)
    assert inputs == {
        "src/sample/module.py": first.read_bytes(),
        "tests/nested/test_unused.py": second.read_bytes(),
    }
    staged = stage_inputs(inputs, tmp_path.with_name(tmp_path.name + "-stage"))
    assert [path.read_bytes() for path in staged] == list(inputs.values())
    verify_inputs(inputs, duplication_inputs(tmp_path))


@pytest.mark.parametrize(
    "marker", ["jscpd" + ":ignore-start", "jscpd " + ": ignore-end"]
)
def test_rejects_inline_suppression(tmp_path: Path, marker: str) -> None:
    write(tmp_path, "quality/check.py", f"# {marker}\n")
    with pytest.raises(ValueError, match="suppression"):
        duplication_inputs(tmp_path)


def test_rejects_invalid_utf8(tmp_path: Path) -> None:
    path = write(tmp_path, "quality/check.py", "pass\n")
    path.write_bytes(b"\xff")
    with pytest.raises(UnicodeDecodeError):
        duplication_inputs(tmp_path)


@pytest.mark.parametrize("change", ["edit", "remove", "insert"])
def test_rejects_changed_input_inventory(tmp_path: Path, change: str) -> None:
    path = write(tmp_path, "quality/check.py", "pass\n")
    before = duplication_inputs(tmp_path)
    if change == "edit":
        path.write_text("raise RuntimeError\n")
    elif change == "remove":
        path.unlink()
    else:
        write(tmp_path, "tests/test_new.py", "pass\n")
    if change == "remove":
        after: dict[str, bytes] = {}
    else:
        after = duplication_inputs(tmp_path)
    with pytest.raises(ValueError, match="changed"):
        verify_inputs(before, after)
