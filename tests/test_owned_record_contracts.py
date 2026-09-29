"""Ownership and completion records cannot be rebound after they are captured."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from quality.owned_process import Cleanup, Completion
from tests.test_mutation_services import instance


@pytest.mark.parametrize("record_name", ["cleanup", "completion", "command", "worker"])
def test_captured_record_fields_cannot_be_rebound(
    tmp_path: Path, record_name: str
) -> None:
    worker = instance(tmp_path)
    records: dict[str, tuple[object, str, object]] = {
        "cleanup": (Cleanup([], []), "killed", [257]),
        "completion": (Completion(0, False, Cleanup([], [])), "returncode", 1),
        "command": (worker.owned, "nonce", "replaced"),
        "worker": (worker, "nonce", "replaced"),
    }
    record, field, replacement = records[record_name]
    captured = getattr(record, field)

    with pytest.raises(FrozenInstanceError):
        setattr(record, field, replacement)

    assert getattr(record, field) is captured
