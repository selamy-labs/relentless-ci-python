"""Every collected case remains enrolled; only its execution order changes."""

import pytest

from quality.test_ordering import priority


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Run direct behavioral witnesses before costly native receipt subprocesses."""
    items.sort(key=lambda item: priority(item.nodeid))
