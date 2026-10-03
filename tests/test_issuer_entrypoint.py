"""Protected entrypoint must compile one native workflow and fixed matrix."""

import json
import runpy
import shutil
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from quality.trusted_policy import issuer_entrypoint
from quality.trusted_policy.check_publisher import Target
from quality.trusted_policy.issuer_entrypoint import (
    app_id,
    event_payload,
    executable,
    main,
    required_names,
    reviewed_policy,
)
from quality.trusted_policy.review_policy import PolicyFailure
from tests.test_issuer_resolution import BASE, HEAD, ROOT, NativeAPI
from tests.test_metadata_collector import NativeAPI as ListNativeAPI
from tests.test_trusted_issuer import comment_event
from tests.test_trusted_issuer import native_source as approved_source


def native_source() -> dict[str, object]:
    return {
        ROOT: {"id": 17, "full_name": "owner/repo", "default_branch": "main"},
        ROOT
        + "/branches/main": {
            "name": "main",
            "protected": True,
            "commit": {"sha": BASE},
        },
        ROOT
        + "/actions/workflows/ci.yml": {
            "id": 23,
            "name": "Relentless CI",
            "path": ".github/workflows/ci.yml",
            "state": "active",
        },
    }


@pytest.mark.parametrize("profile,count", [("python", 17), ("typescript", 13)])
def test_fixed_complete_matrix(profile: str, count: int) -> None:
    names = required_names(profile)
    assert len(names) == count
    assert "Relentless CI gate" in names
    assert ("Full analysis (Python 3.14)" in names) == (profile == "python")
    assert ("Full analysis (Node 26)" in names) == (profile == "typescript")
    assert ("Installed behavior (windows-2025, Python 3.11)" in names) == (
        profile == "python"
    )
    assert ("Installed behavior (macos-15, Node 24)" in names) == (
        profile == "typescript"
    )


def test_native_workflow_and_protected_base_compile_reviewed_policy() -> None:
    api = NativeAPI(native_source())
    policy = reviewed_policy(api, "owner/repo", BASE, "python")
    assert (policy.repository_id, policy.base, policy.workflow_id) == (17, BASE, 23)
    assert policy.required_names == required_names("python")
    assert api.routes == [
        ROOT,
        ROOT + "/branches/main",
        ROOT + "/actions/workflows/ci.yml",
    ]


@pytest.mark.parametrize(
    "route,key,value",
    [
        (ROOT, "full_name", "other/repo"),
        (ROOT, "default_branch", "trunk"),
        (ROOT + "/branches/main", "protected", False),
        (ROOT + "/branches/main", "commit", {"sha": HEAD}),
        (ROOT + "/actions/workflows/ci.yml", "path", "ci-other.yml"),
        (ROOT + "/actions/workflows/ci.yml", "state", "disabled_manually"),
        (ROOT + "/actions/workflows/ci.yml", "name", "Other CI"),
    ],
)
def test_changed_native_identity_cannot_compile(
    route: str, key: str, value: object
) -> None:
    values = native_source()
    changed = deepcopy(values[route])
    assert isinstance(changed, dict)
    changed[key] = value
    values[route] = changed
    with pytest.raises(PolicyFailure):
        reviewed_policy(NativeAPI(values), "owner/repo", BASE, "python")


def test_unknown_profile_cannot_supply_a_smaller_matrix() -> None:
    with pytest.raises(PolicyFailure, match="unknown"):
        required_names("smoke")


def test_event_file_rejects_duplicate_keys_and_accepts_native_json(
    tmp_path: Path,
) -> None:
    path = tmp_path / "event.json"
    path.write_text(json.dumps({"action": "completed", "repository": {"id": 17}}))
    assert event_payload(path) == {"action": "completed", "repository": {"id": 17}}
    path.write_text('{"action":"created","action":"deleted"}')
    with pytest.raises(PolicyFailure, match="duplicate"):
        event_payload(path)


@pytest.mark.parametrize("value", ["0", "-2", "+2", "two", "2.0"])
def test_app_id_requires_exact_positive_decimal(value: str) -> None:
    with pytest.raises(PolicyFailure):
        app_id(value)
    assert app_id("41") == 41


def test_event_file_must_be_absolute_present_and_bounded(tmp_path: Path) -> None:
    with pytest.raises(PolicyFailure, match="missing or too large"):
        event_payload(Path("event.json"))
    with pytest.raises(PolicyFailure, match="missing or too large"):
        event_payload(tmp_path / "missing.json")
    large = tmp_path / "large.json"
    with large.open("wb") as target:
        target.truncate(8 * 1024 * 1024 + 1)
    with pytest.raises(PolicyFailure, match="missing or too large"):
        event_payload(large)


