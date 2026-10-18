"""Resolve explicit import names and unambiguous bindings within lexical scopes."""

import ast
from collections import Counter
from collections.abc import Iterator

Scope = ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef


def module_aliases(node: ast.Import) -> dict[str, str]:
    """Map whole-module imports and their optional local aliases."""
    return {item.asname or item.name.split(".")[0]: item.name for item in node.names}


def member_aliases(node: ast.ImportFrom) -> dict[str, str]:
    """Map named imports; relative imports cannot name forbidden upstream APIs."""
    if node.module is None:
        return {}
    return {
        item.asname or item.name: f"{node.module}.{item.name}" for item in node.names
    }


def aliases(node: ast.AST) -> dict[str, str]:
    """Map one import's local bindings to their named upstream API."""
    if isinstance(node, ast.Import):
        return module_aliases(node)
    if isinstance(node, ast.ImportFrom):
        return member_aliases(node)
    return {}


def imported_names(tree: ast.AST) -> dict[str, str]:
    """Preserve the debugger check's existing direct-import inventory."""
    names: dict[str, str] = {}
    for node in ast.walk(tree):
        names.update(aliases(node))
    return names


def symbol(node: ast.expr, names: dict[str, str]) -> str | None:
    """Return the statically named API, including imported aliases."""
    if isinstance(node, ast.Name):
        return names.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        base = symbol(node.value, names)
        return f"{base}.{node.attr}" if base else None
    return None


def root_name(node: ast.expr) -> str | None:
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def imported_symbol(node: ast.expr, names: dict[str, str]) -> str | None:
    """Bare spellings cannot establish an imported declaration's identity."""
    if root_name(node) not in names:
        return None
    return symbol(node, names)


def definition_header(
    node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
) -> Iterator[ast.AST]:
    return (child for child in ast.iter_child_nodes(node) if child not in node.body)


def local_children(node: ast.AST) -> Iterator[ast.AST]:
    """Definitions bind their name here, but their bodies introduce child scopes."""
    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        return definition_header(node)
    if isinstance(node, ast.Lambda):
        return ast.iter_child_nodes(node.args)
    if isinstance(node, ast.comprehension):
        return iter([node.iter, *node.ifs])
    return ast.iter_child_nodes(node)


def local_nodes(node: ast.AST) -> Iterator[ast.AST]:
    yield node
    for child in local_children(node):
        yield from local_nodes(child)


def scope_nodes(scope: Scope) -> Iterator[ast.AST]:
    for statement in scope.body:
        yield from local_nodes(statement)


def bound_names(node: ast.AST) -> set[str]:
    """Include same-scope control-flow bindings without entering child bodies."""
    match node:
        case ast.Name(id=name, ctx=ast.Store() | ast.Del()):
            return {name}
        case ast.Attribute(ctx=ast.Store() | ast.Del()):
            root = root_name(node)
            return {root} if root else set()
        case ast.Import() | ast.ImportFrom():
            return set(aliases(node))
        case (
            ast.ClassDef(name=name)
            | ast.FunctionDef(name=name)
            | ast.AsyncFunctionDef(name=name)
        ):
            return {name}
        case _:
            return pattern_names(node)


def pattern_names(node: ast.AST) -> set[str]:
    match node:
        case (
            ast.ExceptHandler(name=optional)
            | ast.MatchAs(name=optional)
            | ast.MatchStar(name=optional)
        ):
            return {optional} if optional else set()
        case ast.MatchMapping(rest=rest):
            return {rest} if rest else set()
        case _:
            return set()


def parameters(scope: Scope) -> set[str]:
    if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return set()
    arguments = scope.args
    values = [
        *arguments.posonlyargs,
        *arguments.args,
        *arguments.kwonlyargs,
        arguments.vararg,
        arguments.kwarg,
    ]
    return {item.arg for item in values if item is not None}


def absolute_aliases(node: ast.AST) -> dict[str, str]:
    if isinstance(node, ast.ImportFrom) and node.level != 0:
        return {}
    return aliases(node)


def binding_counts(scope: Scope, nodes: list[ast.AST]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for node in nodes:
        counts.update(bound_names(node))
    counts.update(parameters(scope))
    return counts


def single_import(node: ast.AST, counts: Counter[str]) -> dict[str, str]:
    return {
        name: value
        for name, value in absolute_aliases(node).items()
        if counts[name] == 1
    }


def scope_imports(nodes: list[ast.AST], counts: Counter[str]) -> dict[str, str]:
    names: dict[str, str] = {}
    for node in nodes:
        names.update(single_import(node, counts))
    return names


def scope_bindings(scope: Scope, inherited: dict[str, str]) -> dict[str, str]:
    """Only a single explicit import can establish a declaration exemption."""
    nodes = list(scope_nodes(scope))
    counts = binding_counts(scope, nodes)
    if "*" in counts:
        return {}
    names = {name: value for name, value in inherited.items() if name not in counts}
    names.update(scope_imports(nodes, counts))
    return names
