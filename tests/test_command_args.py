"""Qualify command data independently of pipeline execution and registry I/O."""

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from quality.command_args import argument, command

arguments = st.lists(st.text(min_size=1, max_size=40), min_size=1, max_size=8)
invalid_arguments = st.one_of(
    st.none(), st.booleans(), st.integers(), st.just(""), st.lists(st.integers())
)


@given(arguments)
@example(["tool", "two words", "$(literal)", " ", "é"])
def test_command_preserves_argument_values_and_order(value: list[str]) -> None:
    expected = value.copy()

    assert command(value) == expected
    assert value == expected


@given(st.text(min_size=1, max_size=40))
def test_argument_preserves_nonempty_text(value: str) -> None:
    assert argument(value) == value


@given(arguments, invalid_arguments, st.integers(min_value=0, max_value=8))
def test_command_rejects_invalid_member_at_any_position(
    valid: list[str], invalid: object, position: int
) -> None:
    value: list[object] = list(valid)
    value.insert(position % (len(valid) + 1), invalid)

    with pytest.raises(ValueError, match="check arguments must be nonempty strings"):
        command(value)


@pytest.mark.parametrize("value", [None, {}, [], True, "tool", 0, ("tool",)])
def test_command_rejects_values_outside_argument_arrays(value: object) -> None:
    with pytest.raises(
        ValueError, match="each check must be a nonempty argument array"
    ):
        command(value)
