"""Distinguish explicit interface declarations from unfinished concrete bodies."""

import ast
from collections.abc import Iterator

from quality.python_bindings import Scope, imported_symbol, scope_bindings, scope_nodes

PROTOCOLS = {"typing.Protocol", "typing_extensions.Protocol"}


def implementation_body(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.stmt]:
    """A leading docstring cannot make an otherwise empty body complete."""
    body = node.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
    ):
        if isinstance(body[0].value.value, str):
            return body[1:]
    return body


def raises_unimplemented(node: ast.AST) -> bool:
    if isinstance(node, ast.Raise):
        exc = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
        return isinstance(exc, ast.Name) and exc.id in {"NotImplementedError"}
    return False


def empty_body(node: ast.AST) -> bool:
    """Concrete function placeholders are unfinished; empty classes are declarations."""
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    body = implementation_body(node)
    if len(body) != 1:
        return False
    sole = next(iter(body))
    return isinstance(sole, ast.Pass) or (
        isinstance(sole, ast.Expr)
        and isinstance(sole.value, ast.Constant)
        and sole.value.value is Ellipsis
    )


def unfinished(node: ast.AST) -> bool:
    return raises_unimplemented(node) or empty_body(node)


def protocol_base(base: ast.expr, names: dict[str, str]) -> bool:
    expression = base.value if isinstance(base, ast.Subscript) else base
    return imported_symbol(expression, names) in PROTOCOLS


def protocol(scope: Scope, names: dict[str, str]) -> bool:
    return isinstance(scope, ast.ClassDef) and any(
        protocol_base(base, names) for base in scope.bases
    )


def abstract_method(
    node: ast.FunctionDef | ast.AsyncFunctionDef, names: dict[str, str]
) -> bool:
    return any(
        imported_symbol(item, names) == "abc.abstractmethod"
        for item in node.decorator_list
    )


def declaration_nodes(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[ast.AST]:
    match implementation_body(node):
        case [sole] if raises_unimplemented(sole):
            return {node, sole}
        case _:
            return {node}


def methods(scope: ast.ClassDef) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    return (
        node
        for node in scope_nodes(scope)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


def class_stub_nodes(
    scope: Scope, names: dict[str, str], header: dict[str, str]
) -> set[ast.AST]:
    if not isinstance(scope, ast.ClassDef):
        return set()
    is_protocol = protocol(scope, header)
    found: set[ast.AST] = set()
    for method in methods(scope):
        if is_protocol or abstract_method(method, names):
            found.update(declaration_nodes(method))
    return found


def scope_stubs(
    scope: Scope, inherited: dict[str, str], header: dict[str, str]
) -> set[ast.AST]:
    names = scope_bindings(scope, inherited)
    found = class_stub_nodes(scope, names, header)
    closure = inherited if isinstance(scope, ast.ClassDef) else names
    for node in scope_nodes(scope):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            found.update(scope_stubs(node, closure, names))
    return found


def declaration_stubs(tree: ast.Module) -> frozenset[ast.AST]:
    """Exempt only the actual declaration, never its nested concrete definitions."""
    return frozenset(scope_stubs(tree, {}, {}))
