"""Malformed and incomplete pytest receipts cannot pass verification."""

import json
from pathlib import Path

import pytest

from quality.report_data import array, record
from quality.test_report import (
    prepare_tests,
    report_path,
    verify_test_report,
    verify_tests,
)


def complete(root: Path) -> dict[str, object]:
    tests = [
        {
            "nodeid": f"{name}::test_case",
            "outcome": "passed",
            **{stage: {"outcome": "passed"} for stage in ("setup", "call", "teardown")},
        }
        for name in ("tests/test_first.py", "tests/nested/second_test.py")
    ]
    return {
        "exitcode": 0,
        "root": str(root),
        "summary": {"collected": 2, "total": 2, "passed": 2},
        "tests": tests,
        "collectors": [
            {
                "outcome": "passed",
                "result": [
                    {"nodeid": case["nodeid"], "type": "Function"} for case in tests
                ],
            }
        ],
    }


def expected(root: Path) -> list[Path]:
    return [root / "tests/test_first.py", root / "tests/nested/second_test.py"]


def test_complete_report_and_zero_extra_counts(tmp_path: Path) -> None:
    data = complete(tmp_path)
    verify_test_report(data, expected(tmp_path), tmp_path)
    record(data["summary"])["deselected"] = 0
    data["warnings"] = []
    verify_test_report(data, expected(tmp_path), tmp_path)


@pytest.mark.parametrize("field", ["collected", "total", "passed"])
@pytest.mark.parametrize("count", [True, "2", None, -1, 1, 3])
def test_summary_count_corruption(tmp_path: Path, field: str, count: object) -> None:
    data = complete(tmp_path)
    record(data["summary"])[field] = count
    with pytest.raises(ValueError):
        verify_test_report(data, expected(tmp_path), tmp_path)


@pytest.mark.parametrize(
    "field", ["deselected", "skipped", "xfailed", "xpassed", "failed", "error"]
)
@pytest.mark.parametrize("count", [-1, 1])
def test_unsuccessful_summary(tmp_path: Path, field: str, count: int) -> None:
    data = complete(tmp_path)
    record(data["summary"])[field] = count
    with pytest.raises(ValueError, match="unsuccessful or deselected"):
        verify_test_report(data, expected(tmp_path), tmp_path)


@pytest.mark.parametrize(
    "status", ["skipped", "failed", "xfailed", "xpassed", "", None]
)
@pytest.mark.parametrize("stage", ["setup", "call", "teardown", "test", "collector"])
def test_every_stage_and_collector_must_pass(
    tmp_path: Path, status: object, stage: str
) -> None:
    data = complete(tmp_path)
    item = record(array(data["tests"])[0])
    if stage == "collector":
        item = record(array(data["collectors"])[0])
    elif stage != "test":
        item = record(item[stage])
    item["outcome"] = status
    with pytest.raises(ValueError, match="every test stage and collector must pass"):
        verify_test_report(data, expected(tmp_path), tmp_path)


@pytest.mark.parametrize("exitcode", [1, -1, True, "0", None])
def test_bad_exit_status(tmp_path: Path, exitcode: object) -> None:
    data = complete(tmp_path)
    data["exitcode"] = exitcode
    with pytest.raises(ValueError):
        verify_test_report(data, expected(tmp_path), tmp_path)


def test_report_root_warnings_empty_and_missing(tmp_path: Path) -> None:
    cases: list[tuple[str, object, str]] = [
        ("root", str(tmp_path / "other"), "root differs"),
        ("root", str(tmp_path.parent), "root differs"),
        ("warnings", [{}], "warnings are forbidden"),
        ("tests", [], "test inventory is empty"),
        ("collectors", [], "collector inventory is empty"),
    ]
    for key, value, message in cases:
        data = complete(tmp_path)
        data[key] = value
        with pytest.raises(ValueError, match=message):
            verify_test_report(data, expected(tmp_path), tmp_path)
    for key in complete(tmp_path):
        data = complete(tmp_path)
        del data[key]
        with pytest.raises(KeyError):
            verify_test_report(data, expected(tmp_path), tmp_path)


