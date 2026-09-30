"""Fail closed on incomplete or substituted full-clone reports."""

from copy import deepcopy
from pathlib import Path

import pytest

from quality.duplication_inventory import Eligible
from quality.duplication_report import verify_duplication_report, verify_summary_totals
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


def test_accepts_equal_large_summary_counts() -> None:
    reported_files = int("257")
    reported_folders = int("259")
    expected_files = int("257")
    expected_folders = int("259")
    assert reported_files is not expected_files
    assert reported_folders is not expected_folders
    verify_summary_totals(
        {"totalFiles": reported_files, "totalFolders": reported_folders},
        expected_files,
        expected_folders,
    )


def test_accepts_no_threshold_eligible_files(tmp_path: Path) -> None:
    value = native(tmp_path / "small.py")
    summary = record(value["summary"])
    summary.update(files=[], folders=[], totalFiles=0, totalFolders=0)
    statistics = record(value["statistics"])
    statistics["formats"] = {}
    total = record(statistics["total"])
    total.update(lines=0, sources=0, tokens=0)
    verify_duplication_report(value, {})


def test_rejects_reported_clone(tmp_path: Path) -> None:
    path = tmp_path / "check.py"
    value = native(path)
    array(value["duplicates"]).append({"fragment": "duplicate"})
    with pytest.raises(ValueError, match="contains clones"):
        verify_duplication_report(value, expected(path))


@pytest.mark.parametrize("field", ["clones", "duplicatedLines", "percentage"])
@pytest.mark.parametrize("invalid", [True, False, -1, 1])
def test_rejects_nonzero_or_nonnumeric_metric(
    tmp_path: Path, field: str, invalid: object
) -> None:
    path = tmp_path / "check.py"
    value = native(path)
    statistics = record(value["statistics"])
    record(statistics["total"])[field] = invalid
    with pytest.raises(ValueError, match="invalid zero"):
        verify_duplication_report(value, expected(path))


@pytest.mark.parametrize("field", ["sources", "lines", "tokens"])
@pytest.mark.parametrize("invalid", [0, 999])
def test_rejects_wrong_metric_inventory(
    tmp_path: Path, field: str, invalid: int
) -> None:
    path = tmp_path / "check.py"
    value = native(path)
    statistics = record(value["statistics"])
    record(record(statistics["formats"])["python"])[field] = invalid
    with pytest.raises(ValueError, match="statistics differ"):
        verify_duplication_report(value, expected(path))


@pytest.mark.parametrize(
    "change", ["file", "folder", "file-total", "folder-total", "folder-total-zero"]
)
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
    elif change == "folder-total":
        summary["totalFolders"] = 2
    else:
        summary["totalFolders"] = 0
    with pytest.raises(ValueError, match="incomplete|totals"):
        verify_duplication_report(value, expected(path))


@pytest.mark.parametrize(
    "field", ["path", "format", "bytes", "duplicatedLines", "duplicatedTokens"]
)
def test_rejects_substituted_file_receipt(tmp_path: Path, field: str) -> None:
    path = tmp_path / "check.py"
    value = native(path)
    file, _folder = parts(value)
    file[field] = "other" if field in {"path", "format"} else 999
    with pytest.raises(ValueError, match="inventory|format|source|cloned"):
        verify_duplication_report(value, expected(path))


@pytest.mark.parametrize(
    ("field", "lower"), [("bytes", 8), ("lines", 4), ("tokens", 49)]
)
def test_rejects_underreported_file_counts(
    tmp_path: Path, field: str, lower: int
) -> None:
    path = tmp_path / "check.py"
    value = native(path)
    file, _folder = parts(value)
    file[field] = lower
    with pytest.raises(ValueError, match="eligible source"):
        verify_duplication_report(value, expected(path))


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("path", "other"),
        ("files", 0),
        ("files", 999),
        ("bytes", 0),
        ("bytes", 999),
        ("duplicatedLines", 999),
    ],
)
def test_rejects_substituted_folder_receipt(
    tmp_path: Path, field: str, invalid: object
) -> None:
    path = tmp_path / "check.py"
    value = native(path)
    _file, folder = parts(value)
    folder[field] = invalid
    with pytest.raises(ValueError, match="inventory|folder"):
        verify_duplication_report(value, expected(path))


