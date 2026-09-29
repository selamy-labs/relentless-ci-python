"""One declarative check list drives local and hosted verification."""

import json
import math
import os
from pathlib import Path
from typing import TypeGuard

from quality.commands import run
from quality.mutation import mutate
from quality.security import verify_security
from quality.source_scope import verify_sources, verify_tracked

MINIMUM_TIMEOUT = 0


def is_array(value: object) -> TypeGuard[list[object]]:
    """Retain unknown element types at a JSON boundary."""
    return isinstance(value, list)


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


def checks(root: Path) -> list[list[str]]:
    """Read the protected command registry; an absent or empty list fails."""
    value: object = json.loads((root / "quality" / "checks.json").read_text())
    if not is_array(value) or not value:
        raise ValueError("check registry must be a nonempty array")
    return [command(item) for item in value]


def verify(root: Path) -> None:
    """Run required definitions in order and stop on the first failed gate."""
    policy: object = json.loads((root / "quality" / "timeout.json").read_text())
    if isinstance(policy, bool) or not isinstance(policy, (int, float)):
        raise ValueError("command timeout must be a positive number")
    if policy <= MINIMUM_TIMEOUT or not math.isfinite(policy):
        raise ValueError("command timeout must be a positive finite number")
    verify_sources(root)
    verify_tracked(root)
    for item in checks(root):
        run(item, root, policy, dict(os.environ))
    verify_security(root, policy)
    mutate(root, policy)
