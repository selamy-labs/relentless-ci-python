"""Translate JSON streams to the pure interval library."""

import json
import sys
from typing import TextIO

from relentless_example import normalize


def read_document(stdin: TextIO) -> object:
    """Decode JSON and provide a stable syntax-error diagnostic."""
    try:
        value: object = json.load(stdin)
    except json.JSONDecodeError as error:
        raise ValueError("invalid JSON") from error
    return value


def run(stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
    """Normalize a document, emitting no partial success on invalid input."""
    try:
        result = normalize(read_document(stdin))
    except ValueError as error:
        stderr.write(f"error: {error}\n")
        return 2
    stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    return 0


def main() -> int:
    """Run using process standard streams."""
    return run(sys.stdin, sys.stdout, sys.stderr)