def test_rejects_folder_schema_change(tmp_path: Path) -> None:
    path = tmp_path / "check.py"
    value = native(path)
    _file, folder = parts(value)
    folder["extra"] = 1
    with pytest.raises(ValueError, match="folder fields"):
        verify_duplication_report(value, expected(path))


@pytest.mark.parametrize(
    "field", ["bytes", "complexity", "duplicatedLines", "files", "lines", "tokens"]
)
def test_rejects_missing_folder_metadata(tmp_path: Path, field: str) -> None:
    path = tmp_path / "check.py"
    value = native(path)
    _file, folder = parts(value)
    del folder[field]
    with pytest.raises(ValueError, match="folder fields"):
        verify_duplication_report(value, expected(path))


def test_rejects_extra_file_metadata(tmp_path: Path) -> None:
    path = tmp_path / "check.py"
    value = native(path)
    file, _folder = parts(value)
    file["extra"] = 0
    with pytest.raises(ValueError, match="file fields"):
        verify_duplication_report(value, expected(path))


@pytest.mark.parametrize(
    "field",
    [
        "format",
        "bytes",
        "complexity",
        "duplicatedLines",
        "duplicatedTokens",
        "lines",
        "tokens",
    ],
)
def test_rejects_missing_file_metadata(tmp_path: Path, field: str) -> None:
    path = tmp_path / "check.py"
    value = native(path)
    file, _folder = parts(value)
    del file[field]
    with pytest.raises(ValueError, match="file fields"):
        verify_duplication_report(value, expected(path))


@pytest.mark.parametrize("invalid", [-1, True, 1.5])
def test_rejects_invalid_file_complexity(tmp_path: Path, invalid: object) -> None:
    path = tmp_path / "check.py"
    value = native(path)
    file, _folder = parts(value)
    file["complexity"] = invalid
    with pytest.raises(ValueError, match="nonnegative"):
        verify_duplication_report(value, expected(path))


def test_rejects_later_file_format(tmp_path: Path) -> None:
    path = tmp_path / "check.py"
    value = native(path)
    file, _folder = parts(value)
    file["format"] = "zzzz"
    with pytest.raises(ValueError, match="format"):
        verify_duplication_report(value, expected(path))


def test_rejects_extra_statistics_metric(tmp_path: Path) -> None:
    path = tmp_path / "check.py"
    value = native(path)
    statistics = record(value["statistics"])
    record(statistics["total"])["extra"] = 0
    with pytest.raises(ValueError, match="fields"):
        verify_duplication_report(value, expected(path))


def test_rejects_unexpected_extra_format(tmp_path: Path) -> None:
    path = tmp_path / "check.py"
    value = native(path)
    statistics = record(value["statistics"])
    record(statistics["formats"])["typescript"] = metrics()
    with pytest.raises(ValueError, match="format inventory"):
        verify_duplication_report(value, expected(path))


def test_rejects_duplicate_reported_path(tmp_path: Path) -> None:
    path = tmp_path / "check.py"
    value = native(path)
    summary = record(value["summary"])
    array(summary["files"]).append(deepcopy(array(summary["files"])[0]))
    summary["totalFiles"] = 2
    with pytest.raises(ValueError, match="incomplete"):
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


def test_rejects_later_summary_measure(tmp_path: Path) -> None:
    path = tmp_path / "check.py"
    value = native(path)
    record(value["summary"])["by"] = "zzzz"
    with pytest.raises(ValueError, match="measure"):
        verify_duplication_report(value, expected(path))


def test_rejects_zero_file_total(tmp_path: Path) -> None:
    path = tmp_path / "check.py"
    value = native(path)
    record(value["summary"])["totalFiles"] = 0
    with pytest.raises(ValueError, match="totals"):
        verify_duplication_report(value, expected(path))
