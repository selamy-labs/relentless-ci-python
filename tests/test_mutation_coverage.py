"""Coverage maps record function-body statements and leave everything else unmapped."""

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from coverage import CoverageData
from hypothesis import given
from hypothesis import strategies as st

from quality import mutation_coverage
from quality.mutation_coverage import (
    coverage_map,
    file_lines,
    function_index,
    function_lines,
    statement_spans,
    subprocess_settings,
)

SOURCE = '''"""Module."""

LIMIT = 3


@decorated
def check(value=LIMIT):
    if value > 1:
        return (
            value
        )
    return 0


class Box:
    size = 2

    async def open(self):
        return self.size
'''
CHECK = "tests/test_a.py::test_check"


def test_only_function_bodies_are_mappable() -> None:
    assert function_lines(ast.parse(SOURCE)) == [8, 9, 10, 11, 12, 19]


def test_each_line_spans_its_innermost_complete_statement() -> None:
    spans = statement_spans(ast.parse(SOURCE))
    assert spans[3] == range(3, 4)
    assert spans[7] == range(7, 13)
    assert spans[8] == range(8, 12)
    assert spans[9] == spans[11] == range(9, 12)
    assert spans[12] == range(12, 13)
    assert spans[15] == range(15, 20)
    assert spans[16] == range(16, 17)
    assert 6 not in spans
    assert spans[19] == range(19, 20)


@pytest.mark.parametrize(
    "context,expected",
    [
        (f"{CHECK}|run", CHECK),
        (f"{CHECK}[1-a|b]|setup", CHECK),
        ("tests/test_a.py::Kind::test_x[0]|teardown", "tests/test_a.py::Kind::test_x"),
        ("tests/test_a.py::test_y|z|run", "tests/test_a.py::test_y|z"),
    ],
)
def test_contexts_collapse_to_test_functions(context: str, expected: str) -> None:
    tests = {"tests/test_a.py::test_first": 0}
    assert function_index(tests, context) == 1
    assert function_index(tests, context) == 1
    assert tests == {"tests/test_a.py::test_first": 0, expected: 1}


def test_statement_lines_union_tests_and_skip_import_or_unrun_code() -> None:
    contexts = {
        8: [f"{CHECK}[1]|run", f"{CHECK}[2]|run"],
        9: ["tests/test_b.py::test_large|run"],
        12: ["tests/test_c.py::test_zero|run", ""],
        19: ["tests/test_b.py::test_large|setup"],
    }
    tests: dict[str, int] = {}
    lines = file_lines(SOURCE, contexts, tests)
    assert tests == {
        CHECK: tests[CHECK],
        "tests/test_b.py::test_large": tests["tests/test_b.py::test_large"],
    }
    both = sorted(tests.values())
    large = [tests["tests/test_b.py::test_large"]]
    assert lines == {
        "8": both,
        "9": large,
        "10": large,
        "11": large,
        "19": large,
    }


def test_map_keeps_every_source_and_resolves_measured_paths(tmp_path: Path) -> None:
    (tmp_path / "src/pkg").mkdir(parents=True)
    (tmp_path / "quality").mkdir()
    (tmp_path / "src/pkg/item.py").write_text("def f():\n    return 1\n")
    (tmp_path / "quality/tool.py").write_text("VALUE = 1\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_x.py").write_text("def test_x():\n    pass\n")
    data = CoverageData(str(tmp_path / "contexts.coverage"))
    data.set_context("tests/test_x.py::test_x|run")
    data.add_lines({str((tmp_path / "src/pkg/item.py").resolve()): [2]})
    value = coverage_map(tmp_path, data)
    data.close()
    assert value == {
        "tests": ["tests/test_x.py::test_x"],
        "sources": {
            "quality/tool.py": "VALUE = 1\n",
            "src/pkg/item.py": "def f():\n    return 1\n",
        },
        "lines": {"quality/tool.py": {}, "src/pkg/item.py": {"2": [0]}},
    }


@pytest.mark.parametrize("preexisting", [False, True])
def test_collect_runs_the_complete_suite_with_test_contexts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, preexisting: bool
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "quality").mkdir()
    (tmp_path / "src/item.py").write_text("def f():\n    return 1\n")
    if preexisting:
        (tmp_path / ".quality-results").mkdir()
    calls: list[tuple[list[str], Path, float, dict[str, str]]] = []

    def owned(
        command: list[str], root: Path, timeout: float, env: dict[str, str]
    ) -> None:
        calls.append((command, root, timeout, env))
        data = CoverageData(env["COVERAGE_FILE"])
        data.set_context("tests/test_x.py::test_x|run")
        data.add_lines({str((root / "src/item.py").resolve()): [2]})
        data.write()
        data.close()

    monkeypatch.setattr(mutation_coverage, "run_owned", owned)
    inherited = {"KEEP": "1"}
    encoded = mutation_coverage.collect(tmp_path, 9, inherited)
    assert inherited == {"KEEP": "1"}
    contexts = tmp_path / ".quality-results/mutation-contexts.coverage"
    settings = tmp_path / ".quality-results/mutation-subprocess.toml"
    assert settings.read_text() == subprocess_settings(tmp_path, contexts)
    assert calls == [
        (
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--color=no",
                "-p",
                "quality.mutation_context",
                "--cov",
                "--cov-context=test",
                "--cov-report=",
                "--cov-fail-under=0",
            ],
            tmp_path,
            9,
            {
                "KEEP": "1",
                "COVERAGE_FILE": str(contexts),
                "MUTATION_COVERAGE_RC": str(settings),
            },
        )
    ]
    path = tmp_path / ".quality-results/mutation-coverage.json"
    assert path.read_bytes() == encoded
    assert json.loads(encoded)["lines"] == {"src/item.py": {"2": [0]}}
    assert encoded.decode().startswith('{"lines"')


names = st.from_regex(r"tests/test_[a-z]{1,3}\.py::test_[a-z]{1,3}", fullmatch=True)


@given(st.lists(names, min_size=1), st.lists(st.sampled_from(["run", "setup"])))
def test_function_indices_are_stable_and_dense(
    functions: list[str], phases: list[str]
) -> None:
    tests: dict[str, int] = {}
    for number, function in enumerate(functions):
        phase = phases[number % len(phases)] if phases else "run"
        function_index(tests, f"{function}[{number}]|{phase}")
    assert list(tests) == list(dict.fromkeys(functions))
    assert sorted(tests.values()) == list(range(len(tests)))


def test_subprocess_settings_label_child_data_with_the_inherited_test(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src/child.py").write_text("def run():\n    return 1\n\nrun()\n")
    contexts = tmp_path / "contexts.coverage"
    settings = tmp_path / "settings.toml"
    settings.write_text(subprocess_settings(tmp_path, contexts))
    env = {
        **os.environ,
        "COVERAGE_PROCESS_START": str(settings),
        "MUTATION_TEST_CONTEXT": "tests/test_a.py::test_child|subprocess",
    }
    env.pop("COVERAGE_FILE", None)
    subprocess.run(
        [sys.executable, str(tmp_path / "src/child.py")], env=env, check=True
    )
    (part,) = tmp_path.glob("contexts.coverage.*")
    data = CoverageData(str(part))
    data.read()
    measured = data.contexts_by_lineno(str((tmp_path / "src/child.py").resolve()))
    data.close()
    assert data.has_arcs()
    assert measured[2] == ["tests/test_a.py::test_child|subprocess"]
