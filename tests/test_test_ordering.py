"""Ordering preserves every identity and prioritizes direct behavioral witnesses."""

import pytest

from quality.test_ordering import priority
from tests import conftest
from tests.conftest import pytest_collection_modifyitems


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
    assert priority(node) == (late, node)


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

    assert priority(node) == (True, node)


def test_collection_rejects_broken_native_receipt_priority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(conftest, "priority", lambda node: (False, node))

    with pytest.raises(RuntimeError, match="native receipt ordering contract failed"):
        pytest_collection_modifyitems([])
