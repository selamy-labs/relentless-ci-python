"""Map mutable function-body lines to the test functions that execute them."""

import ast
import json
import sys
from pathlib import Path

from coverage import CoverageData

from quality.owned_commands import run_owned
from quality.trial_launcher import coverage_path

SOURCES = ("src", "quality")
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


def collect(root: Path, timeout: float, env: dict[str, str]) -> bytes:
    """Run the complete suite once with per-test contexts before any mutation."""
    output = coverage_path(root)
    output.parent.mkdir(exist_ok=True)
    contexts = output.with_name("mutation-contexts.coverage")
    settings = output.with_name("mutation-subprocess.toml")
    settings.write_text(subprocess_settings(root, contexts), encoding="utf-8")
    measured = env.copy()
    measured["COVERAGE_FILE"] = str(contexts)
    measured["MUTATION_COVERAGE_RC"] = str(settings)
    run_owned(
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
        root,
        timeout,
        measured,
    )
    data = CoverageData(str(contexts))
    data.read()
    try:
        value = coverage_map(root, data)
    finally:
        data.close()
    encoded = json.dumps(value, sort_keys=True).encode("utf-8")
    output.write_bytes(encoded)
    return encoded


def subprocess_settings(root: Path, contexts: Path) -> str:
    """Children append parallel data labelled by the inherited test context."""
    sources = json.dumps([str(root / name) for name in SOURCES])
    return (
        "[run]\nbranch = true\nparallel = true\n"
        f"source = {sources}\ndata_file = {json.dumps(str(contexts))}\n"
        'context = "${MUTATION_TEST_CONTEXT}"\n'
    )


def coverage_map(root: Path, data: CoverageData) -> dict[str, object]:
    """Every enrolled source keeps its pristine text, even when nothing maps."""
    tests: dict[str, int] = {}
    sources: dict[str, str] = {}
    lines: dict[str, dict[str, list[int]]] = {}
    for path in sorted(
        path for name in SOURCES for path in (root / name).rglob("*.py")
    ):
        name = path.relative_to(root).as_posix()
        sources[name] = path.read_text(encoding="utf-8")
        contexts = data.contexts_by_lineno(str(path.resolve()))
        lines[name] = file_lines(sources[name], contexts, tests)
    return {"tests": list(tests), "sources": sources, "lines": lines}


def file_lines(
    text: str, contexts: dict[int, list[str]], tests: dict[str, int]
) -> dict[str, list[int]]:
    """Import-time or unexecuted statements stay unmapped, selecting every test."""
    tree = ast.parse(text)
    spans = statement_spans(tree)
    result: dict[str, list[int]] = {}
    for line in function_lines(tree):
        names = statement_contexts(spans[line], contexts)
        if names and "" not in names:
            result[str(line)] = function_indices(tests, names)
    return result


def statement_contexts(span: range, contexts: dict[int, list[str]]) -> set[str]:
    return {name for line in span for name in contexts.get(line, [])}


def function_indices(tests: dict[str, int], names: set[str]) -> list[int]:
    return sorted({function_index(tests, name) for name in names})


def function_index(tests: dict[str, int], context: str) -> int:
    """Phase suffixes and parameters collapse to one selectable test function."""
    function = context.rpartition("|")[0].partition("[")[0]
    return tests.setdefault(function, len(tests))


def last_line(node: ast.stmt) -> int:
    return node.end_lineno or node.lineno


def statement_spans(tree: ast.Module) -> dict[int, range]:
    """Breadth-first order lets nested statements replace their enclosing span."""
    spans: dict[int, range] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.stmt):
            continue
        span = range(node.lineno, last_line(node) + 1)
        spans.update(dict.fromkeys(span, span))
    return spans


def function_lines(tree: ast.Module) -> list[int]:
    """Signatures, decorators, class and module bodies remain unmapped."""
    return sorted(
        {
            line
            for node in ast.walk(tree)
            if isinstance(node, FUNCTIONS)
            for line in range(node.body[0].lineno, last_line(node) + 1)
        }
    )
