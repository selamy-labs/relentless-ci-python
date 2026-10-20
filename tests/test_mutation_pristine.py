"""A selected command earns credit only after it passes on pristine sources."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from quality.mutation_trial import selected
from quality.trial_launcher import prepare_launcher
from tests.test_mutation_selection import SOURCE, TESTS, workspace

MUTANT = SOURCE.replace("2", "3")
CACHE = ".quality-results/mutation-pristine.json"


def narrowed(*tests: str) -> list[str]:
    return [sys.executable, "-m", "pytest", "-x", "-q", "--color=no", *tests]


def key(sources: dict[str, str], *tests: str) -> str:
    encoded = json.dumps([sources, narrowed(*tests)]).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


SOURCES = {"src/item.py": SOURCE, "src/other.py": "value = 1\n"}


class Pristine:
    """Record each run and the module text that pytest would have imported."""

    def __init__(self, status: int = 0, stderr: str = "") -> None:
        self.status = status
        self.stderr = stderr
        self.seen: list[tuple[list[str], str]] = []

    def __call__(
        self, command: list[str], **_options: bool
    ) -> subprocess.CompletedProcess[str]:
        text = Path("src/item.py").read_text(encoding="utf-8")
        self.seen.append((command, text))
        return subprocess.CompletedProcess(command, self.status, "", self.stderr)


@pytest.fixture
def mutant(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    workspace(tmp_path, {"2": [2, 0], "3": [1], "4": [0]})
    (tmp_path / "src/item.py").write_text(MUTANT, encoding="utf-8")
    return tmp_path


def test_passing_pristine_selection_is_cached_by_sources_and_command(
    mutant: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = Pristine()
    monkeypatch.setattr(subprocess, "run", run)
    assert selected() == [TESTS[1]]
    assert selected() == [TESTS[1]]
    assert run.seen == [(narrowed(TESTS[1]), SOURCE)]
    assert (mutant / "src/item.py").read_text(encoding="utf-8") == MUTANT
    cache = json.loads((mutant / CACHE).read_text(encoding="utf-8"))
    assert cache == {key(SOURCES, TESTS[1]): True}


@pytest.mark.parametrize(
    "status,stderr", [(1, ""), (2, ""), (5, ""), (-9, ""), (0, "diagnostic\n")]
)
def test_failing_pristine_selection_falls_back_to_the_full_suite(
    mutant: Path, monkeypatch: pytest.MonkeyPatch, status: int, stderr: str
) -> None:
    run = Pristine(status, stderr)
    monkeypatch.setattr(subprocess, "run", run)
    assert selected() == []
    assert selected() == []
    assert run.seen == [(narrowed(TESTS[1]), SOURCE)]
    cache = json.loads((mutant / CACHE).read_text(encoding="utf-8"))
    assert cache == {key(SOURCES, TESTS[1]): False}


def test_each_selection_and_pristine_source_has_its_own_entry(
    mutant: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = Pristine()
    monkeypatch.setattr(subprocess, "run", run)
    (mutant / CACHE).write_text(json.dumps({"other": False}), encoding="utf-8")
    assert selected() == [TESTS[1]]
    (mutant / "src/item.py").write_text(SOURCE.replace("1", "2"), encoding="utf-8")
    assert selected() == [TESTS[0], TESTS[2]]
    cache = json.loads((mutant / CACHE).read_text(encoding="utf-8"))
    assert cache == {
        "other": False,
        key(SOURCES, TESTS[1]): True,
        key(SOURCES, TESTS[0], TESTS[2]): True,
    }
    assert key({**SOURCES, "src/other.py": ""}, TESTS[1]) not in cache


@pytest.mark.parametrize("stored", ["{", "[", ""])
def test_unreadable_cache_is_reestablished(
    mutant: Path, monkeypatch: pytest.MonkeyPatch, stored: str
) -> None:
    (mutant / CACHE).write_text(stored, encoding="utf-8")
    run = Pristine()
    monkeypatch.setattr(subprocess, "run", run)
    assert selected() == [TESTS[1]]
    assert len(run.seen) == 1


def test_unlaunchable_pristine_selection_restores_the_mutant_and_runs_all(
    mutant: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable(command: list[str], **_options: bool) -> None:
        assert Path("src/item.py").read_text(encoding="utf-8") == SOURCE
        raise FileNotFoundError(command[0])

    monkeypatch.setattr(subprocess, "run", unavailable)
    assert selected() == []
    assert (mutant / "src/item.py").read_text(encoding="utf-8") == MUTANT


def test_interrupted_pristine_selection_still_restores_the_mutant(
    mutant: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupted(*_args: object, **_kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(subprocess, "run", interrupted)
    with pytest.raises(KeyboardInterrupt):
        selected()
    assert (mutant / "src/item.py").read_text(encoding="utf-8") == MUTANT
    assert not (mutant / CACHE).exists()


WITNESS = "def answer():\n    return 1 + 0\n\n\ndef other():\n    return 3 - 1\n"
SESSION = """from item import answer, other


