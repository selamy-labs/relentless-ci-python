"""Qualify declaration policy with real source rather than fabricated AST values."""

import string
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from hypothesis import given
from hypothesis import strategies as st

from quality.incomplete import verify_file
from tests.test_incomplete import authored, native_command

ALLOWED = [
    "class Marker:\n    pass\n",
    "class DomainError(ValueError):\n    ...\n",
    'class Marker:\n    """A declaration."""\n    pass\n',
    (
        "from typing import Protocol\n"
        "class Port(Protocol):\n"
        "    def read(self) -> int: ...\n"
    ),
    (
        "import typing as types\n"
        "class Port(types.Protocol):\n"
        "    def read(self) -> int: pass\n"
    ),
    (
        "from typing_extensions import Protocol as Interface\n"
        "class Port(Interface):\n"
        "    async def read(self) -> int: ...\n"
    ),
    (
        "from typing import Protocol, TypeVar\n"
        "T = TypeVar('T', covariant=True)\n"
        "class Port(Protocol[T]):\n"
        "    def read(self) -> T: ...\n"
    ),
    (
        "from abc import ABC, abstractmethod\n"
        "class Port(ABC):\n"
        "    @abstractmethod\n"
        "    def read(self) -> int: raise NotImplementedError\n"
    ),
    (
        "import abc as abstract\n"
        "class Port(abstract.ABC):\n"
        "    @abstract.abstractmethod\n"
        "    async def read(self) -> int: raise NotImplementedError()\n"
    ),
    (
        "from abc import ABC, abstractmethod as declaration\n"
        "class Port(ABC):\n"
        "    @classmethod\n"
        "    @declaration\n"
        "    def read(cls) -> int: ...\n"
    ),
    (
        "from abc import ABC, abstractmethod\n"
        "class Port(ABC):\n"
        "    @property\n"
        "    @abstractmethod\n"
        "    def value(self) -> int: pass\n"
    ),
    (
        "from typing import Protocol\n"
        "def make() -> object:\n"
        "    class Port(Protocol):\n"
        "        def read(self) -> int: ...\n"
        "    return Port\n"
    ),
    (
        "def make() -> object:\n"
        "    from typing import Protocol as Interface\n"
        "    class Port(Interface):\n"
        "        def read(self) -> int: ...\n"
        "    return Port\n"
    ),
    (
        "from typing import Protocol\n"
        "values = [Protocol for Protocol in []]\n"
        "echo = lambda Protocol: Protocol\n"
        "class Port(Protocol):\n    def read(self) -> int: ...\n"
    ),
    (
        "from typing import Protocol\n"
        "class Box: value = 0\n"
        "def make() -> Box: return Box()\n"
        "make().value = 1\n"
        "match {}:\n    case {}: pass\n"
        "match None:\n    case _: pass\n"
        "class Port(Protocol):\n    def read(self) -> int: ...\n"
    ),
]

FORBIDDEN = [
    "def read() -> None: pass\n",
    "async def read() -> None: ...\n",
    "class Concrete:\n    def read(self) -> None: pass\n",
    "def read() -> int: raise NotImplementedError\n",
    "class Protocol: pass\nclass Port(Protocol):\n    def read(self) -> None: pass\n",
    (
        "from other import Protocol\n"
        "class Port(Protocol):\n"
        "    def read(self) -> None: ...\n"
    ),
    (
        "from .typing import Protocol\n"
        "class Port(Protocol):\n"
        "    def read(self) -> None: ...\n"
    ),
    (
        "from typing import Protocol\n"
        "Protocol = object\n"
        "class Port(Protocol):\n"
        "    def read(self) -> None: ...\n"
    ),
    (
        "from typing import Protocol\n"
        "if condition:\n"
        "    Protocol = object\n"
        "class Port(Protocol):\n"
        "    def read(self) -> None: ...\n"
    ),
    (
        "from typing import Protocol\n"
        "from other import *\n"
        "class Port(Protocol):\n"
        "    def read(self) -> None: ...\n"
    ),
    (
        "from typing import Protocol\n"
        "Interface = Protocol\n"
        "class Port(Interface):\n"
        "    def read(self) -> None: ...\n"
    ),
    (
        "from typing import Protocol\n"
        "def make(Protocol: type[object]) -> object:\n"
        "    class Port(Protocol):\n"
        "        def read(self) -> None: ...\n"
        "    return Port\n"
    ),
    (
        "import abc\n"
        "class Port:\n"
        "    abc = object()\n"
        "    @abc.abstractmethod\n"
        "    def read(self) -> None: ...\n"
    ),
    (
        "def abstractmethod(value: object) -> object: return value\n"
        "class Port:\n"
        "    @abstractmethod\n"
        "    def read(self) -> None: ...\n"
    ),
    (
        "from typing import Protocol\n"
        "class Port(Protocol):\n"
        "    def read(self) -> int:\n"
        "        def concrete() -> int: ...\n"
        "        return concrete()\n"
    ),
    (
        "from abc import abstractmethod\n"
        "class Port:\n"
        "    @abstractmethod\n"
        "    def read(self) -> int:\n"
        "        def concrete() -> int: ...\n"
        "        return concrete()\n"
    ),
    (
        "import abc\nabc.abstractmethod = object\n"
        "class Port:\n    @abc.abstractmethod\n"
        "    def read(self) -> None: ...\n"
    ),
    (
        "from typing import Protocol\n"
        "match {}:\n    case {**Protocol}: pass\n"
        "class Port(Protocol):\n    def read(self) -> None: ...\n"
    ),
    (
        "from typing import Protocol\n"
        "match []:\n    case [*Protocol]: pass\n"
        "class Port(Protocol):\n    def read(self) -> None: ...\n"
    ),
    (
        "from typing import Protocol\n"
        "match object():\n    case Protocol: pass\n"
        "class Port(Protocol):\n    def read(self) -> None: ...\n"
    ),
    (
        "from typing import Protocol\n"
        "try:\n    1 / 0\nexcept Exception as Protocol:\n    pass\n"
        "class Port(Protocol):\n    def read(self) -> None: ...\n"
    ),
    (
        "def base() -> type[object]: return object\n"
        "class Port(base()):\n    def read(self) -> None: ...\n"
    ),
]


