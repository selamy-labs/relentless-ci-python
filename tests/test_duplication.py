"""Native duplicate probes and fail-closed scanner orchestration."""

import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from quality import duplication
from quality.duplication import native, prepare_output, verify_duplication
from quality.duplication_inventory import Eligible

SOURCE = """def combine(left: int, right: int) -> int:
    first = left + right
    second = first * 2
    third = second + left
    fourth = third - right
    fifth = fourth * first
    sixth = fifth + third
    seventh = sixth // 2
    return seventh + fourth
"""


def source(root: Path, name: str, content: str = SOURCE) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def configured(root: Path) -> None:
    for name in ("mise.toml", "mise.lock"):
        shutil.copy2(Path.cwd() / name, root / name)


def test_native_clean_and_duplicate_failure(tmp_path: Path) -> None:
    configured(tmp_path)
    source(tmp_path, "quality/check.py")
    source(tmp_path, "tests/test_small.py", "pass\n")
    verify_duplication(tmp_path)
    output = tmp_path / ".quality-results" / "duplication"
    receipt = json.loads((output / "verified.json").read_text())
    assert set(receipt["sources"]) == {"quality/check.py", "tests/test_small.py"}
    assert receipt["tool"] == duplication.VERSION
    assert len(receipt["eligible"]) == 1
    source(tmp_path, "tests/test_check.py")
    with pytest.raises(subprocess.CalledProcessError):
        verify_duplication(tmp_path)
    report = json.loads((output / "combined" / "jscpd-report.json").read_text())
    assert report["duplicates"]
    assert not (output / "verified.json").exists()


def test_native_deadline_expires_before_launch(tmp_path: Path) -> None:
    with pytest.raises(TimeoutError, match="whole-scan deadline"):
        native(tmp_path, ["--version"], time.monotonic() - 1)


def test_missing_native_tool_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("mise")

    monkeypatch.setattr(subprocess, "run", missing)
    with pytest.raises(FileNotFoundError, match="mise"):
        native(tmp_path, ["--version"], time.monotonic() + 5)


@pytest.mark.parametrize("status", [0, 3])
def test_native_exit_status_is_authoritative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    def result(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            ["jscpd"], status, stdout="receipt", stderr="failure"
        )

    monkeypatch.setattr(subprocess, "run", result)
    if status:
        with pytest.raises(subprocess.CalledProcessError):
            native(tmp_path, ["--version"], time.monotonic() + 5)
    else:
        assert native(tmp_path, ["--version"], time.monotonic() + 5) == "receipt"


def test_report_directory_rejects_symlink_and_removes_stale_receipt(
    tmp_path: Path,
) -> None:
    output = prepare_output(tmp_path)
    (output / "verified.json").write_text("stale")
    assert prepare_output(tmp_path) == output
    assert not (output / "verified.json").exists()
    shutil.rmtree(output)
    output.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        prepare_output(tmp_path)


def test_version_mismatch_fails_before_any_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source(tmp_path, "quality/check.py")

    def wrong(*_args: object, **_kwargs: object) -> str:
        return "jscpd 0.0.0"

    monkeypatch.setattr(duplication, "native", wrong)
    with pytest.raises(ValueError, match="version receipt"):
        verify_duplication(tmp_path)
    assert not (tmp_path / ".quality-results/duplication/verified.json").exists()


def test_missing_native_report_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "reports"

    def silent(*_args: object, **_kwargs: object) -> str:
        return ""

    monkeypatch.setattr(duplication, "native", silent)
    with pytest.raises(FileNotFoundError):
        duplication.scan(
            tmp_path,
            tmp_path / "config.json",
            [tmp_path / "file.py"],
            output,
            1,
            time.monotonic() + 5,
        )


def test_source_receipt_binds_bytes() -> None:
    value = duplication.receipt(
        {"quality/check.py": b"pass\n"}, {"/tmp/check.py": Eligible(5, 1, 1)}
    )
    assert value["tool"] == duplication.VERSION
    assert value["sources"] == {
        "quality/check.py": (
            "9f56e761d79bfdb34304a012586cb04d" "16b435ef6130091a97702e559260a2f2"
        )
    }
    assert value["eligible"] == ["/tmp/check.py"]
