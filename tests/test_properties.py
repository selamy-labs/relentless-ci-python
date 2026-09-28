"""Properties use a point-set oracle, not a second merging algorithm."""

from hypothesis import given
from hypothesis import strategies as st

from relentless_example import normalize

range_pairs = st.tuples(st.integers(-20, 19), st.integers(1, 20))


def to_interval(pair: tuple[int, int]) -> list[int]:
    start, length = pair
    return [start, start + length]


collections = st.lists(range_pairs.map(to_interval), max_size=30)


def points(value: list[list[int]]) -> set[int]:
    return {point for start, end in value for point in range(start, end)}


@given(collections)
def test_preserves_represented_points(value: list[list[int]]) -> None:
    assert points(normalize(value)) == points(value)


@given(collections)
def test_normalization_is_idempotent(value: list[list[int]]) -> None:
    result = normalize(value)
    assert normalize(result) == result


@given(collections, st.data())
def test_input_order_is_irrelevant(value: list[list[int]], data: st.DataObject) -> None:
    shuffled = data.draw(st.permutations(value))
    assert normalize(shuffled) == normalize(value)


@given(collections)
def test_output_is_canonical(value: list[list[int]]) -> None:
    result = normalize(value)
    assert all(start < end for start, end in result)
    assert all(
        left[1] < right[0] for left, right in zip(result, result[1:], strict=False)
    )
