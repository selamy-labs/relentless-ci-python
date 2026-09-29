"""Dated support and exact runtime declarations fail closed at their boundaries."""

import hashlib
import json
import runpy
from datetime import date
from pathlib import Path

import pytest
import yaml

from quality.runtime_support import (
    branches,
    calendar,
    end_of_support,
    require_branch,
    verify_metadata,
    verify_runtimes,
)

TODAY = date(2026, 9, 29)
VERSIONS = ["3.11", "3.12", "3.13", "3.14"]


def policy() -> dict[str, object]:
    return {
        "source": "https://raw.githubusercontent.com/python/devguide/"
        + "a" * 40
        + "/versions.rst",
        "releaseCycleSource": "https://peps.python.org/api/release-cycle.json",
        "snapshotSha256": "unused",
        "reviewedOn": "2026-09-29",
        "reviewBy": "2026-12-28",
        "versions": VERSIONS,
    }


def release() -> dict[str, object]:
    return {
        "branch": "3.11",
        "status": "security",
        "first_release": "2022-10-24",
        "end_of_life": "2027-10",
    }


def write_policy(root: Path, approved: dict[str, object]) -> None:
    (root / "quality" / "runtime-support.json").write_text(json.dumps(approved))


def repository(root: Path) -> dict[str, object]:
    (root / "quality").mkdir()
    target = root / ".github" / "workflows"
    target.mkdir(parents=True)
    data = {version: {**release(), "branch": version} for version in VERSIONS}
    raw = json.dumps(data).encode()
    (root / "quality" / "python-releases.json").write_bytes(raw)
    approved = {**policy(), "snapshotSha256": hashlib.sha256(raw).hexdigest()}
    write_policy(root, approved)
    (root / "pyproject.toml").write_text(
        '[project]\nrequires-python = ">=3.11,<3.15"\n'
    )
    jobs = {
        name: {"strategy": {"matrix": {"python": list(VERSIONS)}}}
        for name in ("analysis", "compatibility")
    }
    (target / "ci.yml").write_text(yaml.safe_dump({"jobs": jobs}))
    return approved


def test_clean_review_and_declared_matrices(tmp_path: Path) -> None:
    repository(tmp_path)
    verify_runtimes(tmp_path, TODAY)
    verify_runtimes(tmp_path, date(2026, 12, 27))


@pytest.mark.parametrize(
    "today", [date(2026, 9, 28), date(2026, 12, 28), date(2026, 12, 29)]
)
def test_review_window_boundaries_fail(tmp_path: Path, today: date) -> None:
    repository(tmp_path)
    with pytest.raises(ValueError, match="review"):
        verify_runtimes(tmp_path, today)


@pytest.mark.parametrize("field", list(policy()))
def test_missing_policy_key_fails(tmp_path: Path, field: str) -> None:
    approved = repository(tmp_path)
    del approved[field]
    write_policy(tmp_path, approved)
    with pytest.raises(ValueError, match="keys"):
        verify_runtimes(tmp_path, TODAY)


@pytest.mark.parametrize("value", [None, [], {}, 1, "policy"])
def test_invalid_policy_shape_fails(tmp_path: Path, value: object) -> None:
    repository(tmp_path)
    (tmp_path / "quality" / "runtime-support.json").write_text(json.dumps(value))
    with pytest.raises(ValueError):
        verify_runtimes(tmp_path, TODAY)


@pytest.mark.parametrize(
    "field,value",
    [
        ("extra", True),
        ("source", "https://example.com/versions.rst"),
        (
            "source",
            "https://raw.githubusercontent.com/python/devguide/main/versions.rst",
        ),
        ("releaseCycleSource", "https://example.com/releases"),
        (
            "releaseCycleSource",
            "https://peps.python.org/api/release-cycle.json?unreviewed",
        ),
        ("snapshotSha256", "0" * 64),
        ("snapshotSha256", "f" * 64),
        ("reviewedOn", "20260929"),
        ("reviewBy", "invalid"),
        ("versions", []),
    ],
)
def test_untrusted_or_malformed_policy_fails(
    tmp_path: Path, field: str, value: object
) -> None:
    approved = repository(tmp_path)
    approved[field] = value
    write_policy(tmp_path, approved)
    with pytest.raises(ValueError):
        verify_runtimes(tmp_path, TODAY)


@pytest.mark.parametrize(
    "versions",
    [
        [],
        ["3.11", "3.11"],
        ["3.14", "3.11"],
        ["3.11", "3.13"],
        ["3.011"],
        ["3.-1"],
        ["4.0"],
        [3.11],
        ["3.11.1"],
        "3.11",
        None,
    ],
)
def test_invalid_branch_inventory_fails(versions: object) -> None:
    with pytest.raises(ValueError):
        branches(versions)


