"""Native child process probes for the narrowly bound read-only metadata adapter."""

import json
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from quality.trusted_policy.github_read import GithubAPI, decode_response, endpoint_path
from quality.trusted_policy.review_policy import PolicyFailure

REPO = "owner/repo"
ENDPOINT = "repos/owner/repo/pulls/1/reviews?per_page=100&page=1"


def tool(root: Path, body: str) -> Path:
    path = root / "gh-probe"
    path.write_text(f"#!{sys.executable}\n{body}\n")
    path.chmod(0o700)
    return path


def test_transport_passes_exact_read_only_native_arguments(tmp_path: Path) -> None:
    expected = [
        "api",
        "--hostname",
        "github.com",
        "--method",
        "GET",
        "-H",
        "X-GitHub-Api-Version: 2026-03-10",
        ENDPOINT,
    ]
    executable = tool(
        tmp_path,
        f"import sys\nassert sys.argv[1:] == {expected!r}\nprint('{{\"ok\": true}}')",
    )

    assert GithubAPI(executable, REPO)(ENDPOINT) == {"ok": True}


def test_failed_native_request_never_credits_valid_output(tmp_path: Path) -> None:
    executable = tool(tmp_path, "import sys\nprint('{}')\nsys.exit(1)")

    with pytest.raises(PolicyFailure, match="request failed"):
        GithubAPI(executable, REPO)(ENDPOINT)


def test_negative_native_exit_is_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def terminated(
        command: object, **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        assert kwargs["timeout"] == 30
        return subprocess.CompletedProcess(["gh"], -9, b"{}")

    monkeypatch.setattr(subprocess, "run", terminated)
    with pytest.raises(PolicyFailure, match="request failed"):
        GithubAPI(tool(tmp_path, "print('{}')"), REPO)(ENDPOINT)


def test_native_api_binding_is_immutable() -> None:
    reader = GithubAPI(Path("/bin/true"), REPO)
    field = "repository"
    with pytest.raises(FrozenInstanceError):
        setattr(reader, field, "attacker/repo")


def test_missing_native_cli_fails(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        GithubAPI(tmp_path / "missing-gh", REPO)(ENDPOINT)


def test_relative_cli_path_is_not_resolved_from_candidate_path() -> None:
    with pytest.raises(PolicyFailure, match="absolute"):
        GithubAPI(Path("gh"), REPO)


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://attacker.test/metadata",
        "repos/another/repo/pulls/1",
        "repos/owner/repo-two/pulls/1",
        "repos/owner/repo/pulls/%2e%2e/secrets",
        "repos/owner/repo/pulls/../secrets",
        "repos/owner/repo/pulls/../secrets?per_page=100&page=1",
        "repos/owner/repo/pulls/./1",
        "repos/owner/repo/pulls//1",
        "repos/owner/repo/pulls/1#fragment",
        "repos/owner/repo/pulls/1?per_page=1&page=1",
        "repos/owner/repo/pulls/1?per_page=100&page=0",
    ],
)
def test_bound_transport_rejects_arbitrary_routes(endpoint: str) -> None:
    with pytest.raises(PolicyFailure):
        endpoint_path(endpoint, REPO)


def test_unpaginated_and_native_paginated_routes_are_preserved() -> None:
    assert endpoint_path("repos/owner/repo", REPO) == "repos/owner/repo"
    assert endpoint_path("repos/owner/repo/pulls/1", REPO) == "repos/owner/repo/pulls/1"
    assert endpoint_path(ENDPOINT, REPO) == ENDPOINT


@pytest.mark.parametrize(
    "value", [b"NaN", b"Infinity", b"-Infinity", b'{"id": 1, "id": 2}']
)
def test_nonfinite_numbers_and_duplicate_native_keys_fail(value: bytes) -> None:
    with pytest.raises(PolicyFailure):
        decode_response(value)


@pytest.mark.parametrize("value", [b"", b"{", b"null trailing"])
def test_invalid_native_json_fails(value: bytes) -> None:
    with pytest.raises(json.JSONDecodeError):
        decode_response(value)


def test_native_json_must_be_strict_utf8() -> None:
    with pytest.raises(UnicodeDecodeError):
        decode_response(b'"\xff"')


def test_native_json_response_budget_is_fail_closed() -> None:
    with pytest.raises(PolicyFailure, match="byte budget"):
        decode_response(b" " * (8 * 1024 * 1024 + 1))
