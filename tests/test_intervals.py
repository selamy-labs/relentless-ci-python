"""Examples describe the public contract independently of the implementation."""

import pytest

from relentless_example import normalize


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ([], []),
        ([[1, 2]], [[1, 2]]),
        ([[5, 8], [1, 3], [2, 6]], [[1, 8]]),
        ([[1, 3], [3, 5]], [[1, 5]]),
        ([[1, 3], [4, 5]], [[1, 3], [4, 5]]),
        ([[1, 2], [5, 7], [6, 9]], [[1, 2], [5, 9]]),
        ([[0, 1], [10, 20], [12, 15]], [[0, 1], [10, 20]]),
        ([[1, 8], [2, 3], [1, 8]], [[1, 8]]),
        ([[-1_000_000, 1_000_000]], [[-1_000_000, 1_000_000]]),
        ([[1.0, 2.0]], [[1, 2]]),
    ],
)
def test_normalizes_ranges(value: object, expected: list[list[int]]) -> None:
    assert normalize(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        {},
        "[]",
        [None],
        [[1]],
        [[1, 2, 3]],
        [[1, 1]],
        [[2, 1]],
        [[True, 2]],
        [[0, False]],
        [["1", 2]],
        [[0, None]],
        [[0.5, 2]],
        [[-0.5, 2]],
        [[0, float("inf")]],
        [[float("nan"), 2]],
        [[-1_000_001, 0]],
        [[0, 1_000_001]],
    ],
)
def test_rejects_invalid_ranges(value: object) -> None:
    with pytest.raises(ValueError):
        normalize(value)


@pytest.mark.parametrize("value", [[[]], [[1]], [[1, 2, 3]]])
def test_invalid_pair_shape_has_actionable_error(value: object) -> None:
    with pytest.raises(
        ValueError, match="^each interval must contain exactly two endpoints$"
    ):
        normalize(value)


def test_does_not_mutate_input() -> None:
    value = [[3, 5], [1, 4]]
    assert normalize(value) == [[1, 5]]
    assert value == [[3, 5], [1, 4]]
