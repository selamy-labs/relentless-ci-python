"""The protected registry invokes the actual duplication entrypoint."""

import runpy
from pathlib import Path
from unittest.mock import patch


def test_duplication_module_entrypoint() -> None:
    with patch("quality.duplication.verify_duplication") as verify:
        path = Path(__file__).parents[1] / "quality" / "duplication_main.py"
        runpy.run_path(str(path), run_name="__main__")
    verify.assert_called_once_with(Path.cwd())


def test_duplication_callable_entrypoint() -> None:
    from quality.duplication_main import main

    with patch("quality.duplication_main.verify_duplication") as verify:
        main()
    verify.assert_called_once_with(Path.cwd())
