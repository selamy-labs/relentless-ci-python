"""Preserve failing mutation evidence before deletion; retain uncertain live owners."""

import json
import shutil
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from tempfile import mkdtemp
from typing import cast

from quality.owned_commands import SupervisionUnproven


def cleanup_unproven(error: BaseException) -> bool:
    if isinstance(error, SupervisionUnproven):
        return True
    if isinstance(error, BaseExceptionGroup):
        group = cast(BaseExceptionGroup[BaseException], error)
        return any(cleanup_unproven(item) for item in group.exceptions)
    return False


def preserve_failure(root: Path, target: Path, error: BaseException) -> None:
    output = root / ".quality-results"
    output.mkdir(exist_ok=True)
    retained = Path(mkdtemp(prefix="mutation-failure-", dir=output))
    shutil.copytree(target, retained / "workspace")
    (retained / "failure.json").write_text(
        json.dumps(
            {
                "errorType": type(error).__name__,
                "message": str(error),
                "originalWorkspace": str(target),
                "cleanupUnproven": cleanup_unproven(error),
                "completeMutationPass": False,
            }
        ),
        encoding="utf-8",
    )


def remove_workspace(target: Path, retain: bool) -> None:
    """Leave uncertain owners and failed archives intact."""
    if retain:
        return
    shutil.rmtree(target)


@contextmanager
def workspace(root: Path) -> Generator[Path]:
    target = Path(mkdtemp(prefix="relentless-mutation-"))
    retain = False
    try:
        yield target
    except BaseException as error:
        retain = True
        preserve_failure(root, target, error)
        retain = cleanup_unproven(error)
        raise
    finally:
        remove_workspace(target, retain)
