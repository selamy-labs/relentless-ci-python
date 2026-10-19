"""Label measured test subprocesses with the test function that started them."""

import os
from collections.abc import Generator

import pytest


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(item: pytest.Item) -> Generator[None, object, object]:
    """Inheriting children start coverage through its installed startup hook."""
    os.environ["COVERAGE_PROCESS_START"] = os.environ["MUTATION_COVERAGE_RC"]
    os.environ["MUTATION_TEST_CONTEXT"] = f"{item.nodeid}|subprocess"
    try:
        return (yield)
    finally:
        del os.environ["MUTATION_TEST_CONTEXT"]
        del os.environ["COVERAGE_PROCESS_START"]