def test_github_cli_must_resolve_to_absolute_executable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_cli(_: str) -> None:
        return None

    def relative_cli(_: str) -> str:
        return "gh"

    def absolute_cli(_: str) -> str:
        return "/usr/bin/gh"

    monkeypatch.setattr(shutil, "which", missing_cli)
    with pytest.raises(PolicyFailure, match="missing"):
        executable()
    monkeypatch.setattr(shutil, "which", relative_cli)
    with pytest.raises(PolicyFailure, match="not absolute"):
        executable()
    monkeypatch.setattr(shutil, "which", absolute_cli)
    assert executable() == Path("/usr/bin/gh")


class FakeChecks:
    decisions: list[tuple[str, bool]] = []

    def __init__(self, cli: Path, target: Target) -> None:
        assert cli == Path("/usr/bin/gh")
        assert target == Target("owner/repo", 41)

    def create(self, head: str, passed: bool) -> int:
        self.decisions.append((head, passed))
        return 91


def configured_entrypoint(monkeypatch: pytest.MonkeyPatch, event_file: Path) -> None:
    values = approved_source()
    repository = values[ROOT][0]
    assert isinstance(repository, dict)
    repository["default_branch"] = "main"
    values[ROOT + "/actions/workflows/ci.yml"] = [
        {
            "id": 2,
            "name": "Relentless CI",
            "path": ".github/workflows/ci.yml",
            "state": "active",
        }
    ]

    def native_api(*_args: object) -> ListNativeAPI:
        return ListNativeAPI(values)

    monkeypatch.setattr(issuer_entrypoint, "GithubAPI", native_api)
    monkeypatch.setattr(issuer_entrypoint, "GithubChecks", FakeChecks)
    monkeypatch.setattr(issuer_entrypoint, "executable", lambda: Path("/usr/bin/gh"))
    monkeypatch.setattr(sys, "argv", ["issuer_entrypoint.py", "python"])
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_SHA", BASE)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "issue_comment")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
    monkeypatch.setenv("RELENTLESS_POLICY_APP_ID", "41")


def test_entrypoint_uses_protected_policy_and_app_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(comment_event()))
    configured_entrypoint(monkeypatch, event_file)
    monkeypatch.setenv("GH_TOKEN", "test-token")
    FakeChecks.decisions = []
    assert main() == 91
    assert FakeChecks.decisions == [(HEAD, False)]


def test_entrypoint_requires_installation_token_before_native_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(comment_event()))
    configured_entrypoint(monkeypatch, event_file)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    with pytest.raises(PolicyFailure, match="installation token"):
        main()


def test_module_entry_requires_one_protected_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["issuer_entrypoint.py"])
    with pytest.raises(PolicyFailure, match="one protected template profile"):
        runpy.run_module("quality.trusted_policy.issuer_main", run_name="__main__")


@pytest.mark.parametrize(
    "route,key,values",
    [
        (ROOT, "full_name", ["alpha/repo", "zulu/repo"]),
        (ROOT + "/branches/main", "commit", [{"sha": "0" * 40}, {"sha": "f" * 40}]),
        (ROOT + "/actions/workflows/ci.yml", "name", ["Alpha CI", "Zulu CI"]),
        (
            ROOT + "/actions/workflows/ci.yml",
            "path",
            [".github/workflows/a.yml", ".github/workflows/z.yml"],
        ),
    ],
)
def test_protected_metadata_rejects_both_ordered_mismatch_directions(
    route: str, key: str, values: list[object]
) -> None:
    for alternate in values:
        source = native_source()
        changed = deepcopy(source[route])
        assert isinstance(changed, dict)
        changed[key] = alternate
        source[route] = changed
        with pytest.raises(PolicyFailure):
            reviewed_policy(NativeAPI(source), "owner/repo", BASE, "python")


def test_protected_flag_rejects_truthy_non_boolean() -> None:
    source = native_source()
    route = ROOT + "/branches/main"
    branch = deepcopy(source[route])
    assert isinstance(branch, dict)
    branch["protected"] = 1
    source[route] = branch
    with pytest.raises(PolicyFailure):
        reviewed_policy(NativeAPI(source), "owner/repo", BASE, "python")


@pytest.mark.parametrize("size", [7 * 1024 * 1024 + 1, 8 * 1024 * 1024])
def test_event_file_accepts_valid_json_at_large_boundary(
    tmp_path: Path, size: int
) -> None:
    path = tmp_path / "bounded-event.json"
    empty = json.dumps({"payload": ""}).encode()
    body = json.dumps({"payload": "x" * (size - len(empty))}).encode()
    assert len(body) == size
    path.write_bytes(body)
    assert event_payload(path) == {"payload": "x" * (size - len(empty))}


def test_module_entry_rejects_extra_untrusted_profile_argument(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["issuer_entrypoint.py", "python", "typescript"])
    with pytest.raises(PolicyFailure, match="one protected template profile"):
        runpy.run_module("quality.trusted_policy.issuer_main", run_name="__main__")
