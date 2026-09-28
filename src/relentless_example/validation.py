"""Validate the public interval boundary without trusting caller types."""

from typing import TypeGuard

LIMIT = 1_000_000


def is_array(value: object) -> TypeGuard[list[object]]:
    """Recognize a JSON-style array while retaining unknown element types."""
    return isinstance(value, list)


def endpoint(value: object) -> int:
    """Accept finite integral numbers within the portable domain."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("endpoints must be integers")
    if not -LIMIT <= value <= LIMIT:
        raise ValueError("endpoints must be between -1000000 and 1000000")
    if int(value) != value:
        raise ValueError("endpoints must be integers")
    return int(value)


def interval(value: object) -> tuple[int, int]:
    """Validate one nonempty half-open interval."""
    if not is_array(value) or len(value) != 2:
        raise ValueError("each interval must contain exactly two endpoints")
    start, end = (endpoint(item) for item in value)
    if start >= end:
        raise ValueError("interval start must be less than end")
    return start, end


def intervals(value: object) -> list[tuple[int, int]]:
    """Validate the entire collection before computing an output."""
    if not is_array(value):
        raise ValueError("input must be an array of intervals")
    return [interval(item) for item in value]
