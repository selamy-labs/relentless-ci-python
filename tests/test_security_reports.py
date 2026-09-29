"""Malformed, incomplete and falsely clean scanner-result probes."""

import copy
from pathlib import Path

import pytest

from quality.report_data import array, record, text, unique
from quality.security_reports import (
    read_report,
    verify_audit,
    verify_empty,
    verify_sast,
)


def audit(lockfile: Path) -> dict[str, object]:
    lockfile.write_text('[[package]]\nname = "example"\nversion = "1.0"\n')
    return {
        "results": [
            {
                "source": {"type": "lockfile", "path": str(lockfile)},
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


def package_report(lockfile: Path, item: object) -> dict[str, object]:
    report = audit(lockfile)
    result = record(array(report["results"])[0])
    result["packages"] = item
    return report


def clean_sast() -> dict[str, object]:
    return {
        "results": [],
        "errors": [],
        "skipped_rules": [],
        "paths": {"scanned": ["src/a.py"]},
    }


@pytest.mark.parametrize("value", [None, True, [], "text", 1])
def test_requires_report_objects(value: object) -> None:
    with pytest.raises(ValueError, match="object"):
        record(value)


@pytest.mark.parametrize("value", [None, True, {}, "text", 1])
def test_requires_report_arrays(value: object) -> None:
    with pytest.raises(ValueError, match="array"):
        array(value)


@pytest.mark.parametrize("value", [None, True, [], {}, "", 1])
def test_requires_nonempty_report_strings(value: object) -> None:
    with pytest.raises(ValueError, match="nonempty string"):
        text(value)


def test_accepts_typed_boundary_values() -> None:
    assert record({"key": 1}) == {"key": 1}
    assert array([1]) == [1]
    assert text("text") == "text"
    verify_empty([])


def test_rejects_duplicate_inventory() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        unique([("example", "1.0", "PyPI"), ("example", "1.0", "PyPI")])


def test_reads_report_and_rejects_missing_or_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    with pytest.raises(FileNotFoundError):
        read_report(path)
    path.write_text("{")
    with pytest.raises(ValueError):
        read_report(path)
    path.write_text('{"results": []}')
    assert read_report(path) == {"results": []}


def test_accepts_complete_clean_static_security_scan() -> None:
    verify_sast(clean_sast(), {"src/a.py"})


@pytest.mark.parametrize("field", ["results", "errors", "skipped_rules"])
def test_rejects_findings_errors_and_skipped_rules(field: str) -> None:
    report = clean_sast()
    report[field] = ["one unresolved result"]
    with pytest.raises(ValueError, match="reported"):
        verify_sast(report, {"src/a.py"})


@pytest.mark.parametrize("scanned", [[], ["other.py"], ["src/a.py", "extra.py"]])
def test_rejects_incomplete_or_substituted_source_inventory(scanned: list[str]) -> None:
    report = clean_sast()
    report["paths"] = {"scanned": scanned}
    with pytest.raises(ValueError, match="inventory is incomplete"):
        verify_sast(report, {"src/a.py"})


def test_rejects_missing_static_security_fields() -> None:
    with pytest.raises(KeyError):
        verify_sast({}, {"src/a.py"})


def test_accepts_complete_clean_dependency_audit(tmp_path: Path) -> None:
    lock = tmp_path / "uv.lock"
    verify_audit(audit(lock), lock)


@pytest.mark.parametrize("kind", ["file", "scanner"])
def test_rejects_wrong_audit_source_type(tmp_path: Path, kind: str) -> None:
    lock = tmp_path / "uv.lock"
    report = audit(lock)
    record(array(report["results"])[0])["source"] = {"type": kind, "path": str(lock)}
    with pytest.raises(ValueError, match="requested lockfile"):
        verify_audit(report, lock)


@pytest.mark.parametrize("name", ["aaa.lock", "zzz.lock"])
def test_rejects_wrong_audit_lockfile(tmp_path: Path, name: str) -> None:
    lock = tmp_path / "uv.lock"
    report = audit(lock)
    record(array(report["results"])[0])["source"] = {
        "type": "lockfile",
        "path": str(tmp_path / name),
    }
    with pytest.raises(ValueError, match="requested lockfile"):
        verify_audit(report, lock)


@pytest.mark.parametrize("count", [0, 2])
def test_requires_exactly_one_scanned_lockfile(tmp_path: Path, count: int) -> None:
    lock = tmp_path / "uv.lock"
    report = audit(lock)
    report["results"] = array(report["results"]) * count
    with pytest.raises(ValueError):
        verify_audit(report, lock)


@pytest.mark.parametrize("field", ["vulnerabilities", "groups", "license_violations"])
def test_rejects_all_audit_findings_without_a_severity_floor(
    tmp_path: Path, field: str
) -> None:
    lock = tmp_path / "uv.lock"
    item: dict[str, object] = {
        "package": {"name": "example", "version": "1.0", "ecosystem": "PyPI"},
        field: [{"severity": "LOW"}],
    }
    with pytest.raises(ValueError, match="reported"):
        verify_audit(package_report(lock, [item]), lock)


@pytest.mark.parametrize("change", ["name", "version", "ecosystem"])
def test_rejects_substituted_packages(tmp_path: Path, change: str) -> None:
    lock = tmp_path / "uv.lock"
    package = {"name": "example", "version": "1.0", "ecosystem": "PyPI"}
    package[change] = "substituted"
    with pytest.raises(ValueError, match="inventory is incomplete"):
        verify_audit(package_report(lock, [{"package": package}]), lock)


def test_rejects_omitted_and_duplicate_audit_packages(tmp_path: Path) -> None:
    lock = tmp_path / "uv.lock"
    with pytest.raises(ValueError, match="inventory is incomplete"):
        verify_audit(package_report(lock, []), lock)
    report = audit(lock)
    result = record(array(report["results"])[0])
    result["packages"] = array(result["packages"]) * 2
    with pytest.raises(ValueError, match="duplicate"):
        verify_audit(report, lock)


def test_empty_lock_and_audit_cannot_pass(tmp_path: Path) -> None:
    lock = tmp_path / "uv.lock"
    report = package_report(lock, [])
    lock.write_text("package = []")
    with pytest.raises(ValueError, match="inventory is incomplete"):
        verify_audit(report, lock)


def test_lock_changes_invalidate_the_audit(tmp_path: Path) -> None:
    lock = tmp_path / "uv.lock"
    report = copy.deepcopy(audit(lock))
    lock.write_text('[[package]]\nname = "example"\nversion = "2.0"\n')
    with pytest.raises(ValueError, match="inventory is incomplete"):
        verify_audit(report, lock)


def test_dependency_report_errors_cannot_pass(tmp_path: Path) -> None:
    lock = tmp_path / "uv.lock"
    report = audit(lock)
    report["errors"] = ["query failed"]
    with pytest.raises(ValueError, match="reported"):
        verify_audit(report, lock)
