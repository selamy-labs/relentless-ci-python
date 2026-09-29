"""A native strict type consumer exercises the documented PyYAML API adapter."""

import subprocess
import sys
from pathlib import Path


def test_documented_yaml_adapter_accepts_a_strict_native_consumer(
    tmp_path: Path,
) -> None:
    consumer = tmp_path / "yaml_consumer.py"
    consumer.write_text(
        "from collections.abc import Iterator\n"
        "from typing import assert_type\n"
        "import yaml\n"
        "from yaml.nodes import Node\n"
        "from yaml.tokens import Token\n"
        "from quality.runtime_data import api\n"
        "assert_type(api.scan('jobs: {}', yaml.SafeLoader), Iterator[Token])\n"
        "assert_type(api.compose('jobs: {}', yaml.SafeLoader), Node | None)\n"
        "assert_type(api.safe_load('jobs: {}'), object)\n"
    )
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", "--no-incremental", str(consumer)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
