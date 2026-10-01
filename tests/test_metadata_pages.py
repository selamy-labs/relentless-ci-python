"""Incomplete, drifting or malformed native pages cannot become complete evidence."""

from collections.abc import Iterator

import pytest

from quality.trusted_policy.metadata_pages import (
    array_inventory,
    object_inventory,
    page_route,
    sequence,
)
from quality.trusted_policy.review_policy import PolicyFailure


class Pages:
    def __init__(self, values: list[object]) -> None:
        self.values: Iterator[object] = iter(values)
        self.routes: list[str] = []

    def __call__(self, endpoint: str) -> object:
        self.routes.append(endpoint)
        return next(self.values)


def test_native_association_requires_array() -> None:
    assert sequence([{"number": 1}]) == [{"number": 1}]
    with pytest.raises(PolicyFailure, match="array"):
        sequence({"number": 1})


def test_array_inventory_requires_explicit_terminal_empty_page() -> None:
    api = Pages([[1], [2, 3], []])

    result = array_inventory(api, "repos/owner/repo/pulls/1/reviews")

    assert result == [1, 2, 3]
    assert api.routes == [
        f"repos/owner/repo/pulls/1/reviews?per_page=100&page={page}"
        for page in (1, 2, 3)
    ]


def test_full_page_continues_into_next_page() -> None:
    api = Pages([list(range(100)), [100], []])

    assert array_inventory(api, "endpoint") == list(range(101))


def test_job_pages_require_stable_native_count_and_terminal_empty_page() -> None:
    api = Pages(
        [
            {"total_count": 2, "jobs": [1]},
            {"total_count": 2, "jobs": [2]},
            {"total_count": 2, "jobs": []},
        ]
    )

    assert object_inventory(api, "endpoint", "jobs") == (2, [1, 2])


def test_zero_native_jobs_returns_complete_empty_inventory() -> None:
    api = Pages([{"total_count": 0, "jobs": []}])

    assert object_inventory(api, "endpoint", "jobs") == (0, [])


@pytest.mark.parametrize("value", [None, {}, "array", list(range(101))])
def test_malformed_or_oversized_array_page_fails(value: object) -> None:
    api = Pages([value])

    with pytest.raises(PolicyFailure):
        array_inventory(api, "endpoint")


@pytest.mark.parametrize("total", [False, True, -1, 0.0, "1", None])
def test_native_count_requires_nonnegative_integer(total: object) -> None:
    api = Pages([{"total_count": total, "jobs": []}])

    with pytest.raises(PolicyFailure):
        object_inventory(api, "endpoint", "jobs")


def test_native_count_drift_fails_before_crediting_inventory() -> None:
    api = Pages([{"total_count": 1, "jobs": [1]}, {"total_count": 2, "jobs": []}])

    with pytest.raises(PolicyFailure, match="changed"):
        object_inventory(api, "endpoint", "jobs")


@pytest.mark.parametrize("total", [0, 2])
def test_native_count_rejects_missing_and_extra_entries(total: int) -> None:
    api = Pages(
        [{"total_count": total, "jobs": [1]}, {"total_count": total, "jobs": []}]
    )

    with pytest.raises(PolicyFailure, match="differs"):
        object_inventory(api, "endpoint", "jobs")


@pytest.mark.parametrize("endpoint", ["endpoint?page=9", "endpoint#fragment"])
def test_caller_cannot_inject_pagination_or_fragment(endpoint: str) -> None:
    with pytest.raises(PolicyFailure):
        page_route(endpoint, 1)


@pytest.mark.parametrize("object_shape", [False, True])
def test_endless_inventory_never_returns_partial_evidence(object_shape: bool) -> None:
    value: object = {"total_count": 1000, "jobs": [1]} if object_shape else [1]
    api = Pages([value] * 1000)

    with pytest.raises(PolicyFailure, match="budget"):
        if object_shape:
            object_inventory(api, "endpoint", "jobs")
        else:
            array_inventory(api, "endpoint")
