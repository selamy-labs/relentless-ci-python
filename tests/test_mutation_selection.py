"""Trial selection narrows only to recorded covering tests and otherwise runs all."""

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from hypothesis import given
from hypothesis import strategies as st

from quality import mutation_trial
from quality.mutation_trial import Coverage, changed_lines, covering, selected
from quality.trial_launcher import require_coverage

SOURCE = "def answer():\n    first = 1\n    second = 2\n    return first + second\n"
TESTS = ["tests/a.py::test_zero", "tests/b.py::test_one", "tests/b.py::Kind::test_two"]


def workspace(root: Path, lines: dict[str, list[int]]) -> None:
    (root / "src").mkdir()
    (root / "src/item.py").write_text(SOURCE, encoding="utf-8")
    (root / "src/other.py").write_text("value = 1\n", encoding="utf-8")
    data: Coverage = {
        "tests": TESTS,
        "sources": {"src/item.py": SOURCE, "src/other.py": "value = 1\n"},
        "lines": {
            "src/item.py": {str(k): v for k, v in lines.items()},
            "src/other.py": {},
        },
    }
    (root / ".quality-results").mkdir()
    (root / ".quality-results/mutation-coverage.json").write_text(json.dumps(data))


def pristine_only(
    command: list[str], **_options: bool
) -> subprocess.CompletedProcess[str]:
    status = int(Path("src/item.py").read_text(encoding="utf-8") != SOURCE)
    return subprocess.CompletedProcess(command, status, "", "")


def forbidden(*_args: object, **_kwargs: object) -> None:
    pytest.fail("a full-suite fallback needs no pristine selection run")


@pytest.fixture
def mapped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(subprocess, "run", pristine_only)
    workspace(tmp_path, {"2": [2, 0], "3": [1], "4": [0]})
    return tmp_path


def test_missing_map_or_unchanged_sources_select_every_test(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert selected() == []
    workspace(tmp_path, {"2": [0]})
    assert selected() == []


def test_one_changed_mapped_line_selects_its_tests_in_inventory_order(
    mapped: Path,
) -> None:
    (mapped / "src/item.py").write_text(SOURCE.replace("1", "2"), encoding="utf-8")
    assert selected() == [TESTS[0], TESTS[2]]


def test_changed_statement_lines_union_every_recorded_test(mapped: Path) -> None:
    changed = SOURCE.replace("1", "0").replace("2", "3")
    (mapped / "src/item.py").write_text(changed, encoding="utf-8")
    assert selected() == TESTS


@pytest.mark.parametrize(
    "replacement",
    [
        ("def answer():", "def answer(extra=1):"),
        ("first + second", "first - second"),
    ],
)
def test_any_unmapped_changed_line_selects_every_test(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, replacement: tuple[str, str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(subprocess, "run", forbidden)
    workspace(tmp_path, {"2": [0], "3": [1]})
    (tmp_path / "src/item.py").write_text(SOURCE.replace(*replacement))
    assert selected() == []


def test_several_changed_sources_select_every_test(mapped: Path) -> None:
    (mapped / "src/item.py").write_text(SOURCE.replace("1", "2"), encoding="utf-8")
    (mapped / "src/other.py").write_text("value = 2\n", encoding="utf-8")
    assert selected() == []


def test_change_without_line_difference_selects_every_test(mapped: Path) -> None:
    (mapped / "src/item.py").write_text(SOURCE.rstrip("\n"), encoding="utf-8")
    assert selected() == []


def test_trial_appends_selected_tests_to_the_unchanged_command(
    mapped: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (mapped / "src/item.py").write_text(SOURCE.replace("2", "3"), encoding="utf-8")
    commands: list[list[str]] = []

    def completed(
        command: list[str], **_options: bool
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return pristine_only(command)

    monkeypatch.setattr(subprocess, "run", completed)
    assert mutation_trial.run_trial() == 1
    narrowed = [sys.executable, "-m", "pytest", "-x", "-q", "--color=no", TESTS[1]]
    assert commands == [narrowed, narrowed]
    capsys.readouterr()


@pytest.mark.parametrize(
    "after,expected",
    [
        ("a\nb\nc\n", []),
        ("a\nB\nc\n", [2]),
        ("A\nb\nC\n", [1, 3]),
        ("a\nB\nC\n", [2, 3]),
        ("a\nc\n", []),
        ("a\nnew\nb\nc\n", []),
        ("new\na\nb\nc\n", []),
        ("a\nb\nc\nnew\n", []),
    ],
)
def test_changed_lines_report_original_line_numbers(
    after: str, expected: list[int]
) -> None:
    assert changed_lines("a\nb\nc\n", after) == expected


lines = st.lists(st.text("abc", min_size=1, max_size=3), min_size=1, max_size=12)


@given(lines, st.data())
def test_single_line_replacement_is_located_exactly(
    original: list[str], data: st.DataObject
) -> None:
    index = data.draw(st.integers(0, len(original) - 1))
    changed = [*original]
    changed[index] = "X" + changed[index]
    assert changed_lines("\n".join(original), "\n".join(changed)) == [index + 1]


@given(
    st.dictionaries(st.integers(1, 6), st.lists(st.integers(0, 2), min_size=1)),
    st.integers(1, 6),
)
def test_selection_is_the_mapped_union_or_the_full_suite(
    mapping: dict[int, list[int]], line: int
) -> None:
    original = [f"line{number}" for number in range(1, 7)]
    changed = [*original]
    changed[line - 1] = "mutated"
    with TemporaryDirectory() as directory:
        name = str(Path(directory) / "item.py")
        Path(name).write_text("\n".join(changed), encoding="utf-8")
        data: Coverage = {
            "tests": TESTS,
            "sources": {name: "\n".join(original)},
            "lines": {name: {str(k): v for k, v in mapping.items()}},
        }
        result = covering(data, name)
    assert result == [TESTS[index] for index in sorted(set(mapping.get(line, [])))]


def test_long_sources_compare_line_counts_by_value() -> None:
    before = "".join(f"line {number}\n" for number in range(300))
    after = before.replace("line 299\n", "changed\n")
    assert changed_lines(before, after) == [300]
    assert changed_lines(before, after + "extra\n") == []


@pytest.mark.parametrize("replacement", [b"{ }", b"{", b"{}{}", b"[]", b"|}"])
def test_any_coverage_map_change_is_rejected(
    tmp_path: Path, replacement: bytes
) -> None:
    path = tmp_path / ".quality-results/mutation-coverage.json"
    path.parent.mkdir()
    path.write_bytes(b"{}")
    require_coverage(tmp_path, b"{}")
    path.write_bytes(replacement)
    with pytest.raises(ValueError, match="coverage map changed"):
        require_coverage(tmp_path, b"{}")
