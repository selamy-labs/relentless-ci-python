"""Catch a broken collection order before costly native subprocess probes."""

from quality.test_ordering import priority


def test_non_native_case_stays_before_native_receipts() -> None:
    node = "tests/test_intervals.py::test_empty"
    assert priority(node) == (False, node)
