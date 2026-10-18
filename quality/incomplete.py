"""Reject unfinished or disabled authored Python without scanning string fixtures."""

from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

from quality.declaration_stubs import declaration_stubs, unfinished
from quality.python_bindings import imported_names, symbol
from quality.source_scope import verify_sources

MARKERS = re.compile(r"\b(?:TODO|FIXME|XXX)\b", re.IGNORECASE)
SUPPRESSIONS = re.compile(
    r"\b(?:noqa|nosec|type:\s*ignore|pyright:\s*ignore|mypy:\s*ignore-errors|"
    r"pragma:\s*no\s*(?:cover|branch)|ruff:\s*noqa|fmt:\s*off|semgrep:\s*ignore)\b",
    re.IGNORECASE,
)
FORBIDDEN = {
    "breakpoint",
    "builtins.breakpoint",
    "pdb.set_trace",
    "pytest.set_trace",
    "pytest.skip",
    "pytest.xfail",
    "unittest.skip",
    "unittest.skipIf",
    "unittest.skipUnless",
    "unittest.expectedFailure",
    "pytest.mark.skip",
    "pytest.mark.skipif",
    "pytest.mark.xfail",
}
APPROVED_CASTS = {
    (
        "quality/document_style.py",
        "cast(Callable[..., str], formatter)",
    ): "Pinned external formatter API",
    (
        "quality/mutation_config.py",
        "cast(Callable[[object], str], module.serialize_config)",
    ): "Pinned native serializer API",
    (
        "quality/mutation_coordinator.py",
        "cast(Callable[..., None], module.cli)",
    ): "Pinned native CLI API",
    (
        "quality/mutation_worker.py",
        "cast(Handler, module.handle_mutate_and_test)",
    ): "Pinned native worker API",
    (
        "quality/mutation_workspace.py",
        "cast(BaseExceptionGroup[BaseException], error)",
    ): "Runtime exception-group narrowing",
    ("quality/runtime_data.py", "cast(YamlAPI, yaml)"): "Pinned YAML adapter API",
}


def getattr_arguments(node: ast.Call) -> tuple[ast.expr, ast.expr] | None:
    """Recognize the common literal dynamic-attribute bypass shape."""
    if not isinstance(node.func, ast.Name) or node.func.id not in {"getattr"}:
        return None
    if len(node.args) not in (2, 3):
        return None
    return node.args[0], node.args[1]


def dynamic_api(node: ast.Call, names: dict[str, str]) -> str | None:
    """Resolve literal getattr on a statically named protected API."""
    pair = getattr_arguments(node)
    if pair is None or not isinstance(pair[1], ast.Constant):
        return None
    base = symbol(pair[0], names)
    name = pair[1].value
    return f"{base}.{name}" if base and isinstance(name, str) else None


def comments(source: str, path: Path) -> None:
    """Inspect lexical comments, leaving examples inside strings intact."""
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type in {tokenize.COMMENT} and (
            MARKERS.search(token.string) or SUPPRESSIONS.search(token.string)
        ):
            raise ValueError(
                f"{path}:{token.start[0]}: unfinished or suppressed comment"
            )


def api(node: ast.AST, names: dict[str, str]) -> str | None:
    """Read a call target or a bare decorator/reference."""
    if isinstance(node, ast.Call):
        return dynamic_api(node, names) or symbol(node.func, names)
    if isinstance(node, (ast.Attribute, ast.Name)):
        return symbol(node, names)
    return None


def reject_any(node: ast.AST, names: dict[str, str], location: str) -> None:
    """Reject statically named explicit Any, including import aliases."""
    if isinstance(node, (ast.Name, ast.Attribute)) and symbol(node, names) in {
        "typing.Any",
        "typing_extensions.Any",
    }:
        raise ValueError(f"{location}: explicit Any is unsupported")


def reject_unapproved_cast(
    node: ast.AST, names: dict[str, str], path: Path, location: str
) -> None:
    """Bind each existing third-party cast to its reviewed source expression."""
    if isinstance(node, ast.Call) and symbol(node.func, names) in {
        "typing.cast",
        "typing_extensions.cast",
    }:
        key = ("/".join(path.parts[-2:]), ast.unparse(node))
        if key not in APPROVED_CASTS:
            raise ValueError(f"{location}: unapproved type cast")


def verify_node(
    node: ast.AST,
    names: dict[str, str],
    path: Path,
    declarations: frozenset[ast.AST] = frozenset(),
) -> None:
    """Reject unfinished bodies, debug APIs and type escape hatches."""
    location = f"{path}:{getattr(node, 'lineno', 0)}"
    if node not in declarations and unfinished(node):
        raise ValueError(f"{location}: incomplete implementation")
    if api(node, names) in FORBIDDEN:
        raise ValueError(f"{location}: debug or disabled-test API")
    reject_any(node, names, location)
    reject_unapproved_cast(node, names, path, location)


def verify_file(path: Path) -> None:
    """Reject static debugger/test-disable APIs and unfinished definitions."""
    source = path.read_text(encoding="utf-8")
    comments(source, path)
    tree = ast.parse(source, filename=str(path))
    names = imported_names(tree)
    declarations = declaration_stubs(tree)
    for node in ast.walk(tree):
        verify_node(node, names, path, declarations)


def verify_incomplete(root: Path) -> None:
    """Use the complete independent authored-source inventory."""
    for path in verify_sources(root):
        verify_file(path)
