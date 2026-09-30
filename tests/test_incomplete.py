"""Source-aware negative probes for unfinished, disabled and suppressed Python."""

import ast
import importlib
import os
import runpy
import subprocess
import sys
import tokenize
from pathlib import Path

import pytest

from quality.incomplete import (
    comments,
    dynamic_api,
    empty_body,
    getattr_arguments,
    module_aliases,
    verify_file,
    verify_incomplete,
    verify_node,
)


def authored(root: Path, name: str, source: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def test_accepts_completed_code_and_literal_fixture_text(tmp_path: Path) -> None:
    source = (
        '"""A sample string mentions TODO, # noqa and pytest.skip()."""\n'
        "def actual() -> int:\n    return 1\n"
        "try:\n    actual()\nexcept ValueError:\n    pass\n"
        'example = "breakpoint() # FIXME"\n'
        "def constant_expression():\n    1\n"
        "def two_statements():\n    value = 1\n    return value\n"
        "from . import local\n"
        "make().unknown()\n"
        "getattr(thing, 'allowed')\n"
        "getattr(thing, attribute)\n"
        "getattr(thing, 1)\n"
        "getattr(make(), 'skip')\n"
        "getattr(thing)\n"
    )
    path = authored(tmp_path, "quality/check.py", source)
    verify_file(path)
    verify_incomplete(tmp_path)


def test_dotted_import_binds_its_first_component() -> None:
    node = ast.parse("import package.module").body[0]
    assert isinstance(node, ast.Import)
    assert module_aliases(node) == {"package": "package.module"}


@pytest.mark.parametrize("function", ["alpha", "zeta"])
def test_only_literal_getattr_is_dynamic(function: str) -> None:
    expression = ast.parse(f"{function}(pytest, 'skip')").body[0]
    assert isinstance(expression, ast.Expr)
    assert isinstance(expression.value, ast.Call)
    assert getattr_arguments(expression.value) is None


def test_dynamic_api_requires_statically_named_base() -> None:
    expression = ast.parse("getattr(make(), 'skip')").body[0]
    assert isinstance(expression, ast.Expr)
    assert isinstance(expression.value, ast.Call)
    assert dynamic_api(expression.value, {}) is None


@pytest.mark.parametrize("error", ["AError", "ZError"])
def test_other_exception_names_are_complete(tmp_path: Path, error: str) -> None:
    verify_file(
        authored(tmp_path, "quality/check.py", f"def run():\n    raise {error}\n")
    )


def test_ast_empty_body_is_not_a_single_placeholder() -> None:
    function = ast.parse("def run():\n    pass\n").body[0]
    assert isinstance(function, ast.FunctionDef)
    function.body = []
    assert empty_body(function) is False


def test_two_statement_body_with_pass_is_not_empty() -> None:
    function = ast.parse("def run():\n    pass\n    return 1\n").body[0]
    assert isinstance(function, ast.FunctionDef)
    assert empty_body(function) is False


def test_ellipsis_identity_does_not_accept_custom_equality() -> None:
    class EqualToEllipsis:
        def __eq__(self, other: object) -> bool:
            return other is Ellipsis

    function = ast.parse("def run():\n    ...\n").body[0]
    assert isinstance(function, ast.FunctionDef)
    expression = function.body[0]
    assert isinstance(expression, ast.Expr)
    expression.value = ast.Constant(value=Ellipsis)
    field = "value"
    setattr(expression.value, field, EqualToEllipsis())
    assert empty_body(function) is False


def test_unfinished_comment_reports_line_not_column() -> None:
    with pytest.raises(ValueError, match=r"check.py:2: unfinished"):
        comments("value = 1\nvalue = 2  # TODO\n", Path("check.py"))


def test_non_comment_token_cannot_supply_a_suppression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = tokenize.TokenInfo(tokenize.COMMENT + 1, "# TODO", (1, 0), (1, 6), "")

    def generated(*_args: object) -> list[tokenize.TokenInfo]:
        return [token]

    monkeypatch.setattr(tokenize, "generate_tokens", generated)
    comments("ignored", Path("check.py"))


def test_location_defaults_to_zero_for_synthetic_node() -> None:
    node = ast.Name(id="breakpoint", ctx=ast.Load())
    with pytest.raises(ValueError, match=r"check.py:0: debug"):
        verify_node(node, {}, Path("check.py"))


@pytest.mark.parametrize(
    "source",
    [
        "breakpoint()\n",
        "import builtins as b\nb.breakpoint()\n",
        "import pdb as debug\ndebug.set_trace()\n",
        "from pdb import set_trace as pause\npause()\n",
        "import pytest as pt\npt.set_trace()\n",
        "import pytest as pt\npt.skip('reason')\n",
        "from pytest import xfail as expected\nexpected('reason')\n",
        "import pytest as pt\ngetattr(pt.mark, 'skip')\n",
        "import pytest as pt\ngetattr(pt.mark, 'skip', None)\n",
        "import pytest as pt\ngetattr(pt, 'xfail')\n",
        (
            "import unittest as unit\n@unit.skip('reason')\n"
            "def test_case():\n    assert True\n"
        ),
        (
            "from unittest import skipIf as conditional\n"
            "@conditional(True, 'reason')\ndef test_case():\n    assert True\n"
        ),
        (
            "from unittest import skipUnless\n@skipUnless(False, 'reason')\n"
            "def test_case():\n    assert True\n"
        ),
        (
            "from unittest import expectedFailure\n@expectedFailure\n"
            "def test_case():\n    assert True\n"
        ),
        "import pytest as pt\n@pt.mark.skip\ndef test_case():\n    assert True\n",
        (
            "from pytest import mark as m\n@m.skipif(False)\n"
            "def test_case():\n    assert True\n"
        ),
        "import pytest\n@pytest.mark.xfail\ndef test_case():\n    assert True\n",
        "def pending():\n    pass\n",
        'def pending():\n    """Documented only."""\n    ...\n',
        "async def pending():\n    pass\n",
        'class Pending:\n    """Documented only."""\n    pass\n',
        "def pending():\n    raise NotImplementedError\n",
        "def pending():\n    raise NotImplementedError()\n",
        "# TODO: finish later\nvalue = 1\n",
        "# FIXME: broken\nvalue = 1\n",
        "# XXX: revisit\nvalue = 1\n",
        "value = 1  # noqa: F401\n",
        "value = 1  # type: ignore\n",
        "value = 1  # pragma: no cover\n",
        "value = 1  # pragma: no branch\n",
        "value = 1  # nosec\n",
        "value = 1  # fmt: off\n",
        "value = 1  # ruff: noqa\n",
        "value = 1  # pyright: ignore\n",
        "value = 1  # mypy: ignore-errors\n",
        "value = 1  # semgrep: ignore\n",
    ],
)
def test_rejects_unfinished_or_disabled_source(tmp_path: Path, source: str) -> None:
    path = authored(tmp_path, "quality/check.py", source)
    with pytest.raises(ValueError, match="incomplete|debug|suppressed"):
        verify_file(path)


def test_nested_never_imported_file_is_enrolled(tmp_path: Path) -> None:
    authored(tmp_path, "src/package/good.py", "value = 1\n")
    authored(tmp_path, "tests/nested/hidden.py", "breakpoint()\n")
    with pytest.raises(ValueError, match="debug or disabled-test API"):
        verify_incomplete(tmp_path)


def test_empty_inventory_fails(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no authored Python"):
        verify_incomplete(tmp_path)


def test_main_uses_current_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    authored(tmp_path, "quality/check.py", "value = 1\n")
    monkeypatch.chdir(tmp_path)
    runpy.run_module("quality.incomplete_main", run_name="__main__")
    assert callable(importlib.import_module("quality.incomplete_main").main)


def test_native_command_rejects_defect(tmp_path: Path) -> None:
    authored(tmp_path, "quality/check.py", "breakpoint()\n")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "quality.incomplete_main"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode != 0
    assert "debug or disabled-test API" in result.stderr
