"""Current full-scope native receipts must be clean before a success is saved."""

import json
import runpy
import subprocess
from pathlib import Path

import pytest

from quality import workflows
from tests.test_workflow_paths import directory

POLICY = {
    "shellcheck": ["shellcheck", "--version"],
    "shellcheckVersion": "0.11.0",
    "actionlint": ["actionlint"],
    "zizmor": [
        "zizmor",
        "--offline",
        "--pedantic",
        "--no-ignores",
        "--strict-collection",
        "--collect",
        "all",
        "--format",
        "json",
    ],
}


def repository(root: Path) -> Path:
    target = directory(root)
    (target / "first.yml").write_text("name: First\n")
    (target / "second.yaml").write_text("name: Second\n")
    (root / "quality").mkdir()
    (root / "quality/workflow-commands.json").write_text(json.dumps(POLICY))
    output = root / ".quality-results/workflows-security.json"
    return output


@pytest.mark.parametrize("stale", [False, True])
def test_checks_all_files_and_replaces_only_current_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stale: bool
) -> None:
    output = repository(tmp_path)
    if stale:
        output.parent.mkdir()
        output.write_text("stale")
    calls: list[list[str]] = []

    def tool(root: Path, args: list[str]) -> str:
        assert root == tmp_path
        assert not output.exists()
        calls.append(args)
        return "ShellCheck\nversion: 0.11.0\n" if args[0] == "shellcheck" else "[]\n"

    monkeypatch.setattr(workflows, "tool", tool)
    workflows.verify_workflows(tmp_path)
    paths = [
        str((tmp_path / ".github/workflows" / name).resolve())
        for name in ("first.yml", "second.yaml")
    ]
    assert calls == [
        POLICY["shellcheck"],
        ["actionlint", *paths],
        [*POLICY["zizmor"], *paths],
    ]
    assert output.read_bytes() == b"[]\n"
    workflows.verify_workflows(tmp_path)
    assert output.read_bytes() == b"[]\n"


@pytest.mark.parametrize(
    "version",
    [
        "",
        "version: 0.10.0",
        "version: 0.11.00",
        "prefix version: 0.11.0",
        "version: 0.11.0 extra",
    ],
)
def test_wrong_or_partial_version_receipt_stops_audits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, version: str
) -> None:
    output = repository(tmp_path)

    def tool(_root: Path, _args: list[str]) -> str:
        return version

    monkeypatch.setattr(workflows, "tool", tool)
    with pytest.raises(ValueError, match="ShellCheck version receipt"):
        workflows.verify_workflows(tmp_path)
    assert not output.exists()


@pytest.mark.parametrize(
    "report", ["", "broken", "null", "{}", '"[]"', '[{"finding": "unsafe"}]']
)
def test_report_failures_cannot_reuse_stale_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, report: str
) -> None:
    output = repository(tmp_path)
    output.parent.mkdir()
    output.write_text("[]")

    def tool(_root: Path, args: list[str]) -> str:
        return "version: 0.11.0\n" if args[0] == "shellcheck" else report

    monkeypatch.setattr(workflows, "tool", tool)
    with pytest.raises(ValueError):
        workflows.verify_workflows(tmp_path)
    assert not output.exists()


@pytest.mark.parametrize("stage", ["shellcheck", "actionlint", "zizmor"])
def test_native_failures_stop_without_a_success_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    output = repository(tmp_path)
    calls: list[str] = []

    def tool(_root: Path, args: list[str]) -> str:
        calls.append(args[0])
        if args[0] == stage:
            raise subprocess.CalledProcessError(1, args)
        return "version: 0.11.0\n" if args[0] == "shellcheck" else "[]"

    monkeypatch.setattr(workflows, "tool", tool)
    with pytest.raises(subprocess.CalledProcessError):
        workflows.verify_workflows(tmp_path)
    assert calls[-1] == stage
    assert not output.exists()


@pytest.mark.parametrize(
    "value", [None, [], {}, {**POLICY, "unexpected": []}, {"shellcheck": []}]
)
def test_policy_schema_rejects_unknown_and_missing_keys(
    tmp_path: Path, value: object
) -> None:
    repository(tmp_path)
    (tmp_path / "quality/workflow-commands.json").write_text(json.dumps(value))
    with pytest.raises(ValueError):
        workflows.policy(tmp_path)


def test_policy_requires_valid_utf8(tmp_path: Path) -> None:
    repository(tmp_path)
    (tmp_path / "quality/workflow-commands.json").write_bytes(b'{"\xff": []}')
    with pytest.raises(UnicodeDecodeError):
        workflows.policy(tmp_path)


def test_native_tool_is_bounded_locked_without_shell_interpolation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def output(args: list[str], **options: object) -> bytes:
        assert args == [
            "mise",
            "--yes",
            "--locked",
            "exec",
            "--",
            "scanner",
            "argument with spaces",
        ]
        assert options == {"cwd": tmp_path, "timeout": 30, "stdin": subprocess.DEVNULL}
        return b"native\r\n"

    monkeypatch.setattr(subprocess, "check_output", output)
    assert workflows.tool(tmp_path, ["scanner", "argument with spaces"]) == "native\r\n"


def test_invalid_utf8_tool_output_is_not_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def output(*_args: object, **_kw: object) -> bytes:
        return b'"\xff"'

    monkeypatch.setattr(subprocess, "check_output", output)
    with pytest.raises(UnicodeDecodeError):
        workflows.tool(tmp_path, ["scanner"])


def test_entry_uses_current_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    roots: list[Path] = []
    monkeypatch.setattr(workflows, "verify_workflows", roots.append)
    runpy.run_module("quality.workflows_main", run_name="__main__")
    assert roots == [Path.cwd()]
