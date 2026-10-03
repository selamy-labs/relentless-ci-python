"""Ordering preserves every identity and prioritizes direct behavioral witnesses."""

import hashlib

import pytest

from quality.test_ordering import FAST_FIRST, priority
from tests.conftest import pytest_collection_modifyitems

EXPECTED_FIRST_SHA256 = (
    "6667e18e42d0c48550a164a1012a1732a2d094c654355392dee5723479ebf7f7"
)


@pytest.mark.parametrize(
    "node,late",
    [
        ("tests/test_pytest_integrity.py::test_native_complete_receipt", True),
        ("tests/test_pytest_integrity.py::test_case[param]", True),
        ("tests/test_owned_process_native.py::test_case", True),
        ("tests/test_owned_caller_native.py::test_case", True),
        ("tests/nested/test_owned_caller_native.py::test_case", False),
        ("tests/nested/test_owned_process_native.py::test_case", False),
        ("tests/test_owned_process_native.py.backup::test_case", False),
        ("tests/test_owned_process.py::test_case", False),
        (
            "tests/test_process_cleanup.py::"
            "test_native_timeout_terminates_descendant_before_it_writes",
            True,
        ),
        (
            "tests/test_process_cleanup.py::test_stop_uses_platform_tree_and_reaps",
            False,
        ),
        ("tests/test_test_report.py::test_receipt", False),
        ("tests/nested/test_pytest_integrity.py::test_case", False),
        ("tests/test_pytest_integrity.py.backup::test_case", False),
    ],
)
def test_priority_uses_only_the_exact_native_receipt_module(
    node: str, late: bool
) -> None:
    assert priority(node)[0] is late
    assert priority(node)[2] == node


def test_ordering_preserves_duplicates_and_empty_inventory() -> None:
    nodes = [
        "tests/test_pytest_integrity.py::test_z",
        "tests/test_workflows.py::test_b",
        "tests/test_workflows.py::test_a",
        "tests/test_workflows.py::test_a",
    ]
    assert sorted(nodes, key=priority) == [nodes[2], nodes[3], nodes[1], nodes[0]]
    pytest_collection_modifyitems([])


def test_constructed_cleanup_identity_has_value_equality() -> None:
    node = "::".join(
        [
            "tests/test_process_cleanup.py",
            "test_native_timeout_terminates_descendant_before_it_writes",
        ]
    )

    assert priority(node) == (True, 30, node)


def test_evidence_rank_is_exact_and_unknown_files_remain_enrolled() -> None:
    assert len(FAST_FIRST) == 30
    assert hashlib.sha256("\n".join(FAST_FIRST).encode()).hexdigest() == (
        EXPECTED_FIRST_SHA256
    )
    assert [priority(file + "::witness")[1] for file in FAST_FIRST] == list(range(30))
    assert priority("tests/new_feature.py::test_case") == (
        False,
        30,
        "tests/new_feature.py::test_case",
    )