def test_duplicate_cases_and_file_inventory(tmp_path: Path) -> None:
    data = complete(tmp_path)
    array(data["tests"])[1] = array(data["tests"])[0]
    with pytest.raises(ValueError, match="duplicate test identifiers"):
        verify_test_report(data, expected(tmp_path), tmp_path)
    for paths in ([], expected(tmp_path)[:1], expected(tmp_path) * 2):
        with pytest.raises(ValueError, match="test file inventory differs"):
            verify_test_report(complete(tmp_path), paths, tmp_path)


def test_discovery_and_fresh_receipts(tmp_path: Path) -> None:
    sources = expected(tmp_path) + [
        tmp_path / "tests/helper.py",
        tmp_path / "src/tests/test_hidden.py",
        tmp_path / "quality/test_hidden.py",
    ]
    prepare_tests(tmp_path)
    report_path(tmp_path).write_text(json.dumps(complete(tmp_path)), encoding="utf-8")
    verify_tests(tmp_path, sources)
    with pytest.raises(ValueError, match="test file inventory differs"):
        verify_tests(tmp_path, sources + [tmp_path / "tests/test_missing.py"])
    prepare_tests(tmp_path)
    with pytest.raises(FileNotFoundError):
        verify_tests(tmp_path, sources)
    report_path(tmp_path).write_text("broken", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        verify_tests(tmp_path, sources)


@pytest.mark.parametrize("exitcode", [False, True, 0.0])
def test_exit_status_cannot_coerce_boolean_or_float(
    tmp_path: Path, exitcode: object
) -> None:
    data = complete(tmp_path)
    data["exitcode"] = exitcode
    with pytest.raises(ValueError, match="must be integers"):
        verify_test_report(data, expected(tmp_path), tmp_path)


def test_large_counts_use_value_equality(tmp_path: Path) -> None:
    data = complete(tmp_path)
    template = record(array(data["tests"])[0])
    cases = [
        {**template, "nodeid": f"tests/test_first.py::test_case[{i}]"}
        for i in range(300)
    ]
    data["tests"] = cases
    data["summary"] = {"collected": 300, "total": 300, "passed": 300}
    data["collectors"] = [
        {
            "outcome": "passed",
            "result": [
                {"nodeid": case["nodeid"], "type": "Function"} for case in cases
            ],
        }
    ]
    verify_test_report(data, [tmp_path / "tests/test_first.py"], tmp_path)


def test_collection_identifiers_are_complete_and_unique(tmp_path: Path) -> None:
    data = complete(tmp_path)
    collector = record(array(data["collectors"])[0])
    children = array(collector["result"])
    children.append(children[0])
    with pytest.raises(ValueError, match="duplicate collected test identifiers"):
        verify_test_report(data, expected(tmp_path), tmp_path)
    children.pop()
    children.pop()
    with pytest.raises(ValueError, match="collected test identifiers differ"):
        verify_test_report(data, expected(tmp_path), tmp_path)


def test_groups_and_unittest_items_are_supported(tmp_path: Path) -> None:
    data = complete(tmp_path)
    children = array(record(array(data["collectors"])[0])["result"])
    record(children[0])["type"] = "TestCaseFunction"
    children.append({"nodeid": "tests", "type": "Package"})
    verify_test_report(data, expected(tmp_path), tmp_path)


def test_unexecuted_collected_case_is_forbidden(tmp_path: Path) -> None:
    data = complete(tmp_path)
    children = array(record(array(data["collectors"])[0])["result"])
    children.append(
        {"nodeid": "tests/test_first.py::test_unexecuted", "type": "Function"}
    )
    with pytest.raises(ValueError, match="collected test identifiers differ"):
        verify_test_report(data, expected(tmp_path), tmp_path)
