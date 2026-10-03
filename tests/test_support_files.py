"""Strict support-format inventory, native shell and stale-receipt probes."""

import configparser
import hashlib
import importlib
import json
import runpy
import shutil
import subprocess
from pathlib import Path

import pytest

from quality import support_files
from quality.support_files import child, verify_support


def authored(root: Path, name: str, content: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_complete_inventory_and_strict_formats(tmp_path: Path) -> None:
    files = [
        authored(tmp_path, "quality/config.json", '{"enabled":true}\n'),
        authored(tmp_path, ".hidden/nested.yml", "enabled: true\n"),
        authored(tmp_path, "pyproject.toml", 'name = "example"\n'),
        authored(tmp_path, "mise.lock", "lockfile_version = 3\n"),
        authored(tmp_path, "uv.lock", "version = 1\n"),
        authored(tmp_path, "settings.ini", "[main]\nkey=value\n"),
    ]
    authored(tmp_path, ".venv/ignored.json", "invalid JSON")
    authored(tmp_path, "README.md", "A document\n")
    verify_support(tmp_path)
    verify_support(tmp_path)
    receipt = json.loads((tmp_path / ".quality-results/support-files.json").read_text())
    expected = {
        str(path.relative_to(tmp_path)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in files
    }
    assert receipt == {"files": expected}


def test_equal_but_distinct_root_path_skips_generated_files(tmp_path: Path) -> None:
    authored(tmp_path, "quality/config.json", "{}\n")
    authored(tmp_path, ".venv/ignored.json", "broken JSON")
    discovered = set(support_files.authored(tmp_path, Path(str(tmp_path))))
    assert tmp_path / "quality/config.json" in discovered
    assert tmp_path / ".venv/ignored.json" not in discovered


def test_nested_generated_name_is_not_a_global_exemption(tmp_path: Path) -> None:
    authored(tmp_path, "quality/config.json", "{}\n")
    authored(tmp_path, "quality/.venv/invalid.json", "broken JSON")
    with pytest.raises(ValueError):
        verify_support(tmp_path)


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("quality/bad.json", '{"key":1,"key":2}\n'),
        ("quality/bad.json", '{"key":NaN}\n'),
        ("quality/bad.json", "{broken}\n"),
        ("quality/bad.toml", "key = 1\nkey = 2\n"),
        ("quality/bad.yml", "key: 1\nkey: 2\n"),
        ("quality/bad.yaml", "left: &same 1\nright: *same\n"),
        ("quality/bad.ini", "[main]\nkey=1\nkey=2\n"),
        ("quality/bad.ini", ""),
    ],
)
def test_rejects_bad_format_and_removes_stale_receipt(
    tmp_path: Path, name: str, content: str
) -> None:
    authored(tmp_path, "quality/good.json", "{}\n")
    output = tmp_path / ".quality-results/support-files.json"
    output.parent.mkdir()
    output.write_text("stale")
    authored(tmp_path, name, content)
    with pytest.raises((ValueError, configparser.Error)):
        verify_support(tmp_path)
    assert not output.exists()


def test_empty_inventory_fails(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="inventory must be nonempty"):
        verify_support(tmp_path)


def test_invalid_utf8_fails(tmp_path: Path) -> None:
    path = authored(tmp_path, "quality/config.json", "{}\n")
    path.write_bytes(b"\xff")
    with pytest.raises(UnicodeDecodeError):
        verify_support(tmp_path)


def test_unenrolled_suffix_does_not_parse_as_ini(tmp_path: Path) -> None:
    support_files.parse(tmp_path / "sample.abc", "not an INI document")


def test_lexically_later_source_drift_fails(tmp_path: Path) -> None:
    path = authored(tmp_path, "quality/config.json", "{}\n")
    original = path.read_bytes()
    path.write_text("~")
    with pytest.raises(ValueError, match="changed while being checked"):
        support_files.verify_unchanged({path: original})