@pytest.mark.parametrize("source", ALLOWED)
def test_accepts_genuine_declarations(tmp_path: Path, source: str) -> None:
    verify_file(authored(tmp_path, "quality/declarations.py", source))


@pytest.mark.parametrize("source", FORBIDDEN)
def test_rejects_concrete_stubs_and_false_declaration_bindings(
    tmp_path: Path, source: str
) -> None:
    with pytest.raises(ValueError, match="incomplete implementation"):
        verify_file(authored(tmp_path, "quality/declarations.py", source))


aliases = st.text(alphabet=string.ascii_letters, min_size=1, max_size=12).map(
    lambda suffix: f"Interface_{suffix}"
)


@given(aliases, st.sampled_from(["pass", "...", "raise NotImplementedError"]))
def test_protocol_import_alias_and_unrelated_parameter_do_not_change_acceptance(
    alias: str, body: str
) -> None:
    source = (
        f"from typing import Protocol as {alias}\n"
        f"def echo({alias}: object) -> object: return {alias}\n"
        f"class Port({alias}):\n    def read(self) -> int: {body}\n"
    )
    with TemporaryDirectory() as directory:
        verify_file(authored(Path(directory), "quality/declarations.py", source))


@pytest.mark.parametrize(
    ("source", "reason"),
    [
        (
            (
                "from abc import abstractmethod\n"
                "class Port:\n"
                "    @abstractmethod\n"
                "    def read(self) -> None: breakpoint()\n"
            ),
            "debug or disabled-test API",
        ),
        (
            (
                "from typing import Protocol\n"
                "class Port(Protocol):\n"
                "    def read(self) -> int: ...  # noqa\n"
            ),
            "suppressed comment",
        ),
    ],
)
def test_declaration_recognition_does_not_exempt_other_protections(
    tmp_path: Path, source: str, reason: str
) -> None:
    with pytest.raises(ValueError, match=reason):
        verify_file(authored(tmp_path, "quality/declarations.py", source))


NATIVE_DECLARATIONS = (
    "from abc import ABC, abstractmethod as declaration\n"
    "from typing import Protocol as Interface, TypeVar\n"
    "import typing_extensions as extensions\n"
    "T_co = TypeVar('T_co', covariant=True)\n"
    "class Marker: pass\n"
    "class DomainError(ValueError): pass\n"
    "class Port(Interface[T_co]):\n    def read(self) -> T_co: ...\n"
    "class AsyncPort(extensions.Protocol):\n"
    "    async def read(self) -> int: pass\n"
    "class AbstractPort(ABC):\n    @declaration\n"
    "    def read(self) -> int: raise NotImplementedError\n"
)


@pytest.mark.parametrize(
    ("source", "status"),
    [
        (NATIVE_DECLARATIONS, 0),
        ("def concrete() -> None: pass\n", 1),
        (
            "import abc\nabc = object()\nclass Port:\n"
            "    @abc.abstractmethod\n    def read(self) -> None: ...\n",
            1,
        ),
    ],
)
def test_native_gate_qualifies_declarations_and_concrete_controls(
    tmp_path: Path, source: str, status: int
) -> None:
    authored(tmp_path, "quality/declarations.py", source)
    result = native_command(tmp_path)

    assert result.returncode == status, result.stdout + result.stderr
    if status:
        assert "incomplete implementation" in result.stderr


def test_allowed_declarations_are_valid_under_the_native_type_checker(
    tmp_path: Path,
) -> None:
    path = authored(tmp_path, "declarations.py", NATIVE_DECLARATIONS)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--strict",
            "--no-incremental",
            "--cache-dir",
            str(tmp_path / "cache"),
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
