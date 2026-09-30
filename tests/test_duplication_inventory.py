"""Reject substituted, omitted, and malformed native scanner inventory."""

from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from quality.duplication_inventory import Eligible, duplication_inventory, nonnegative
from quality.report_data import array, record


def report(path: Path, content: bytes) -> dict[str, object]:
    return {
        "summary": {
            "by": "tokens",
            "totalFiles": 1,
            "files": [
                {
                    "bytes": len(content),
                    "complexity": 0,
                    "duplicatedLines": 0,
                    "duplicatedTokens": 0,
                    "format": "python",
                    "lines": 5,
                    "path": str(path),
                    "tokens": 50,
                }
            ],
        }
    }


def file(value: dict[str, object]) -> dict[str, object]:
    return record(array(record(value["summary"])["files"])[0])


def test_accepts_exact_native_file_inventory(tmp_path: Path) -> None:
    path = tmp_path / "quality" / "check.py"
    content = b"value = 1\n"
    assert duplication_inventory(report(path, content), path, content) == Eligible(
        len(content), 5, 50
    )


def test_eligible_receipt_cannot_be_rewritten() -> None:
    value = Eligible(5, 4, 50)
    field = "tokens"
    with pytest.raises(FrozenInstanceError):
        setattr(value, field, 49)


@pytest.mark.parametrize("bad", [True, 1.5, -1, "3"])
def test_rejects_noninteger_counts(bad: object) -> None:
    with pytest.raises(ValueError, match="nonnegative integer"):
        nonnegative(bad)


@pytest.mark.parametrize(
    ("field", "bad", "message"),
    [
        ("path", "/other.py", "identity"),
        ("path", "/zzzz.py", "identity"),
        ("format", "javascript", "identity"),
        ("format", "zzzz", "identity"),
        ("bytes", 42, "bytes"),
        ("bytes", 1, "bytes"),
        ("complexity", -1, "nonnegative"),
        ("duplicatedLines", -1, "nonnegative"),
        ("duplicatedTokens", -1, "nonnegative"),
        ("lines", 0, "empty source"),
        ("tokens", 0, "empty source"),
    ],
)
def test_rejects_substituted_file_field(
    tmp_path: Path, field: str, bad: object, message: str
) -> None:
    path = tmp_path / "check.py"
    value = report(path, b"pass\n")
    file(value)[field] = bad
    with pytest.raises(ValueError, match=message):
        duplication_inventory(value, path, b"pass\n")


@pytest.mark.parametrize("change", ["missing", "extra"])
def test_rejects_file_schema_change(tmp_path: Path, change: str) -> None:
    path = tmp_path / "check.py"
    value = report(path, b"pass\n")
    if change == "missing":
        del file(value)["tokens"]
    else:
        file(value)["new"] = 1
    with pytest.raises(ValueError, match="fields differ"):
        duplication_inventory(value, path, b"pass\n")


@pytest.mark.parametrize(
    "change", ["measure", "measure-later", "total", "total-zero", "duplicate"]
)
def test_rejects_incomplete_native_summary(tmp_path: Path, change: str) -> None:
    path = tmp_path / "check.py"
    value = report(path, b"pass\n")
    summary = record(value["summary"])
    if change == "measure":
        summary["by"] = "lines"
    elif change == "measure-later":
        summary["by"] = "zzzz"
    elif change == "total":
        summary["totalFiles"] = 2
    elif change == "total-zero":
        summary["totalFiles"] = 0
    else:
        array(summary["files"]).append(deepcopy(file(value)))
        summary["totalFiles"] = 2
    with pytest.raises(ValueError, match="measure|totals"):
        duplication_inventory(value, path, b"pass\n")


def test_only_blank_file_may_be_absent(tmp_path: Path) -> None:
    path = tmp_path / "check.py"
    value = report(path, b"pass\n")
    summary = record(value["summary"])
    summary["files"] = []
    summary["totalFiles"] = 0
    assert duplication_inventory(value, path, b"\n  \n") is None
    with pytest.raises(ValueError, match="omitted nonempty"):
        duplication_inventory(value, path, b"pass\n")
