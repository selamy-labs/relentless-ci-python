"""The inventory fails closed on unreviewed or incomplete license evidence."""

import hashlib
import json
import runpy
from pathlib import Path

import pytest

from quality.component_inventory import inventory
from quality.report_data import array, record

HASH = "a" * 64
SOURCE = "https://files.pythonhosted.org/packages/"


def fixture(root: Path) -> tuple[dict[str, object], str]:
    (root / "quality").mkdir()
    (root / "pyproject.toml").write_text(
        '[project]\nname = "example-project"\nversion = "0.1.0"\nlicense = "MIT"\n'
    )
    (root / "LICENSE").write_text("MIT License\n")
    lock = (
        "version = 1\n"
        '[[package]]\nname = "example-project"\nversion = "0.1.0"\n'
        'source = { editable = "." }\n'
        '[[package]]\nname = "alpha"\nversion = "1.0.0"\n'
        'source = { registry = "https://pypi.org/simple" }\n'
        f'sdist = {{ url = "{SOURCE}alpha-1.0.0.tar.gz", '
        f'hash = "sha256:{HASH}", size = 1 }}\n'
        '[[package]]\nname = "beta"\nversion = "2.0.0"\n'
        'source = { registry = "https://pypi.org/simple" }\n'
        f'sdist = {{ url = "{SOURCE}beta-2.0.0.tar.gz", '
        f'hash = "sha256:{HASH}", size = 1 }}\n'
    )
    (root / "uv.lock").write_text(lock)
    policy: dict[str, object] = {
        "version": 1,
        "projectLicense": "MIT",
        "projectLicenseSha256": hashlib.sha256(b"MIT License\n").hexdigest(),
        "approvedExpressions": ["MIT", "Apache-2.0"],
        "packages": {
            "alpha==1.0.0": {
                "spdx": "MIT",
                "evidenceKind": "pypi-release-metadata",
                "evidenceSha256": HASH,
                "evidenceUrl": "https://pypi.org/pypi/alpha/1.0.0/json",
            },
            "beta==2.0.0": {
                "spdx": "Apache-2.0",
                "evidenceKind": "locked-sdist-license-file",
                "evidenceSha256": HASH,
                "evidenceUrl": SOURCE + "beta-2.0.0.tar.gz#beta/LICENSE",
            },
        },
    }
    save(root, policy)
    return policy, lock


def save(root: Path, policy: dict[str, object]) -> None:
    (root / "quality/license-policy.json").write_text(json.dumps(policy))


def test_complete_inventory_binds_each_component_and_project(tmp_path: Path) -> None:
    fixture(tmp_path)
    result = inventory(tmp_path)
    assert result["projectLicense"] == "MIT"
    assert result["componentCount"] == 2
    rows = [record(value) for value in array(result["components"])]
    assert [row["identity"] for row in rows] == ["alpha==1.0.0", "beta==2.0.0"]
    assert rows[0]["spdx"] == "MIT" and rows[1]["spdx"] == "Apache-2.0"
    assert rows[0]["wheels"] == [] and record(rows[1]["sdist"])["size"] == 1
    assert (
        result["lockSha256"]
        == hashlib.sha256((tmp_path / "uv.lock").read_bytes()).hexdigest()
    )
    assert (
        result["policySha256"]
        == hashlib.sha256(
            (tmp_path / "quality/license-policy.json").read_bytes()
        ).hexdigest()
    )


