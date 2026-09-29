"""Real pytest subprocesses prove that successful exits can hide incomplete tests."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from quality.test_report import verify_test_report


def native(root: Path, source: str, arguments: list[str]) -> tuple[int, object]:
    path = root / "tests" / "test_example.py"
    path.parent.mkdir()
    path.write_text(source, encoding="utf-8")
    (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    env = dict(os.environ)
    env["PYTEST_ADDOPTS"] = ""
    command = [
        sys.executable,
        "-m",
        "pytest",
        "--json-report",
        "--json-report-file=tests.json",
        "-q",
        *arguments,
    ]
    result = subprocess.run(
        command,
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    value: object = json.loads((root / "tests.json").read_text(encoding="utf-8"))
    return result.returncode, value


def test_native_complete_receipt(tmp_path: Path) -> None:
    status, value = native(
        tmp_path,
        "def test_alpha():\n assert True\ndef test_beta():\n assert True\n",
        [],
    )
    assert status == 0
    verify_test_report(value, [tmp_path / "tests/test_example.py"], tmp_path)


@pytest.mark.parametrize(
    "source,arguments",
    [
        ("import pytest\n@pytest.mark.skip\ndef test_case():\n assert True\n", []),
        ("import pytest\n@pytest.mark.xfail\ndef test_case():\n assert False\n", []),
        ("import pytest\n@pytest.mark.xfail\ndef test_case():\n assert True\n", []),
        (
            "def test_alpha():\n assert True\ndef test_beta():\n assert True\n",
            ["-k", "alpha"],
        ),
    ],
)
def test_native_successful_exit_with_incomplete_results_fails(
    tmp_path: Path, source: str, arguments: list[str]
) -> None:
    status, value = native(tmp_path, source, arguments)
    assert status == 0
    with pytest.raises(ValueError):
        verify_test_report(value, [tmp_path / "tests/test_example.py"], tmp_path)


@pytest.mark.parametrize("source,status", [("", 5), ("invalid syntax!\n", 2)])
def test_native_empty_or_collection_error(
    tmp_path: Path, source: str, status: int
) -> None:
    actual, value = native(tmp_path, source, [])
    assert actual == status
    with pytest.raises(ValueError, match="exit successfully"):
        verify_test_report(value, [tmp_path / "tests/test_example.py"], tmp_path)
