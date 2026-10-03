"""Bounded deterministic malformed-input fuzzing through both CLI boundaries."""

import io
import json
import string
import subprocess

import pytest
from hypothesis import example, given, seed, settings
from hypothesis import strategies as st

from relentless_example.cli import run

TEXT = st.text(alphabet=string.ascii_letters + string.digits, max_size=64)
INVALID = st.one_of(
    st.booleans(),
    st.none(),
    TEXT,
    st.integers(-100, 100).map(lambda number: number + 0.5),
)


def malformed(value: str, mode: int) -> str:
    encoded = json.dumps(value)
    return (
        encoded[:-1],
        "[" + encoded,
        '{"value":' + encoded,
        "[" + encoded + ",]",
    )[mode]


def typed_endpoint(value: object, first: bool) -> str:
    return json.dumps([[value, 0]] if first else [[0, value]])


def parser_rejects(text: str, message: str) -> None:
    assert len(text.encode("utf-8")) <= 512
    stdout, stderr = io.StringIO(), io.StringIO()
    assert run(io.StringIO(text), stdout, stderr) == 2
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == f"error: {message}\n"


def installed_rejects(text: str, message: str) -> None:
    assert len(text.encode("utf-8")) <= 512
    result = subprocess.run(
        ["relentless-example"],
        input=text,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        "",
        f"error: {message}\n",
    )


@seed(20260929)
@settings(max_examples=200, deadline=None)
@given(value=TEXT, mode=st.integers(0, 3))
@example(value="", mode=0)
@example(value="", mode=1)
@example(value="", mode=2)
@example(value="", mode=3)
def test_bounded_malformed_json_parser(value: str, mode: int) -> None:
    parser_rejects(malformed(value, mode), "invalid JSON")


@seed(20260929)
@settings(max_examples=200, deadline=None)
@given(value=INVALID, first=st.booleans())
@example(value=False, first=True)
@example(value=None, first=False)
@example(value="invalid", first=True)
@example(value=0.5, first=False)
def test_bounded_invalid_endpoint_parser(value: object, first: bool) -> None:
    parser_rejects(typed_endpoint(value, first), "endpoints must be integers")


@seed(20260929)
@settings(max_examples=32, deadline=None)
@given(value=TEXT, mode=st.integers(0, 3))
def test_bounded_malformed_json_installed(value: str, mode: int) -> None:
    installed_rejects(malformed(value, mode), "invalid JSON")


@seed(20260929)
@settings(max_examples=32, deadline=None)
@given(value=INVALID, first=st.booleans())
def test_bounded_invalid_endpoint_installed(value: object, first: bool) -> None:
    installed_rejects(typed_endpoint(value, first), "endpoints must be integers")


@pytest.mark.parametrize("mode", range(4))
def test_malformed_json_installed_edges(mode: int) -> None:
    installed_rejects(malformed("", mode), "invalid JSON")


@pytest.mark.parametrize("value", [False, None, "invalid", 0.5])
@pytest.mark.parametrize("first", [True, False])
def test_invalid_endpoint_installed_edges(value: object, first: bool) -> None:
    installed_rejects(typed_endpoint(value, first), "endpoints must be integers")