def test_authored_symlink_fails(tmp_path: Path) -> None:
    authored(tmp_path, "quality/config.json", "{}\n")
    (tmp_path / "quality/link.json").symlink_to("config.json")
    with pytest.raises(ValueError, match="symlink"):
        verify_support(tmp_path)


def test_unsupported_entry_fails(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported authored support entry"):
        list(child(tmp_path, tmp_path / "missing"))


@pytest.mark.parametrize("parent", [False, True])
def test_redirected_output_fails(tmp_path: Path, parent: bool) -> None:
    authored(tmp_path, "quality/config.json", "{}\n")
    external = tmp_path / "external"
    external.mkdir()
    report = tmp_path / ".quality-results"
    if parent:
        report.symlink_to(external, target_is_directory=True)
    else:
        report.mkdir()
        (report / "support-files.json").symlink_to(external / "receipt")
    with pytest.raises(ValueError, match="symlink"):
        verify_support(tmp_path)


def test_changed_input_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = authored(tmp_path, "quality/config.json", "{}\n")

    def modify(_root: Path, _paths: list[Path]) -> None:
        path.write_text('{"changed":true}\n')

    monkeypatch.setattr(support_files, "shell", modify)
    with pytest.raises(ValueError, match="changed while being checked"):
        verify_support(tmp_path)
    assert not (tmp_path / ".quality-results/support-files.json").exists()


def shell_root(tmp_path: Path) -> None:
    source = Path.cwd()
    for name in ("mise.toml", "mise.lock"):
        shutil.copy2(source / name, tmp_path / name)
    shutil.copy2(
        source / "quality/workflow-commands.json",
        authored(tmp_path, "quality/workflow-commands.json", "{}\n"),
    )


@pytest.mark.parametrize(
    ("content", "passes"),
    [
        ("#!/bin/sh\nprintf '%s\\n' hello\n", True),
        ("#!/bin/sh\necho $UNDEFINED\n", False),
    ],
)
def test_pinned_native_shellcheck(tmp_path: Path, content: str, passes: bool) -> None:
    shell_root(tmp_path)
    authored(tmp_path, "scripts/check.sh", content)
    if not passes:
        authored(tmp_path, ".shellcheckrc", "disable=SC2086\n")
    output = tmp_path / ".quality-results/support-files.json"
    if passes:
        verify_support(tmp_path)
        assert output.is_file()
    else:
        with pytest.raises(subprocess.CalledProcessError):
            verify_support(tmp_path)
        assert not output.exists()


def test_inline_shellcheck_suppression_fails(tmp_path: Path) -> None:
    shell_root(tmp_path)
    authored(
        tmp_path,
        "scripts/check.sh",
        "#!/bin/sh\n# shellcheck disable=SC2086\necho $UNDEFINED\n",
    )
    with pytest.raises(ValueError, match="inline ShellCheck suppression"):
        verify_support(tmp_path)


def test_missing_shell_tool_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shell_root(tmp_path)
    authored(tmp_path, "scripts/check.sh", "#!/bin/sh\nexit 0\n")

    def missing(_root: Path, _args: list[str]) -> str:
        raise FileNotFoundError("shellcheck")

    monkeypatch.setattr(support_files, "tool", missing)
    with pytest.raises(FileNotFoundError):
        verify_support(tmp_path)


def test_wrong_shell_version_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shell_root(tmp_path)
    authored(tmp_path, "scripts/check.sh", "#!/bin/sh\nexit 0\n")

    def wrong_version(_root: Path, _args: list[str]) -> str:
        return "version: 0\n"

    monkeypatch.setattr(support_files, "tool", wrong_version)
    with pytest.raises(ValueError, match="ShellCheck version"):
        verify_support(tmp_path)


def test_main_uses_repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    authored(tmp_path, "quality/config.json", "{}\n")
    monkeypatch.chdir(tmp_path)
    runpy.run_module("quality.support_files_main", run_name="__main__")
    assert callable(importlib.import_module("quality.support_files_main").main)
