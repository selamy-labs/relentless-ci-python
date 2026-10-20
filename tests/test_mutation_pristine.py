"""Only coordinator-established pristine selections earn credit; trials never write."""

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web

from quality import mutation_pristine
from quality import mutation_worker as worker
from quality.mutation_inputs import CONFIGURATION, INPUTS
from quality.mutation_pristine import establish, mutator, planned
from quality.mutation_trial import selected
from quality.trial_launcher import prepare_launcher
from tests.test_mutation_selection import SOURCE, TESTS, mapped_workspace
from tests.test_mutation_transport import run_handler

MUTANT = SOURCE.replace("2", "3")
PRISTINE = ".quality-results/mutation-pristine.json"
SOURCES = {"src/item.py": SOURCE, "src/other.py": "value = 1\n"}


def narrowed(*tests: str) -> list[str]:
    return [sys.executable, "-m", "pytest", "-x", "-q", "--color=no", *tests]


def forged_key(sources: dict[str, str], *tests: str) -> str:
    """The cache key the previous trial trusted and let any trial rewrite."""
    encoded = json.dumps([sources, narrowed(*tests)]).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@pytest.fixture
def mutant(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    mapped = mapped_workspace(tmp_path, monkeypatch)
    (mapped / "src/item.py").write_text(MUTANT, encoding="utf-8")
    (mapped / PRISTINE).unlink()
    return mapped


def test_established_selection_is_used_without_any_trial_write(mutant: Path) -> None:
    (mutant / PRISTINE).write_text(json.dumps([[TESTS[1]]]), encoding="utf-8")
    before = (mutant / PRISTINE).read_bytes()
    assert selected() == [TESTS[1]]
    assert (mutant / PRISTINE).read_bytes() == before
    assert sorted(path.name for path in (mutant / ".quality-results").iterdir()) == [
        "mutation-coverage.json",
        "mutation-pristine.json",
    ]


@pytest.mark.parametrize(
    "stored",
    [
        "[]",
        json.dumps([[TESTS[0]], [TESTS[1], TESTS[2]]]),
        json.dumps({forged_key(SOURCES, TESTS[1]): True}),
        json.dumps(TESTS[1]),
        "{",
        "",
        None,
    ],
)
def test_unestablished_or_unreadable_selection_runs_the_full_suite(
    mutant: Path, stored: str | None
) -> None:
    if stored is not None:
        (mutant / PRISTINE).write_text(stored, encoding="utf-8")
    assert selected() == []
    assert not (mutant / PRISTINE).exists() or stored is not None


WITNESS = "def answer():\n    return 1 + 0\n\n\ndef other():\n    return 3 - 1\n"
SESSION = """from item import answer, other


def test_session(request):
    assert answer() == 1
    assert len(request.session.items) == 2


def test_other():
    assert other() == 2
"""
SESSION_TEST = "tests/test_item.py::test_session"
OTHER_TEST = "tests/test_item.py::test_other"
CONFIG = """[cosmic-ray]
module-path = "src/item.py"
timeout = 60.0
excluded-modules = []
test-command = "python .quality-results/mutation-trial.py"

[cosmic-ray.distributor]
name = "local"
"""


def native_workspace(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A complete enrolled copy: real verifier package, witness source and tests."""
    monkeypatch.chdir(root)
    monkeypatch.setenv("PYTHONPATH", str(root / "src"))
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    for name in (*INPUTS, ".quality-results"):
        (root / name).mkdir(exist_ok=True)
    for name in CONFIGURATION:
        (root / name).write_text("", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
    )
    (root / "cosmic-ray.toml").write_text(CONFIG, encoding="utf-8")
    (root / "src/item.py").write_text(WITNESS, encoding="utf-8")
    (root / "tests/test_item.py").write_text(SESSION, encoding="utf-8")
    shutil.rmtree(root / "quality")
    shutil.copytree(
        Path(__file__).resolve().parents[1] / "quality",
        root / "quality",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    prepare_launcher(root)
    data = {
        "tests": [SESSION_TEST, OTHER_TEST],
        "sources": {"src/item.py": WITNESS},
        "lines": {"src/item.py": {"2": [0], "6": [1]}},
    }
    (root / ".quality-results/mutation-coverage.json").write_text(json.dumps(data))
    cosmic = str(Path(sys.executable).with_name("cosmic-ray"))
    subprocess.run([cosmic, "init", "cosmic-ray.toml", "mutation.sqlite"], check=True)


def subset_status() -> int:
    """The coverage selection alone fails on pristine and mutant code alike."""
    command = narrowed(SESSION_TEST)
    return subprocess.run(command, capture_output=True, check=False).returncode


def native_trial(operator: str) -> tuple[object, dict[str, object]]:
    """The pinned Cosmic Ray worker mutates, runs the launcher and restores."""
    trial = f"{sys.executable} .quality-results/mutation-trial.py"
    cosmic = str(Path(sys.executable).with_name("cosmic-ray"))
    arguments = ["mutate-and-test", "src/item.py", f"core/{operator}", "0", trial]
    completed = subprocess.run(
        [cosmic, *arguments], capture_output=True, text=True, check=True
    )
    result: dict[str, object] = json.loads(completed.stdout)
    assert result["worker_outcome"] == "normal"
    assert Path("src/item.py").read_text(encoding="utf-8") == WITNESS
    record: dict[str, object] = json.loads(str(result["output"]))
    return result["test_outcome"], record


def established(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Runs inside each test body so a broken coordinator is a test failure."""
    native_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(mutation_pristine, "worker_count", lambda: 3)
    assert planned(tmp_path) == [[OTHER_TEST], [SESSION_TEST]]
    encoded = establish(tmp_path, 600, dict(os.environ))
    assert json.loads(encoded) == [[OTHER_TEST]]
    assert (tmp_path / PRISTINE).read_bytes() == encoded
    return tmp_path


def test_session_dependent_subset_cannot_kill_an_equivalent_mutant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = established(tmp_path, monkeypatch)
    item = root / "src/item.py"
    item.write_text(WITNESS.replace("1 + 0", "1 - 0"), encoding="utf-8")
    assert subset_status() == 1
    item.write_text(WITNESS, encoding="utf-8")
    assert subset_status() == 1
    outcome, record = native_trial("ReplaceBinaryOperator_Add_Sub")
    assert outcome == "survived"
    assert record["returncode"] == 0
    assert "2 passed" in str(record["stdout"])


def test_forged_trial_cache_entry_cannot_restore_the_false_kill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = established(tmp_path, monkeypatch)
    """The exploit wrote a cached pristine success for the failing selection."""
    forged = {forged_key({"src/item.py": WITNESS}, SESSION_TEST): True}
    (root / PRISTINE).write_text(json.dumps(forged), encoding="utf-8")
    outcome, record = native_trial("ReplaceBinaryOperator_Add_Sub")
    assert outcome == "survived"
    assert "2 passed" in str(record["stdout"])
    assert json.loads((root / PRISTINE).read_text()) == forged


def test_pristine_validated_subset_still_kills_a_real_mutant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = established(tmp_path, monkeypatch)
    before = (root / PRISTINE).read_bytes()
    outcome, record = native_trial("ReplaceBinaryOperator_Sub_Add")
    assert outcome == "killed"
    assert record["returncode"] == 1
    assert f"FAILED {OTHER_TEST}" in str(record["stdout"])
    assert "passed" not in str(record["stdout"])
    assert (root / PRISTINE).read_bytes() == before


def test_worker_rejects_a_trial_that_forges_pristine_credit(tmp_path: Path) -> None:
    """A forged success is caught after its own request and before the next."""
    (tmp_path / "quality").mkdir()
    (tmp_path / "quality/mutation_trial.py").write_bytes(b"native launcher\n")
    (tmp_path / ".quality-results").mkdir()
    (tmp_path / ".quality-results/mutation-coverage.json").write_bytes(b"{}")
    (tmp_path / PRISTINE).write_text(json.dumps([[OTHER_TEST]]), encoding="utf-8")

    async def forging(_request: web.Request) -> web.Response:
        forged = json.dumps([[OTHER_TEST], [SESSION_TEST]])
        (tmp_path / PRISTINE).write_text(forged, encoding="utf-8")
        return web.Response(status=200)

    handler = AsyncMock(side_effect=forging)
    wrapped = worker.journal_handler(tmp_path, handler)
    for _ in range(2):
        request = MagicMock(json=AsyncMock())
        with pytest.raises(ValueError, match="selection inputs changed"):
            asyncio.run(run_handler(wrapped(request)))
        request.json.assert_not_awaited()
    assert handler.await_count == 1
    assert not (tmp_path / ".quality-results/worker-jobs.jsonl").exists()


def test_inapplicable_native_mutation_leaves_the_code_unchanged() -> None:
    mutate = mutator()
    assert mutate("x = 1\n", "core/NumberReplacer", json.dumps("{}"), 0) == "x = 2\n"
    assert mutate("x = 1\n", "core/NumberReplacer", json.dumps("{}"), 9) == "x = 1\n"
