"""Native Markdown link, heading, inventory and stale-receipt probes."""

import hashlib
import importlib
import json
import runpy
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from markdown_it import MarkdownIt
from markdown_it.token import Token

from quality import document_links
from quality.document_links import checked_target, document, verify_document_links


def write(root: Path, name: str, content: str) -> Path:
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content.encode("utf-8"))
    return target


def test_native_readme_and_source_bound_receipt() -> None:
    root = Path.cwd()
    verify_document_links(root)
    receipt = json.loads((root / ".quality-results/document-links.json").read_text())
    assert (
        receipt["files"]["README.md"]
        == hashlib.sha256((root / "README.md").read_bytes()).hexdigest()
    )
    assert "https://mise.jdx.dev/" in receipt["external"]
    assert len(receipt["files"]) >= 10


def test_local_links_images_fragments_and_duplicate_headings(tmp_path: Path) -> None:
    page = write(tmp_path, "docs/page.md", "# Section!\n" * 5)
    write(
        tmp_path,
        "README.md",
        "[one](docs/page.md#section)\n\n[two](docs/page.md#section-1)\n\n[three](docs/page.md#section-2)\n\n[five](docs/page.md#section-4)\n\n![image](logo.png)\n",
    )
    write(tmp_path, "logo.png", "image")
    verify_document_links(tmp_path)
    assert document(page.read_text()).anchors == {
        "section",
        "section-1",
        "section-2",
        "section-3",
        "section-4",
    }
    assert document("no links").links == []
    assert (
        checked_target(tmp_path, tmp_path / "README.md", "", {tmp_path / "README.md"})
        is None
    )


def test_document_record_rejects_rebinding() -> None:
    parsed = document("# Section\n")
    field = "links"
    with pytest.raises(FrozenInstanceError):
        setattr(parsed, field, [])


@pytest.mark.parametrize(
    ("href", "message"),
    [
        ("missing.md", "target is missing"),
        ("../outside.md", "target is missing"),
        ("https://host/doc", ""),
        ("ftp://host/doc", "unsupported"),
        ("ftp:docs/page.md", "unsupported"),
        ("docs/page.md?query=1", "unsupported"),
        ("docs/page.md#missing", "heading is missing"),
        ("logo.png#heading", "requires Markdown"),
        ("logo.aa#present", "requires Markdown"),
    ],
)
def test_link_resolution_fail_closed(tmp_path: Path, href: str, message: str) -> None:
    source = write(tmp_path, "README.md", "# Readme\n")
    page = write(tmp_path, "docs/page.md", "# Present\n")
    image = write(tmp_path, "logo.png", "image")
    earlier = write(tmp_path, "logo.aa", "# Present\n")
    if href.startswith("https:"):
        assert (
            checked_target(tmp_path, source, href, {source, page, image, earlier})
            == href
        )
    else:
        with pytest.raises(ValueError, match=message):
            checked_target(tmp_path, source, href, {source, page, image, earlier})


def test_percent_encoded_local_path(tmp_path: Path) -> None:
    source = write(tmp_path, "README.md", "[named](docs/a%20b.md#hello-world)\n")
    page = write(tmp_path, "docs/a b.md", "# Hello World\n")
    assert (
        checked_target(tmp_path, source, "docs/a%20b.md#hello-world", {source, page})
        is None
    )


def test_missing_markdown_or_invalid_utf8(tmp_path: Path) -> None:
    write(tmp_path, "LICENSE", "MIT")
    with pytest.raises(ValueError, match="inventory is empty"):
        verify_document_links(tmp_path)
    page = write(tmp_path, "README.md", "# Valid\n")
    page.write_bytes(b"\xff")
    with pytest.raises(UnicodeDecodeError):
        verify_document_links(tmp_path)


@pytest.mark.parametrize("parent", [False, True])
def test_redirected_receipt_fails(tmp_path: Path, parent: bool) -> None:
    write(tmp_path, "README.md", "# Valid\n")
    external = tmp_path / "external"
    external.mkdir()
    report = tmp_path / ".quality-results"
    if parent:
        report.symlink_to(external, target_is_directory=True)
    else:
        report.mkdir()
        (report / "document-links.json").symlink_to(external / "receipt")
    with pytest.raises(ValueError, match="symlink"):
        verify_document_links(tmp_path)


def test_changed_source_removes_stale_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = write(tmp_path, "README.md", "[link](page.md)\n")
    write(tmp_path, "page.md", "# Original\n")
    output = tmp_path / ".quality-results/document-links.json"
    output.parent.mkdir()
    output.write_text("stale")
    original = document_links.checked_target

    def changed(root: Path, source: Path, href: str, files: set[Path]) -> str | None:
        page.write_text("changed")
        return original(root, source, href, files)

    monkeypatch.setattr(document_links, "checked_target", changed)
    with pytest.raises(ValueError, match="changed while being checked"):
        verify_document_links(tmp_path)
    assert not output.exists()


def test_lexically_smaller_source_drift_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = write(tmp_path, "README.md", "[link](page.md)\n")
    write(tmp_path, "page.md", "# Original\n")
    original = document_links.checked_target

    def changed(root: Path, source: Path, href: str, files: set[Path]) -> str | None:
        page.write_text("A")
        return original(root, source, href, files)

    monkeypatch.setattr(document_links, "checked_target", changed)
    with pytest.raises(ValueError, match="changed while being checked"):
        verify_document_links(tmp_path)


def test_symlinked_authored_file_fails(tmp_path: Path) -> None:
    write(tmp_path, "README.md", "# Valid\n")
    (tmp_path / "copy.md").symlink_to("README.md")
    with pytest.raises(ValueError, match="symlink"):
        verify_document_links(tmp_path)


def test_nonstring_parser_destination_fails() -> None:
    link = Token("link_open", "a", 1)
    link.attrSet("href", 1)
    inline = Token("inline", "", 0)
    inline.children = [link]
    with pytest.raises(ValueError, match="must be a string"):
        document_links.child_links(inline)
    tokens = MarkdownIt("commonmark").parse("![alt](image.png)")
    assert "image.png" in document_links.child_links(tokens[1])


@pytest.mark.parametrize("token_type", ["A", "z"])
def test_non_inline_parser_token_cannot_supply_links(
    monkeypatch: pytest.MonkeyPatch, token_type: str
) -> None:
    link = Token("link_open", "a", 1)
    link.attrSet("href", "ignored.md")
    non_inline = Token(token_type, "", 0)
    non_inline.children = [link]

    def parsed(*_args: object) -> list[Token]:
        return [non_inline]

    monkeypatch.setattr(MarkdownIt, "parse", parsed)
    assert document("ignored").links == []


def test_negative_repeat_counter_cannot_become_first_heading() -> None:
    anchors: set[str] = set()
    repeats = {"section": -1}
    document_links.remember_heading(anchors, repeats, "Section")
    assert anchors == {"section--1"}
    assert repeats == {"section": 0}


def test_link_receipt_has_canonical_key_order(tmp_path: Path) -> None:
    write(tmp_path, "README.md", "# Heading\n")
    verify_document_links(tmp_path)
    receipt = (tmp_path / ".quality-results/document-links.json").read_text()
    assert receipt.startswith('{"external":')


def test_main_uses_repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write(tmp_path, "README.md", "# Valid\n")
    monkeypatch.chdir(tmp_path)
    runpy.run_module("quality.document_links_main", run_name="__main__")
    assert callable(importlib.import_module("quality.document_links_main").main)
