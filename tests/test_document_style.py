"""Pinned GFM style, complete inventory and report integrity probes."""

import hashlib
import importlib
import importlib.metadata
import json
import runpy
from pathlib import Path

import mdformat
import pytest

from quality import document_style
from quality.document_style import verify_document_style


def page(root: Path, source: str) -> Path:
    target = root / "README.md"
    target.write_bytes(source.encode("utf-8"))
    return target


def test_native_all_authored_documents() -> None:
    root = Path.cwd()
    verify_document_style(root)
    receipt = json.loads((root / ".quality-results/document-style.json").read_text())
    assert receipt["versions"] == {"mdformat": "1.0.0", "mdformat-gfm": "1.0.0"}
    assert (
        receipt["files"]["README.md"]
        == hashlib.sha256((root / "README.md").read_bytes()).hexdigest()
    )
    assert len(receipt["files"]) >= 10


@pytest.mark.parametrize(
    "source",
    ["\n\n# Header\n", "# Header\n\n\nParagraph\n"],
)
def test_unformatted_markdown_fails_despite_ambient_config(
    tmp_path: Path, source: str
) -> None:
    page(tmp_path, source)
    (tmp_path / ".mdformat.toml").write_text("[style]\nwrap = 1\n")
    with pytest.raises(ValueError, match="style differs"):
        verify_document_style(tmp_path)


def test_wrong_or_missing_formatter_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page(tmp_path, "# Header\n")
    actual = importlib.metadata.version

    def wrong(name: str) -> str:
        return "0" if name == "mdformat-gfm" else actual(name)

    monkeypatch.setattr(importlib.metadata, "version", wrong)
    with pytest.raises(ValueError, match="formatter version"):
        verify_document_style(tmp_path)

    def missing(_name: str) -> str:
        raise ModuleNotFoundError("mdformat")

    monkeypatch.setattr(importlib.metadata, "version", missing)
    with pytest.raises(ModuleNotFoundError):
        verify_document_style(tmp_path)


def test_missing_plugin_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    page(tmp_path, "# Header\n")

    def no_plugin(_text: str, *, extensions: set[str]) -> str:
        assert extensions == {"gfm"}
        raise LookupError("gfm plugin absent")

    monkeypatch.setattr(mdformat, "text", no_plugin)
    with pytest.raises(LookupError):
        verify_document_style(tmp_path)

    monkeypatch.setattr(mdformat, "text", None)
    with pytest.raises(TypeError, match="API is unavailable"):
        verify_document_style(tmp_path)


def test_invalid_utf8_empty_scope_and_symlink(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="inventory is empty"):
        verify_document_style(tmp_path)
    target = page(tmp_path, "# Header\n")
    target.write_bytes(b"\xff")
    with pytest.raises(UnicodeDecodeError):
        verify_document_style(tmp_path)
    target.write_text("# Header\n")
    (tmp_path / "copy.md").symlink_to("README.md")
    with pytest.raises(ValueError, match="symlink"):
        verify_document_style(tmp_path)


@pytest.mark.parametrize("parent", [False, True])
def test_redirected_receipt_fails(tmp_path: Path, parent: bool) -> None:
    page(tmp_path, "# Header\n")
    external = tmp_path / "external"
    external.mkdir()
    output = tmp_path / ".quality-results"
    if parent:
        output.symlink_to(external, target_is_directory=True)
    else:
        output.mkdir()
        (output / "document-style.json").symlink_to(external / "receipt")
    with pytest.raises(ValueError, match="symlink"):
        verify_document_style(tmp_path)


@pytest.mark.parametrize("replacement", ["changed", "!"])
def test_source_drift_removes_stale_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, replacement: str
) -> None:
    target = page(tmp_path, "# Header\n")
    output = tmp_path / ".quality-results/document-style.json"
    output.parent.mkdir()
    output.write_text("stale")

    def drift(_inputs: dict[Path, bytes]) -> None:
        target.write_text(replacement)

    monkeypatch.setattr(document_style, "verify_format", drift)
    with pytest.raises(ValueError, match="changed while style"):
        verify_document_style(tmp_path)
    assert not output.exists()


def test_main_uses_repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    page(tmp_path, "# Header\n")
    monkeypatch.chdir(tmp_path)
    runpy.run_module("quality.document_style_main", run_name="__main__")
    assert callable(importlib.import_module("quality.document_style_main").main)
