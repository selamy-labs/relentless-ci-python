"""One declarative check list drives local and hosted verification."""

import json
import os
from pathlib import Path

from quality.command_args import command
from quality.commands import run
from quality.deadline import read_deadline
from quality.mutation import mutate
from quality.report_data import is_array
from quality.security import verify_security
from quality.source_scope import verify_sources, verify_tracked
from quality.test_report import prepare_tests, verify_tests


def checks(root: Path) -> list[list[str]]:
    """Read the protected command registry; an absent or empty list fails."""
    value: object = json.loads((root / "quality" / "checks.json").read_text())
    if not is_array(value) or not value:
        raise ValueError("check registry must be a nonempty array")
    return [command(item) for item in value]


def analyze(root: Path) -> float:
    """Run every non-mutation gate in order and stop on the first failure."""
    policy = read_deadline(root / "quality" / "timeout.json")
    sources = verify_sources(root)
    prepare_tests(root)
    verify_tracked(root)
    for item in checks(root):
        run(item, root, policy, dict(os.environ))
    verify_tests(root, sources)
    verify_security(root, policy)
    return policy


def verify(root: Path) -> None:
    """Run the complete local command: every analysis gate, then every mutant."""
    mutate(root, analyze(root))
