"""Exercise native parsing, graph membership and declared dependency boundaries."""

import os
import runpy
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import grimp
import pytest

from quality.architecture import (
    declared_dependencies,
    module_name,
    native_graph,
    owned_modules,
    tooling_dependencies,
    verify_architecture,
    verify_boundary,
    verify_edge,
    verify_external,
)


def repository(tmp_path: Path, source: str = "") -> Path:
    package = tmp_path / "src" / "probe_architecture"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "entry.py").write_text(source)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="probe"\nversion="1.0"\n'
        '[dependency-groups]\ndev=["pytest>=8"]\n'
    )
    return tmp_path


def deptry_result(root: Path) -> subprocess.CompletedProcess[str]:
    """Run the native analyzer against a deliberately defective repository."""
    return subprocess.run(
        [sys.executable, "-m", "deptry", "src", "--exclude", "^$"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


@pytest.mark.parametrize(
    ("path", "name"),
    [
        ("src/example/__init__.py", "example"),
        ("src/example/__about__.py", "example.__about__"),
        ("src/example/nested/child.py", "example.nested.child"),
        ("quality/check.py", "quality.check"),
        ("tests/__init__.py", "tests"),
    ],
)
def test_module_names(tmp_path: Path, path: str, name: str) -> None:
    assert module_name(tmp_path, tmp_path / path) == name


def test_module_name_uses_path_value_with_a_fresh_string(tmp_path: Path) -> None:
    source = bytearray(b"src").decode()
    path = tmp_path / source / "example.py"
    assert module_name(tmp_path, path) == "example"


def test_module_inventory(tmp_path: Path) -> None:
    paths = [tmp_path / "src" / "app.py", tmp_path / "quality" / "check.py"]
    assert owned_modules(tmp_path, paths) == {"app": "src", "quality.check": "quality"}
    with pytest.raises(ValueError, match="unique"):
        owned_modules(tmp_path, paths + paths)
    with pytest.raises(ValueError, match="nonempty"):
        owned_modules(tmp_path, [tmp_path / "src" / "__init__.py"])


def test_empty_graph_and_missing_native_module(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="empty"):
        native_graph(tmp_path, {})
    with patch(
        "quality.architecture.grimp.build_graph", return_value=grimp.ImportGraph()
    ):
        with pytest.raises(ValueError, match="incomplete"):
            native_graph(tmp_path, {"example": "src"})


def test_extra_native_module_is_not_silently_accepted(tmp_path: Path) -> None:
    graph = grimp.ImportGraph()
    graph.add_module("expected")
    graph.add_module("extra")
    with patch("quality.architecture.grimp.build_graph", return_value=graph):
        with pytest.raises(ValueError, match="incomplete"):
            native_graph(tmp_path, {"expected": "src"})


def test_native_failure_restores_import_path(tmp_path: Path) -> None:
    original = sys.path.copy()
    with patch(
        "quality.architecture.grimp.build_graph", side_effect=RuntimeError("failed")
    ):
        with pytest.raises(RuntimeError, match="failed"):
            native_graph(tmp_path, {"example": "src"})
    assert sys.path == original


def test_native_options_and_complete_inventory(tmp_path: Path) -> None:
    graph = grimp.ImportGraph()
    graph.add_module("example")
    graph.add_module("json", is_squashed=True)
    original = sys.path.copy()

    def build_graph(*_args: object, **_kwargs: object) -> grimp.ImportGraph:
        assert sys.path == [str(tmp_path / "src"), str(tmp_path), *original]
        return graph

    with patch(
        "quality.architecture.grimp.build_graph", side_effect=build_graph
    ) as build:
        assert native_graph(tmp_path, {"example": "src"}) is graph
    build.assert_called_once_with(
        "example",
        include_external_packages=True,
        exclude_type_checking_imports=False,
        cache_dir=None,
    )


def test_real_native_graph_and_clean_boundary(tmp_path: Path) -> None:
    root = repository(tmp_path, "import json\nfrom . import companion\n")
    (root / "src" / "probe_architecture" / "companion.py").write_text("")
    verify_architecture(root)


@pytest.mark.parametrize(
    "source",
    [
        "import pytest\n",
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n import pytest\n",
    ],
)
def test_native_dev_import_even_under_type_checking(
    tmp_path: Path, source: str
) -> None:
    with pytest.raises(ValueError, match="undeclared runtime"):
        verify_architecture(repository(tmp_path, source))


def test_declared_runtime_dependency_is_allowed(tmp_path: Path) -> None:
    root = repository(tmp_path, "import pytest\n")
    config = root / "pyproject.toml"
    config.write_text(
        config.read_text().replace(
            "[dependency-groups]", 'dependencies=["PyTest>=8"]\n[dependency-groups]'
        )
    )
    verify_architecture(root)


def test_unimported_nested_cycle(tmp_path: Path) -> None:
    root = repository(tmp_path)
    nested = root / "src" / "probe_architecture" / "nested"
    nested.mkdir()
    (nested / "__init__.py").write_text("")
    (nested / "first.py").write_text("from . import second\n")
    (nested / "second.py").write_text("from . import first\n")
    with pytest.raises(ValueError, match="cycle"):
        verify_architecture(root)


def test_cycle_across_package_roots(tmp_path: Path) -> None:
    root = repository(tmp_path, "import another_architecture\n")
    another = root / "src" / "another_architecture"
    another.mkdir()
    (another / "__init__.py").write_text("from probe_architecture import entry\n")
    with pytest.raises(ValueError, match="cycle"):
        verify_architecture(root)


def native_command(root: Path) -> subprocess.CompletedProcess[str]:
    original = Path(__file__).resolve().parents[1]
    shutil.copytree(
        original / "quality",
        root / "quality",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    (root / "pyproject.toml").write_text((original / "pyproject.toml").read_text())
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join([str(root / "src"), str(root)])
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "quality.architecture_main"],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_production_imports_other_source_scope(tmp_path: Path) -> None:
    result = native_command(repository(tmp_path, "import quality.commands\n"))
    assert result.returncode == 1
    assert "production imports tooling" in result.stderr


def test_native_tooling_can_use_declared_dev_dependencies(tmp_path: Path) -> None:
    root = repository(tmp_path)
    tests = root / "tests"
    tests.mkdir()
    (tests / "__init__.py").write_text("import pytest\n")
    result = native_command(root)
    assert result.returncode == 0, result.stderr


def test_tooling_unknown_dependency_fails(tmp_path: Path) -> None:
    root = repository(tmp_path)
    # Grimp's quality root is already loaded in this process; use an isolated
    # fake graph to verify the same boundary without importing a second copy.
    graph = grimp.ImportGraph()
    graph.add_module("quality")
    graph.add_module("unknown", is_squashed=True)
    graph.add_import(importer="quality", imported="unknown")
    with patch(
        "quality.architecture.owned_modules", return_value={"quality": "quality"}
    ):
        with patch("quality.architecture.native_graph", return_value=graph):
            with pytest.raises(ValueError, match="undeclared runtime"):
                verify_architecture(root)


@pytest.mark.parametrize("scope", ["tests", "quality"])
def test_production_forbidden_edge(scope: str) -> None:
    modules = {"app": "src", "tooling": scope}
    with pytest.raises(ValueError, match="production imports tooling"):
        verify_boundary(modules, "app", "tooling")
    verify_boundary(modules, "tooling", "app")


def test_boundary_uses_scope_values_with_fresh_strings() -> None:
    source = bytearray(b"src").decode()
    tooling = bytearray(b"quality").decode()
    modules = {"app": source, "tooling": tooling}
    with pytest.raises(ValueError, match="production imports tooling"):
        verify_boundary(modules, "app", "tooling")


def test_native_policy_classifies_fresh_source_scope(tmp_path: Path) -> None:
    root = repository(tmp_path)
    source = bytearray(b"src").decode()
    graph = grimp.ImportGraph()
    graph.add_module("app")
    graph.add_module("pytest", is_squashed=True)
    graph.add_import(importer="app", imported="pytest")
    with patch("quality.architecture.owned_modules", return_value={"app": source}):
        with patch("quality.architecture.native_graph", return_value=graph):
            with pytest.raises(ValueError, match="undeclared runtime"):
                verify_architecture(root)


def test_edge_cycle_and_noncyclic_production() -> None:
    graph = grimp.ImportGraph()
    for name in ["app", "other"]:
        graph.add_module(name)
    graph.add_import(importer="app", imported="other")
    modules = {"app": "src", "other": "src"}
    verify_edge(graph, modules, "app", "other", set(), {})
    graph.add_import(importer="other", imported="app")
    with pytest.raises(ValueError, match="cycle"):
        verify_edge(graph, modules, "app", "other", set(), {})


def test_external_declaration_and_provider_normalization() -> None:
    verify_external("app", "json", set(), {})
    verify_external(
        "app", "module.child", {"some-package"}, {"module": ["Some_Package"]}
    )
    with pytest.raises(ValueError, match="undeclared runtime"):
        verify_external("app", "missing", set(), {})
    with pytest.raises(ValueError, match="undeclared runtime"):
        verify_external("app", "module", {"other"}, {"module": ["Some_Package"]})


def test_dependency_sets_and_missing_groups(tmp_path: Path) -> None:
    root = repository(tmp_path)
    assert declared_dependencies(root) == set()
    assert tooling_dependencies(root, {"runtime"}) == {"runtime", "pytest"}
    (root / "pyproject.toml").write_text(
        '[project]\ndependencies=["Some_Package[extra]>=1"]\n'
    )
    assert declared_dependencies(root) == {"some-package"}
    assert tooling_dependencies(root, {"runtime"}) == {"runtime"}


def test_entry_point() -> None:
    with patch("quality.architecture.verify_architecture") as verify:
        runpy.run_module("quality.architecture_main", run_name="__main__")
    verify.assert_called_once_with(Path.cwd())


@pytest.mark.parametrize(
    ("source", "rule"),
    [
        ("import pytest\n", "DEP004"),
        ("import click\n", "DEP003"),
        ("import nonexistent_relentless_dependency\n", "DEP001"),
    ],
)
def test_real_deptry_production_defects(tmp_path: Path, source: str, rule: str) -> None:
    root = repository(tmp_path, source)
    result = deptry_result(root)
    assert result.returncode == 1
    assert rule in result.stderr


def test_real_deptry_unused_runtime_dependency(tmp_path: Path) -> None:
    root = repository(tmp_path)
    config = root / "pyproject.toml"
    config.write_text(
        config.read_text().replace(
            "[dependency-groups]", 'dependencies=["pytest"]\n[dependency-groups]'
        )
    )
    result = deptry_result(root)
    assert result.returncode == 1
    assert "DEP002" in result.stderr


def test_native_namespace_cannot_escape_inventory(tmp_path: Path) -> None:
    root = repository(tmp_path)
    nested = root / "src" / "probe_architecture" / "namespace"
    nested.mkdir()
    (nested / "unimported.py").write_text("import json\n")
    with pytest.raises(ValueError, match="inventory is incomplete"):
        verify_architecture(root)


def test_development_modules_may_import_each_other() -> None:
    modules = {"verifier": "quality", "test": "tests"}
    verify_boundary(modules, "test", "verifier")
    verify_boundary(modules, "verifier", "test")
