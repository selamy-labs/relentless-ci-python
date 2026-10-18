"""Resolve enrolled library annotations under every declared Python runtime."""

import importlib
import inspect
import typing
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

from quality.source_scope import verify_sources


def module_name(path: Path) -> str:
    parts = (
        path.relative_to("src").with_suffix("").parts
        if path.parts[0] == "src"
        else path.with_suffix("").parts
    )
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def library_modules() -> list[ModuleType]:
    paths = sorted(Path("quality").rglob("*.py")) + sorted(Path("src").rglob("*.py"))
    names = [
        module_name(path)
        for path in paths
        if not path.name.endswith("_main.py") and path.name != "verify.py"
    ]
    return [importlib.import_module(name) for name in names]


def declared_members(module: ModuleType) -> Iterator[object]:
    for value in vars(module).values():
        if getattr(value, "__module__", None) == module.__name__:
            yield from annotated_members(value)


def annotated_members(value: object) -> Iterator[object]:
    if inspect.isfunction(value) or inspect.isclass(value):
        yield value
    if inspect.isclass(value):
        yield from class_methods(value)


def class_methods(owner: type[object]) -> Iterator[object]:
    for value in vars(owner).values():
        if inspect.isfunction(value):
            yield value


def test_library_discovery_matches_authored_scope() -> None:
    root = Path.cwd()
    expected = {
        path.relative_to(root)
        .with_suffix("")
        .as_posix()
        .removeprefix("src/")
        .removesuffix("/__init__")
        .replace("/", ".")
        for path in verify_sources(root)
        if path.relative_to(root).parts[0] in {"src", "quality"}
        and not path.name.endswith("_main.py")
        and path.name != "verify.py"
    }
    modules = library_modules()
    assert {module.__name__ for module in modules} == expected


def test_library_annotations_resolve_without_runtime_errors() -> None:
    members = [
        item for module in library_modules() for item in declared_members(module)
    ]
    for member in members:
        typing.get_type_hints(member)
