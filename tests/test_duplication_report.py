"""Fail closed on incomplete or substituted full-clone reports."""

from copy import deepcopy
from pathlib import Path

import pytest

from quality.duplication_inventory import Eligible
from quality.duplication_report import verify_duplication_report
from quality.report_data import array, record


def metrics() -> dict[str, object]:
    return {
        "clones": 0,
        "duplicatedLines": 0,
        "duplicatedTokens": 0,
        "lines": 5,
        "newClones": 0,
        "newDuplicatedLines": 0,
        "percentage": 0.0,
        "percentageTokens": 0.0,
        "sources": 1,
        "tokens": 50,
    }


def native(path: Path) -> dict[str, object]:
    filename = str(path)
    folder = str(path.parent)
    return {
        "duplicates": [],
        "statistics": {
            "detectionDate": "2026-09-29T20:00:00.000Z",
            "formats": {"python": metrics()},
            "total": metrics(),
        },
        "summary": {
            "by": "tokens",
            "totalFiles": 1,
            "totalFolders": 1,
            "files": [
                {
                    "bytes": 9,
                    "complexity": 0,
                    "duplicatedLines": 0,
                    "duplicatedTokens": 0,
                    "format": "python",
                    "lines": 5,
                    "path": filename,
                    "tokens": 50,
                }
            ],
            "folders": [
                {
                    "bytes": 9,
                    "complexity": 0,
                    "duplicatedLines": 0,
                    "files": 1,
                    "lines": 5,
                    "path": folder,
                    "tokens": 50,
                }
            ],
        },
    }


def parts(value: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    summary = record(value["summary"])
    return record(array(summary["files"])[0]), record(array(summary["folders"])[0])


def expected(path: Path) -> dict[str, Eligible]:
    return {str(path): Eligible(9, 5, 50)}


def test_accepts_complete_clean_report(tmp_path: Path) -> None:
    path = tmp_path / "check.py"
    verify_duplication_report(native(path), expected(path))


def test_rejects_reported_clone(tmp_path: Path) -> None:
    path = tmp_path / "check.py"
    value = native(path)
    array(value["duplicates"]).append({"fragment": "duplicate"})
    with pytest.raises(ValueError, match="contains clones"):
        verify_duplication_report(value, expected(path))


@pytest.mark.parametrize("field", ["clones", "duplicatedLines", "percentage"])
def test_rejects_nonzero_or_nonnumeric_metric(tmp_path: Path, field: str) -> None:
    path = tmp_path / "check.py"
    value = native(path)
    statistics = record(value["statistics"])
    record(statistics["total"])[field] = True
    with pytest.raises(ValueError, match="invalid zero"):
        verify_duplication_report(value, expected(path))


@pytest.mark.parametrize("field", ["sources", "lines", "tokens"])
def test_rejects_wrong_metric_inventory(tmp_path: Path, field: str) -> None:
    path = tmp_path / "check.py"
    value = native(path)
    statistics = record(value["statistics"])
    record(record(statistics["formats"])["python"])[field] = 999
    with pytest.raises(ValueError, match="statistics differ"):
        verify_duplication_report(value, expected(path))


@pytest.mark.parametrize("change", ["file", "folder", "file-total", "folder-total"])
def test_rejects_missing_summary_inventory(tmp_path: Path, change: str) -> None:
    path = tmp_path / "check.py"
    value = native(path)
    summary = record(value["summary"])
    if change == "file":
        summary["files"] = []
    elif change == "folder":
        summary["folders"] = []
    elif change == "file-total":
        summary["totalFiles"] = 2
    else:
        summary["totalFolders"] = 2
    with pytest.raises(ValueError, match="incomplete|totals"):
        verify_duplication_report(value, expected(path))


@pytest.mark.parametrize("field", ["path", "format", "bytes", "duplicatedLines"])
def test_rejects_substituted_file_receipt(tmp_path: Path, field: str) -> None:
    path = tmp_path / "check.py"
    value = native(path)
    file, _folder = parts(value)
    file[field] = "other" if field in {"path", "format"} else 999
    with pytest.raises(ValueError, match="inventory|format|source|cloned"):
        verify_duplication_report(value, expected(path))


@pytest.mark.parametrize("field", ["path", "files", "bytes", "duplicatedLines"])
def test_rejects_substituted_folder_receipt(tmp_path: Path, field: str) -> None:
    path = tmp_path / "check.py"
    value = native(path)
    _file, folder = parts(value)
    folder[field] = "other" if field == "path" else 999
    with pytest.raises(ValueError, match="inventory|folder"):
        verify_duplication_report(value, expected(path))


def test_rejects_folder_schema_change(tmp_path: Path) -> None:
    path = tmp_path / "check.py"
    value = native(path)
    _file, folder = parts(value)
    folder["extra"] = 1
    with pytest.raises(ValueError, match="folder fields"):
        verify_duplication_report(value, expected(path))


@pytest.mark.parametrize("change", ["timestamp", "format", "summary", "metric-field"])
def test_rejects_report_metadata_change(tmp_path: Path, change: str) -> None:
    path = tmp_path / "check.py"
    value = deepcopy(native(path))
    statistics = record(value["statistics"])
    if change == "timestamp":
        statistics["detectionDate"] = "2026-09-29T20:00:00"
    elif change == "format":
        statistics["formats"] = {}
    elif change == "summary":
        record(value["summary"])["by"] = "lines"
    else:
        del record(statistics["total"])["tokens"]
    with pytest.raises(ValueError, match="timezone|format|measure|fields"):
        verify_duplication_report(value, expected(path))
