"""Failure evidence survives deletion; unproven cleanup retains original ownership."""

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from quality.mutation_workspace import cleanup_unproven, workspace
from quality.owned_commands import SupervisionUnproven


def test_success_removes_only_its_own_temporary_workspace(tmp_path: Path) -> None:
    (tmp_path / "foreign").write_text("keep")
    with workspace(tmp_path) as target:
        assert target.exists()
        (target / "source.py").write_text("original")
    assert not target.exists()
    assert (tmp_path / "foreign").read_text() == "keep"
    assert not (tmp_path / ".quality-results").exists()


@pytest.mark.parametrize("unproven", [False, True])
def test_failure_preserves_database_sidecars_and_mutated_inputs_before_cleanup(
    tmp_path: Path, unproven: bool
) -> None:
    error: RuntimeError | None = None
    target: Path | None = None
    with pytest.raises(RuntimeError) as caught:
        with workspace(tmp_path) as target:
            (target / "mutation.sqlite").write_bytes(b"partial database")
            (target / "mutation.sqlite-journal").write_bytes(b"journal")
            (target / "source.py").write_text("mutated")
            error = (
                SupervisionUnproven(123, target, "still live")
                if unproven
                else RuntimeError("trial failed")
            )
            raise error
    assert error is not None
    assert target is not None
    assert caught.value is error
    retained = list((tmp_path / ".quality-results").glob("mutation-failure-*"))
    assert len(retained) == 1
    copied = retained[0] / "workspace"
    assert (copied / "mutation.sqlite").read_bytes() == b"partial database"
    assert (copied / "mutation.sqlite-journal").read_bytes() == b"journal"
    assert (copied / "source.py").read_text() == "mutated"
    detail = json.loads((retained[0] / "failure.json").read_text())
    assert detail == {
        "errorType": type(error).__name__,
        "message": str(error),
        "originalWorkspace": str(target),
        "cleanupUnproven": unproven,
        "completeMutationPass": False,
    }
    assert target.exists() is unproven
    if unproven:
        # No process owns this deliberately retained test workspace.
        shutil.rmtree(target)


def test_nested_cleanup_failures_remain_unproven(tmp_path: Path) -> None:
    failure = SupervisionUnproven(123, tmp_path, "unknown")
    assert cleanup_unproven(failure) is True
    assert cleanup_unproven(RuntimeError("ordinary")) is False
    assert (
        cleanup_unproven(ExceptionGroup("ordinary", [RuntimeError("ordinary")]))
        is False
    )
    assert (
        cleanup_unproven(ExceptionGroup("nested", [ExceptionGroup("inner", [failure])]))
        is True
    )


def test_failed_archive_retains_original_evidence(tmp_path: Path) -> None:
    target: Path | None = None
    failure = RuntimeError("trial failed")
    with patch(
        "quality.mutation_workspace.shutil.copytree", side_effect=OSError("disk")
    ):
        with pytest.raises(OSError, match="disk") as caught:
            with workspace(tmp_path) as target:
                (target / "mutation.sqlite").write_bytes(b"partial database")
                raise failure
    assert caught.value.__context__ is failure
    assert target is not None
    assert (target / "mutation.sqlite").read_bytes() == b"partial database"
    shutil.rmtree(target)
