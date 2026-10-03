"""Native spelling inventory, defects and fail-closed report probes."""

import hashlib
import importlib
import json
import runpy
import shutil
import subprocess
from pathlib import Path

import pytest

from quality import document_spelling
from quality.document_spelling import verify_document_spelling, verify_inventory


def fixture(root: Path, content: str) -> Path:
    path = root / "README.md"
    path.write_bytes(content.encode("utf-8"))
    return path


def native_tools(root: Path) -> None:
    source = Path.cwd()
    for name in ("mise.toml", "mise.lock"):
        shutil.copy2(source / name, root / name)


def test_native_all_authored_documents() -> None:
    root = Path.cwd()
    verify_document_spelling(root)
    receipt = json.loads((root / ".quality-results/document-spelling.json").read_text())
    assert receipt["version"] == "typos-cli 1.50.3"
    assert (
        (root / ".quality-results/document-spelling.json")
        .read_text()
        .startswith('{"files":')
    )
    assert (
        receipt["files"]["README.md"]
        == hashlib.sha256((root / "README.md").read_bytes()).hexdigest()
    )
    assert len(receipt["files"]) >= 10


def test_native_typo_survives_ambient_ignore(tmp_path: Path) -> None:
    native_tools(tmp_path)
    fixture(tmp_path, "Teh obvious error.\n")
    (tmp_path / "_typos.toml").write_text('[default.extend-words]\nTeh = "Teh"\n')
    with pytest.raises(subprocess.CalledProcessError):
        verify_document_spelling(tmp_path)
    assert not (tmp_path / ".quality-results/document-spelling.json").exists()


@pytest.mark.parametrize(
    ("report", "message"),
    [
        ("", "inventory differs"),
        ('{"type":"file","path":"other.md"}', "inventory differs"),
        (
            '{"type":"file","path":"README.md"}\n{"type":"file","path":"README.md"}',
            "inventory differs",
        ),
        ('{"type":"finding","path":"README.md"}', "malformed file"),
        ('{"type":"a","path":"README.md"}', "malformed file"),
        ('{"type":"file","path":42}', "malformed file"),
        ('{"type":"file","path":"README.md","extra":1}', "malformed record"),
        ('{"path":"README.md"}', "malformed record"),
        ("[]", "malformed record"),
    ],
)
def test_invalid_native_inventory(report: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        verify_inventory(report, ["README.md"])


def test_missing_tool_or_wrong_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture(tmp_path, "# Document\n")

    def missing(_root: Path, _args: list[str]) -> str:
        raise FileNotFoundError("typos")

    monkeypatch.setattr(document_spelling, "tool", missing)
    with pytest.raises(FileNotFoundError):
        verify_document_spelling(tmp_path)

    def wrong(_root: Path, _args: list[str]) -> str:
        return "typos-cli 0.0.0\n"

    monkeypatch.setattr(document_spelling, "tool", wrong)
    with pytest.raises(ValueError, match="version"):
        verify_document_spelling(tmp_path)


def test_newer_unexpected_native_version_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture(tmp_path, "# Document\n")

    def newer(_root: Path, args: list[str]) -> str:
        if "--version" in args:
            return "typos-cli 999.0.0\n"
        if "--files" in args:
            return '{"type":"file","path":"README.md"}\n'
        return ""

    monkeypatch.setattr(document_spelling, "tool", newer)
    with pytest.raises(ValueError, match="version"):
        verify_document_spelling(tmp_path)


def test_nonempty_findings_fail_even_on_native_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture(tmp_path, "# Document\n")

    def findings(_root: Path, args: list[str]) -> str:
        if "--version" in args:
            return "typos-cli 1.50.3\n"
        if "--files" in args:
            return '{"type":"file","path":"README.md"}\n'
        return '{"type":"typo"}\n'

    monkeypatch.setattr(document_spelling, "tool", findings)
    with pytest.raises(ValueError, match="findings"):
        verify_document_spelling(tmp_path)


@pytest.mark.parametrize("replacement", ["changed", "!"])
def test_source_drift_invalidates_stale_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, replacement: str
) -> None:
    page = fixture(tmp_path, "# Document\n")
    report = tmp_path / ".quality-results/document-spelling.json"
    report.parent.mkdir()
    report.write_text("stale")

    def changed(_root: Path, args: list[str]) -> str:
        if "--version" in args:
            return "typos-cli 1.50.3\n"
        if "--files" in args:
            return '{"type":"file","path":"README.md"}\n'
        page.write_text(replacement)
        return ""

    monkeypatch.setattr(document_spelling, "tool", changed)
    with pytest.raises(ValueError, match="changed while spelling"):
        verify_document_spelling(tmp_path)
    assert not report.exists()


@pytest.mark.parametrize("parent", [False, True])
def test_redirected_receipt_fails(tmp_path: Path, parent: bool) -> None:
    fixture(tmp_path, "# Document\n")
    external = tmp_path / "external"
    external.mkdir()
    report = tmp_path / ".quality-results"
    if parent:
        report.symlink_to(external, target_is_directory=True)
    else:
        report.mkdir()
        (report / "document-spelling.json").symlink_to(external / "receipt")
    with pytest.raises(ValueError, match="symlink"):
        verify_document_spelling(tmp_path)


def test_empty_and_linked_markdown_fail(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="inventory is empty"):
        verify_document_spelling(tmp_path)
    fixture(tmp_path, "# Document\n")
    (tmp_path / "copy.md").symlink_to("README.md")
    with pytest.raises(ValueError, match="symlink"):
        verify_document_spelling(tmp_path)


def test_main_uses_repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    native_tools(tmp_path)
    fixture(tmp_path, "# Document\n")
    monkeypatch.chdir(tmp_path)
    runpy.run_module("quality.document_spelling_main", run_name="__main__")
    assert callable(importlib.import_module("quality.document_spelling_main").main)
