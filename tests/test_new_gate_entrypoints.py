"""Every new quality command runs only when used as a Python entry point."""

import importlib
import runpy
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("module", "dependency", "function"),
    [
        ("duplication", "duplication", "verify_duplication"),
        ("incomplete", "incomplete", "verify_incomplete"),
        ("document_links", "document_links", "verify_document_links"),
        ("document_spelling", "document_spelling", "verify_document_spelling"),
        ("document_style", "document_style", "verify_document_style"),
        ("readme_example", "readme_example", "verify_readme_example"),
        ("support_files", "support_files", "verify_support"),
        ("repository_hygiene", "repository_hygiene", "verify_repository"),
    ],
)
def test_new_gate_entrypoint_dispatch(
    monkeypatch: pytest.MonkeyPatch, module: str, dependency: str, function: str
) -> None:
    called: list[Path] = []

    def record(root: Path) -> None:
        called.append(root)

    target = importlib.import_module(f"quality.{dependency}")
    monkeypatch.setattr(target, function, record)
    name = f"quality.{module}_main"
    monkeypatch.delitem(sys.modules, name, raising=False)
    for run_name in ("A", "z", name):
        runpy.run_module(name, run_name=run_name)
        assert called == []
    runpy.run_module(name, run_name="__main__")
    assert called == [Path.cwd()]
