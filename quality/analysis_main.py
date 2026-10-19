"""Hosted extra runtimes: every gate of quality.verify except mutation."""

from pathlib import Path

from quality.pipeline import analyze

analyze(Path.cwd())