def test_session(request):
    assert answer() == 1
    assert len(request.session.items) == 2


def test_other():
    assert other() == 2
"""


def native_workspace(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(root)
    monkeypatch.setenv("PYTHONPATH", str(root / "src"))
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    for name in ("src", "tests", "quality", ".quality-results"):
        (root / name).mkdir()
    (root / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n")
    (root / "src/item.py").write_text(WITNESS, encoding="utf-8")
    (root / "tests/test_item.py").write_text(SESSION, encoding="utf-8")
    trial = Path(__file__).resolve().parents[1] / "quality/mutation_trial.py"
    (root / "quality/mutation_trial.py").write_bytes(trial.read_bytes())
    prepare_launcher(root)
    data = {
        "tests": ["tests/test_item.py::test_session", "tests/test_item.py::test_other"],
        "sources": {"src/item.py": WITNESS},
        "lines": {"src/item.py": {"2": [0], "6": [1]}},
    }
    (root / ".quality-results/mutation-coverage.json").write_text(json.dumps(data))


def subset_status() -> int:
    """The coverage selection alone fails on pristine and mutant code alike."""
    command = narrowed("tests/test_item.py::test_session")
    return subprocess.run(command, capture_output=True, check=False).returncode


def native_trial(operator: str) -> tuple[object, dict[str, object]]:
    """The pinned Cosmic Ray worker mutates, runs the launcher and restores."""
    trial = f"{sys.executable} .quality-results/mutation-trial.py"
    worker = str(Path(sys.executable).with_name("cosmic-ray"))
    arguments = ["mutate-and-test", "src/item.py", f"core/{operator}", "0", trial]
    completed = subprocess.run(
        [worker, *arguments], capture_output=True, text=True, check=True
    )
    result: dict[str, object] = json.loads(completed.stdout)
    assert result["worker_outcome"] == "normal"
    assert Path("src/item.py").read_text(encoding="utf-8") == WITNESS
    record: dict[str, object] = json.loads(str(result["output"]))
    return result["test_outcome"], record


def test_session_dependent_subset_cannot_kill_an_equivalent_mutant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    native_workspace(tmp_path, monkeypatch)
    item = tmp_path / "src/item.py"
    item.write_text(WITNESS.replace("1 + 0", "1 - 0"), encoding="utf-8")
    assert subset_status() == 1
    item.write_text(WITNESS, encoding="utf-8")
    assert subset_status() == 1
    outcome, record = native_trial("ReplaceBinaryOperator_Add_Sub")
    assert outcome == "survived"
    assert record["returncode"] == 0
    assert "2 passed" in str(record["stdout"])


def test_pristine_validated_subset_still_kills_a_real_mutant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    native_workspace(tmp_path, monkeypatch)
    outcome, record = native_trial("ReplaceBinaryOperator_Sub_Add")
    assert outcome == "killed"
    assert record["returncode"] == 1
    assert "FAILED tests/test_item.py::test_other" in str(record["stdout"])
    assert "passed" not in str(record["stdout"])
    cache = json.loads((tmp_path / CACHE).read_text(encoding="utf-8"))
    assert list(cache.values()) == [True]
