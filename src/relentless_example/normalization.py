"""Compute canonical unions without changing the caller's input."""

from relentless_example.validation import intervals


def append_interval(result: list[list[int]], start: int, end: int) -> None:
    """Extend the last union component or begin a disjoint component."""
    if result and start <= result[-1][1]:
        result[-1][1] = max(result[-1][1], end)
        return
    result.append([start, end])


def normalize(value: object) -> list[list[int]]:
    """Return sorted, disjoint, nonadjacent intervals representing the input."""
    result: list[list[int]] = []
    for start, end in sorted(intervals(value)):
        append_interval(result, start, end)
    return result
