"""Keep costly native receipt probes after the tests that usually kill defects."""

CLEANUP_PROBE = (
    "tests/test_process_cleanup.py::"
    "test_native_timeout_terminates_descendant_before_it_writes"
)


def priority(node: str) -> tuple[bool, str]:
    """Change execution order without filtering or changing collected identities."""
    native_receipt = node.split("::")[0] in (
        "tests/test_pytest_integrity.py",
        "tests/test_owned_process_native.py",
        "tests/test_owned_caller_native.py",
    )
    native_cleanup = node == CLEANUP_PROBE
    return native_receipt or native_cleanup, node
