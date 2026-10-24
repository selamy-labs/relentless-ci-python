"""Pristine validation shard entry point runs in its own copied checkout."""

from pathlib import Path

from quality.mutation_pristine import run_shard

run_shard(Path.cwd())
