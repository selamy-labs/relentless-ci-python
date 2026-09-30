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


def test_native_uses_exact_per_scan_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    options: list[object] = []

    def completed(*_args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        options.append(kwargs["timeout"])
        return subprocess.CompletedProcess(["jscpd"], 0, "jscpd 5.3.3", "")

    monkeypatch.setattr(subprocess, "run", completed)
    assert native(tmp_path, ["--version"], time.monotonic() + 100)
    assert options == [30.0]


def test_positive_fractional_scan_budget_still_launches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed: list[float] = []

    def completed(*_args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        timeout = kwargs["timeout"]
        assert isinstance(timeout, (int, float))
        observed.append(float(timeout))
        return subprocess.CompletedProcess(["jscpd"], 0, "done", "")

    monkeypatch.setattr(subprocess, "run", completed)
    monkeypatch.setattr(time, "monotonic", lambda: 100.0)
    assert native(tmp_path, ["--version"], 100.5) == "done"
    assert observed == [0.5]


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


def test_newer_unexpected_native_version_also_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source(tmp_path, "quality/check.py")

    def wrong(*_args: object, **_kwargs: object) -> str:
        return "jscpd 999.0.0"

    monkeypatch.setattr(duplication, "native", wrong)
    with pytest.raises(ValueError, match="version receipt"):
        verify_duplication(tmp_path)


def test_whole_scan_uses_exact_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source(tmp_path, "quality/check.py")

    def capture(_root: Path, _args: list[str], deadline: float) -> str:
        assert deadline == 400.0
        raise RuntimeError("observed")

    monkeypatch.setattr(time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(duplication, "native", capture)
    with pytest.raises(RuntimeError, match="observed"):
        verify_duplication(tmp_path)


@pytest.mark.parametrize(
    ("lines", "tokens", "enrolled"),
    [(3, 50, False), (4, 49, False), (4, 50, True)],
)
def test_exact_clone_inventory_threshold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    lines: int,
    tokens: int,
    enrolled: bool,
) -> None:
    path = tmp_path / "stage" / "quality" / "check.py"
    path.parent.mkdir(parents=True)
    path.write_text("pass\n")
    seen: list[int] = []

    def scanned(
        _root: Path,
        _config: Path,
        _paths: list[Path],
        _output: Path,
        minimum: int,
        _deadline: float,
    ) -> object:
        seen.append(minimum)
        return {}

    monkeypatch.setattr(duplication, "scan", scanned)

    def inventory(*_args: object) -> Eligible:
        return Eligible(5, lines, tokens)

    monkeypatch.setattr(duplication, "duplication_inventory", inventory)
    found = duplication.eligible_inputs(
        tmp_path,
        tmp_path / "config.json",
        {"quality/check.py": b"pass\n"},
        tmp_path / "stage",
        tmp_path / "reports",
        100.0,
    )
    assert seen == [1]
    assert (str(path) in found) is enrolled


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


@pytest.mark.parametrize(
    ("minimum", "lines", "threshold"),
    [(1, "1", "100"), (50, "4", "0")],
)
def test_native_scan_receives_exact_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    minimum: int,
    lines: str,
    threshold: str,
) -> None:
    observed: list[str] = []

    def report(_root: Path, args: list[str], _deadline: float) -> str:
        observed.extend(args)
        output = Path(args[args.index("--output") + 1])
        (output / "jscpd-report.json").write_text("{}\n")
        return ""

    monkeypatch.setattr(duplication, "native", report)
    assert (
        duplication.scan(
            tmp_path,
            tmp_path / "config.json",
            [tmp_path / "quality.py"],
            tmp_path / f"report-{minimum}",
            minimum,
            100.0,
        )
        == {}
    )
    assert observed[observed.index("--min-tokens") + 1] == str(minimum)
    assert observed[observed.index("--min-lines") + 1] == lines
    assert observed[observed.index("--threshold") + 1] == threshold


def test_native_scan_rejects_unreviewed_threshold(tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        duplication.scan(
            tmp_path,
            tmp_path / "config.json",
            [tmp_path / "quality.py"],
            tmp_path / "report",
            51,
            100.0,
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