def test_supported_dates_include_start_and_exclude_eol_month() -> None:
    item = release()
    require_branch("3.11", item, date(2022, 10, 24))
    require_branch("3.11", item, date(2027, 9, 30))
    for today in [date(2022, 10, 23), date(2027, 10, 1), date(2027, 10, 2)]:
        with pytest.raises(ValueError, match="dates"):
            require_branch("3.11", item, today)
    assert end_of_support("2027-10-31") == date(2027, 10, 31)
    assert calendar("2024-02-29") == date(2024, 2, 29)


@pytest.mark.parametrize(
    "field,value",
    [
        ("branch", "3.12"),
        ("branch", "3.10"),
        ("status", "prerelease"),
        ("status", "end-of-life"),
        ("first_release", "2022-02-30"),
        ("end_of_life", "2027-13"),
        ("end_of_life", "202710"),
        ("end_of_life", None),
    ],
)
def test_unsupported_branch_or_malformed_dates_fail(field: str, value: object) -> None:
    item = {**release(), field: value}
    with pytest.raises(ValueError):
        require_branch("3.11", item, TODAY)


@pytest.mark.parametrize(
    "declaration",
    [">=3.10,<3.15", ">=3.11,<3.14", ">=3.12,<3.15", ">=3.11,<3.16", ">=3.11", ""],
)
def test_metadata_scope_must_match_review(tmp_path: Path, declaration: str) -> None:
    repository(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nrequires-python = "{declaration}"\n'
    )
    with pytest.raises(ValueError, match="metadata"):
        verify_runtimes(tmp_path, TODAY)


@pytest.mark.parametrize("name", ["analysis", "compatibility"])
@pytest.mark.parametrize("versions", [VERSIONS[:-1], VERSIONS + ["3.15"]])
def test_each_required_matrix_must_match(
    tmp_path: Path, name: str, versions: list[str]
) -> None:
    repository(tmp_path)
    path = tmp_path / ".github" / "workflows" / "ci.yml"
    jobs = {
        job: {"strategy": {"matrix": {"python": list(VERSIONS)}}}
        for job in ("analysis", "compatibility")
    }
    jobs[name]["strategy"]["matrix"]["python"] = versions
    path.write_text(yaml.safe_dump({"jobs": jobs}))
    with pytest.raises(ValueError, match="matrix"):
        verify_runtimes(tmp_path, TODAY)


@pytest.mark.parametrize("name", ["runtime-support.json", "python-releases.json"])
def test_missing_policy_or_snapshot_fails(tmp_path: Path, name: str) -> None:
    repository(tmp_path)
    (tmp_path / "quality" / name).unlink()
    with pytest.raises(FileNotFoundError):
        verify_runtimes(tmp_path, TODAY)


def test_native_entrypoint_uses_current_reviewed_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository(tmp_path)
    monkeypatch.chdir(tmp_path)
    runpy.run_module("quality.runtime_support_main", run_name="__main__")


@pytest.mark.parametrize("status", ["bugfix", "security"])
def test_both_stable_upstream_support_phases_pass(status: str) -> None:
    require_branch("3.11", {**release(), "status": status}, TODAY)


@pytest.mark.parametrize(
    "source", ["20260929", "2026-W40-2", "2026-9-29", "2026-09-029"]
)
def test_calendar_rejects_noncanonical_supported_iso_forms(source: str) -> None:
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        calendar(source)


def test_metadata_upper_bound_advances_an_odd_final_minor(tmp_path: Path) -> None:
    repository(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nrequires-python = ">=3.11,<3.14"\n'
    )
    verify_metadata(tmp_path, ["3.11", "3.12", "3.13"])


@pytest.mark.parametrize(
    "field,value",
    [("status", "prerelease"), ("branch", "3.10"), ("end_of_life", "2026-09")],
)
def test_complete_gate_rejects_unsupported_branch_in_reviewed_snapshot(
    tmp_path: Path, field: str, value: str
) -> None:
    approved = repository(tmp_path)
    path = tmp_path / "quality" / "python-releases.json"
    raw = json.loads(path.read_text())
    raw["3.14"][field] = value
    path.write_text(json.dumps(raw))
    approved["snapshotSha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    write_policy(tmp_path, approved)
    with pytest.raises(ValueError, match="stable|dates"):
        verify_runtimes(tmp_path, TODAY)
