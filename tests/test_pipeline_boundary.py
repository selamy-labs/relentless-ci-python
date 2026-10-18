"""Qualify the narrow pipeline direction using native graphs and source fixtures."""

from pathlib import Path

import grimp
import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from quality.architecture import verify_pipeline_boundary
from tests.test_architecture import native_command, repository

CLIENTS = ("quality.workflows", "quality.support_files", "quality.command_args")
NODES = (*CLIENTS, "quality.pipeline", "quality.verify", "tests.check", "quality.leaf")
edges = st.sets(st.tuples(st.sampled_from(NODES), st.sampled_from(NODES)), max_size=12)


def import_graph(imports: set[tuple[str, str]]) -> grimp.ImportGraph:
    graph = grimp.ImportGraph()
    for name in NODES:
        graph.add_module(name)
    for importer, imported in imports:
        graph.add_import(importer=importer, imported=imported)
    return graph


def reachable(imports: set[tuple[str, str]], start: str) -> set[str]:
    found = {start}
    for _ in range(len(imports)):
        found |= {target for source, target in imports if source in found}
    return found


@given(edges)
@example(set())
def test_boundary_agrees_with_independent_reachability(
    imports: set[tuple[str, str]],
) -> None:
    forbidden = any(
        "quality.pipeline" in reachable(imports, client) for client in CLIENTS
    )
    graph = import_graph(imports)

    if forbidden:
        with pytest.raises(ValueError, match="checker imports pipeline"):
            verify_pipeline_boundary(graph)
    else:
        verify_pipeline_boundary(graph)


@pytest.mark.parametrize("client", CLIENTS)
@pytest.mark.parametrize("indirect", [False, True], ids=["direct", "transitive"])
def test_source_boundary_rejects_upward_paths(
    tmp_path: Path, client: str, indirect: bool
) -> None:
    root = repository(tmp_path)
    dependency = "leaf" if indirect else "pipeline"
    sources = (
        (f"{client.split('.')[-1]}.py", f"import quality.{dependency}\n"),
        ("leaf.py", "import quality.pipeline\n"),
    )

    result = native_command(root, sources)

    assert result.returncode == 1
    assert "checker imports pipeline" in result.stderr


def test_entrypoints_and_tests_may_import_pipeline() -> None:
    verify_pipeline_boundary(
        import_graph(
            {
                ("quality.verify", "quality.pipeline"),
                ("tests.check", "quality.pipeline"),
            }
        )
    )


def test_repositories_without_pipeline_are_accepted() -> None:
    graph = grimp.ImportGraph()
    graph.add_module("quality.workflows")
    verify_pipeline_boundary(graph)


def test_multiple_violations_report_a_stable_first_importer() -> None:
    graph = import_graph({(client, "quality.pipeline") for client in CLIENTS})

    with pytest.raises(ValueError) as error:
        verify_pipeline_boundary(graph)

    assert str(error.value) == "checker imports pipeline: quality.command_args"
