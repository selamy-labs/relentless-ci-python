"""Parse command argument data without importing verification orchestration."""

from quality.report_data import is_array


def command(value: object) -> list[str]:
    """Only nonempty argument arrays are executable check definitions."""
    if not is_array(value) or not value:
        raise ValueError("each check must be a nonempty argument array")
    return [argument(item) for item in value]


def argument(value: object) -> str:
    """Avoid implicit coercion and never interpolate command text into a shell."""
    if not isinstance(value, str) or not value:
        raise ValueError("check arguments must be nonempty strings")
    return value