def test_single_character_sdist_license_file_path_is_valid(tmp_path: Path) -> None:
    policy, _ = fixture(tmp_path)
    record(record(policy["packages"])["beta==2.0.0"])["evidenceUrl"] = (
        SOURCE + "beta-2.0.0.tar.gz#L"
    )
    save(tmp_path, policy)
    assert inventory(tmp_path)["componentCount"] == 2


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("version", 0, "unsupported component license policy version"),
        ("version", 2, "unsupported component license policy version"),
        ("projectLicense", "BSD-3-Clause", "project license differs"),
        ("projectLicense", "Zlib", "project license differs"),
        ("projectLicenseSha256", HASH, "project license notice differs"),
        ("projectLicenseSha256", "0" * 64, "project license notice differs"),
        ("approvedExpressions", ["MIT", "Apache-2.0", "UNKNOWN"], "approved SPDX"),
    ],
)
def test_unreviewed_top_level_policy_fails(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    policy, _ = fixture(tmp_path)
    policy[field] = value
    save(tmp_path, policy)
    with pytest.raises(ValueError, match=message):
        inventory(tmp_path)


@pytest.mark.parametrize(
    ("key", "field", "value", "message"),
    [
        ("alpha==1.0.0", "spdx", "UNKNOWN", "SPDX expression requires review"),
        ("alpha==1.0.0", "evidenceSha256", "bad", "canonical SHA-256"),
        ("alpha==1.0.0", "evidenceKind", "a-invalid", "provenance"),
        ("alpha==1.0.0", "evidenceKind", "z-invalid", "provenance"),
        ("alpha==1.0.0", "evidenceUrl", "https://unapproved.example/a", "provenance"),
        (
            "alpha==1.0.0",
            "evidenceUrl",
            "https://pypi.org/pypi/alpha/1.0.0/jso",
            "provenance",
        ),
        ("beta==2.0.0", "evidenceKind", "a-invalid", "provenance"),
        ("beta==2.0.0", "evidenceKind", "z-invalid", "provenance"),
        ("beta==2.0.0", "evidenceUrl", SOURCE + "beta-2.0.0.tar.gz#", "provenance"),
    ],
)
def test_unreviewed_component_fails(
    tmp_path: Path, key: str, field: str, value: object, message: str
) -> None:
    policy, _ = fixture(tmp_path)
    record(record(policy["packages"])[key])[field] = value
    save(tmp_path, policy)
    with pytest.raises(ValueError, match=message):
        inventory(tmp_path)


@pytest.mark.parametrize("extra", [False, True])
def test_missing_or_extra_license_record_fails(tmp_path: Path, extra: bool) -> None:
    policy, _ = fixture(tmp_path)
    packages = record(policy["packages"])
    if extra:
        packages["unlocked==1"] = packages["alpha==1.0.0"]
    else:
        packages.pop("alpha==1.0.0")
    save(tmp_path, policy)
    with pytest.raises(ValueError, match="locked component lacks reviewed"):
        inventory(tmp_path)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("duplicate", "duplicate locked component identity"),
        ("empty", "locked component inventory is empty"),
    ],
)
def test_lock_identity_is_complete(tmp_path: Path, change: str, message: str) -> None:
    _, lock = fixture(tmp_path)
    registry = lock.index('[[package]]\nname = "alpha"')
    if change == "duplicate":
        (tmp_path / "uv.lock").write_text(
            lock + lock[registry : lock.index('[[package]]\nname = "beta"')]
        )
    else:
        (tmp_path / "uv.lock").write_text(lock[:registry])
    with pytest.raises(ValueError, match=message):
        inventory(tmp_path)


def test_entrypoint_replaces_stale_receipt_only_after_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy, _ = fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    report = tmp_path / ".quality-results/component-inventory.json"
    assert not report.exists()
    runpy.run_module("quality.component_inventory_main", run_name="__main__")
    assert json.loads(report.read_text())["componentCount"] == 2
    report.write_text("stale")
    runpy.run_module("quality.component_inventory_main", run_name="__main__")
    actual = report.read_text()
    assert actual == json.dumps(inventory(tmp_path), indent=2) + "\n"
    assert json.loads(actual)["componentCount"] == 2
    policy["approvedExpressions"] = ["UNKNOWN"]
    save(tmp_path, policy)
    with pytest.raises(ValueError):
        runpy.run_module("quality.component_inventory_main", run_name="__main__")
    assert not report.exists()
