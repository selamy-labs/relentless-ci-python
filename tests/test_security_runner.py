"""Native scanner protocol, stale-output and failure-propagation probes."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from quality import security


def repository(root: Path) -> None:
    (root / "src").mkdir()
    (root / "src" / "example.py").write_text("value = 1\n")
    (root / "uv.lock").write_text('[[package]]\nname = "example"\nversion = "1.0"\n')


def report_path(arguments: list[str]) -> Path:
    for flag in ("--report-path", "--output-file", "--output"):
        if flag in arguments:
            return Path(arguments[arguments.index(flag) + 1])
    raise AssertionError("missing required report option")


def report(arguments: list[str], root: Path) -> object:
    if arguments[0] == "gitleaks":
        return []
    if arguments[0] == "osv-scanner":
        return {
            "results": [
                {
                    "source": {"type": "lockfile", "path": str(root / "uv.lock")},
                    "packages": [
                        {
                            "package": {
                                "name": "example",
                                "version": "1.0",
                                "ecosystem": "PyPI",
                            }
                        }
                    ],
                }
            ]
        }
    return {
        "results": [],
        "errors": [],
        "skipped_rules": [],
        "paths": {"scanned": ["src/example.py"]},
    }


def test_all_required_scans_use_fresh_reports_and_strict_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository(tmp_path)
    output = tmp_path / ".quality-results"
    output.mkdir()
    for name in security.REPORTS:
        (output / name).write_text("stale")
    received: list[list[str]] = []

    def tool(arguments: list[str], root: Path, timeout: float) -> None:
        assert root == tmp_path
        assert timeout == 5
        destination = report_path(arguments)
        assert not destination.exists()
        destination.write_text(json.dumps(report(arguments, root)))
        received.append(arguments)

    monkeypatch.setattr(security, "tool", tool)
    security.verify_security(tmp_path, 5)
    assert [arguments[:2] for arguments in received] == [
        ["gitleaks", "git"],
        ["gitleaks", "dir"],
        ["osv-scanner", "scan"],
        ["opengrep", "scan"],
    ]
    history, tree, audit, static = received
    assert history[2] == tree[2] == "."
    assert "--ignore-gitleaks-allow" in history
    assert "--redact" in tree
    assert (
        history[history.index("--gitleaks-ignore-path") + 1]
        == "quality/gitleaks.ignore"
    )
    assert audit[audit.index("--lockfile") + 1] == str(tmp_path / "uv.lock")
    assert "--all-vulns" in audit
    assert "--all-packages" in audit
    assert audit[audit.index("--config") + 1] == "quality/osv-scanner.toml"
    assert "--strict" in static
    assert "--error" in static
    assert "--disable-nosem" in static
    assert "--no-git-ignore" in static
    assert "--x-ignore-semgrepignore-files" in static
    assert "--taint-intrafile" in static
    assert "--disable-version-check" in static
    assert static[static.index("--max-target-bytes") + 1] == "0"
    assert static[-1] == "src/example.py"


def test_missing_new_report_cannot_reuse_old_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository(tmp_path)
    output = tmp_path / ".quality-results"
    output.mkdir()
    (output / "history-secrets.json").write_text("[]")

    def success_without_report(*_arguments: object) -> None:
        return

    monkeypatch.setattr(security, "tool", success_without_report)
    with pytest.raises(FileNotFoundError):
        security.verify_security(tmp_path, 5)


def test_failed_tool_stops_further_scans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository(tmp_path)
    received: list[list[str]] = []

    def failure(arguments: list[str], root: Path, timeout: float) -> None:
        received.append(arguments)
        raise subprocess.CalledProcessError(127, arguments)

    monkeypatch.setattr(security, "tool", failure)
    with pytest.raises(subprocess.CalledProcessError):
        security.verify_security(tmp_path, 5)
    assert len(received) == 1


def test_findings_cannot_pass_even_after_a_zero_tool_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository(tmp_path)

    def findings(arguments: list[str], root: Path, timeout: float) -> None:
        report_path(arguments).write_text('[{"RuleID": "a-secret"}]')

    monkeypatch.setattr(security, "tool", findings)
    with pytest.raises(ValueError, match="reported"):
        security.verify_security(tmp_path, 5)


def test_tool_runs_locked_without_a_shell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    received: list[list[str]] = []

    def run(
        arguments: list[str], root: Path, timeout: float, env: dict[str, str]
    ) -> None:
        assert root == tmp_path
        assert timeout == 5
        assert env == dict(os.environ)
        received.append(arguments)

    monkeypatch.setattr(security, "run", run)
    security.tool(["scanner", "an argument with spaces"], tmp_path, 5)
    assert received == [
        [
            "mise",
            "--yes",
            "--locked",
            "exec",
            "--",
            "scanner",
            "an argument with spaces",
        ]
    ]
