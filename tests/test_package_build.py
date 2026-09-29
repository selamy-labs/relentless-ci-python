"""Fresh builds cannot reuse old artifacts or publish results before consumers pass."""

import runpy
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from quality import package_build
from quality.package_metadata import record_bytes
from tests.test_package_contents import (
    PROJECT,
    sdist_values,
    sources,
    wheel_values,
    write_sdist,
    write_wheel,
)


def repository(root: Path) -> None:
    sources(root)
    (root / "pyproject.toml").write_text(
        "[project]\n"
        + "\n".join(f'{key} = "{value}"' for key, value in PROJECT.items())
    )
    (root / "uv.lock").write_text("locked build")
    (root / "quality").mkdir()
    (root / "quality/build-constraints.txt").write_text("hashed build")


def test_stage_copies_public_inputs_and_every_new_source(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    repository(root)
    (root / ".gitignore").write_text("private patterns")
    cache = root / "src/relentless_example/__pycache__"
    cache.mkdir()
    (cache / "bytecode.pyc").write_bytes(b"generated")
    (root / "src/new_module.py").write_text("new source")
    stage = tmp_path / "stage"
    stage.mkdir()
    package_build.public_stage(root, stage)
    assert (stage / "src/new_module.py").read_text() == "new source"
    assert not (stage / "src/relentless_example/__pycache__").exists()
    assert not (stage / ".gitignore").exists()
    for name in ("README.md", "LICENSE", "pyproject.toml", "uv.lock"):
        assert (stage / name).read_bytes() == (root / name).read_bytes()


@pytest.mark.parametrize("archive", [False, True])
def test_native_build_requires_hashes_and_selected_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, archive: bool
) -> None:
    commands: list[list[str]] = []
    source = tmp_path / "source"
    if archive:
        source.write_bytes(b"archive")
    else:
        source.mkdir()
    output = tmp_path / "output"
    constraints = tmp_path / "constraints"

    def command(
        arguments: list[str], root: Path, timeout: float, env: dict[str, str]
    ) -> None:
        assert root == tmp_path
        assert timeout == 120
        assert env["PYTHONWARNINGS"] == "error"
        commands.append(arguments)

    monkeypatch.setattr(package_build, "run", command)
    package_build.native_build(source, output, constraints, tmp_path)
    assert commands == [
        [
            "uv",
            "build",
            str(source),
            *(["--wheel"] if archive else []),
            "--build-constraints",
            str(constraints),
            "--require-hashes",
            "--python",
            sys.executable,
            "--no-python-downloads",
            "--no-create-gitignore",
            "--out-dir",
            str(output),
        ]
    ]


@dataclass
class Scenario:
    root: Path
    defect: str
    stages: list[Path] = field(default_factory=list[Path])
    commands: list[tuple[Path, Path]] = field(default_factory=list[tuple[Path, Path]])
    installed: list[Path] = field(default_factory=list[Path])

    def build(
        self, source: Path, directory: Path, constraints: Path, root: Path
    ) -> None:
        self.stages.append(root)
        self.commands.append((source, directory))
        assert constraints == self.root / "quality/build-constraints.txt"
        assert constraints.read_text() == "hashed build"
        assert not (self.root / ".quality-results/dist").exists()
        if self.defect == "build-error":
            raise subprocess.CalledProcessError(2, ["uv", "build"])
        directory.mkdir()
        files = self.artifact_files(root)
        write_wheel(directory / "sample-1.0.0-py3-none-any.whl", files)
        if source.is_dir():
            write_sdist(directory / "sample-1.0.0.tar.gz", sdist_values(root))

    def artifact_files(self, root: Path) -> dict[str, bytes]:
        files = wheel_values(root)
        if self.defect == "archive":
            files["secret.txt"] = b"hidden"
        generators = {"reproducibility-low": b"a", "reproducibility-high": b"z"}
        if self.defect in generators and len(self.commands) == 2:
            files["sample-1.0.0.dist-info/WHEEL"] += (
                b"Generator: " + generators[self.defect] + b"\n"
            )
            files["sample-1.0.0.dist-info/RECORD"] = record_bytes(
                files, "sample-1.0.0.dist-info/RECORD"
            )
        return files

    def consumer(self, wheel: Path) -> None:
        self.installed.append(wheel)
        assert wheel.is_file()
        assert not (self.root / ".quality-results/dist").exists()
        if self.defect == "consumer":
            raise ValueError("installed consumer failed")

    def successful(self, output: Path) -> None:
        stage = self.stages[0]
        assert {path.name for path in output.iterdir()} == {
            "sample-1.0.0-py3-none-any.whl",
            "sample-1.0.0.tar.gz",
        }
        assert self.commands == [
            (stage, stage / "dist"),
            (stage / "dist/sample-1.0.0.tar.gz", stage / "rebuilt"),
        ]
        assert self.installed == [
            stage / "dist/sample-1.0.0-py3-none-any.whl",
            stage / "rebuilt/sample-1.0.0-py3-none-any.whl",
        ]


@pytest.mark.parametrize(
    "defect",
    [
        "none",
        "build-error",
        "archive",
        "consumer",
        "reproducibility-low",
        "reproducibility-high",
    ],
)
@pytest.mark.parametrize("stale", [False, True])
def test_full_package_sequence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, defect: str, stale: bool
) -> None:
    repository(tmp_path)
    output = tmp_path / ".quality-results/dist"
    if stale:
        output.mkdir(parents=True)
        (output / "stale.whl").write_bytes(b"stale artifact")
    scenario = Scenario(tmp_path, defect)
    monkeypatch.setattr(package_build, "native_build", scenario.build)
    monkeypatch.setattr(package_build, "installed_consumer", scenario.consumer)
    if defect == "none":
        package_build.verify_packages(tmp_path)
        scenario.successful(output)
    else:
        with pytest.raises((ValueError, subprocess.CalledProcessError)):
            package_build.verify_packages(tmp_path)
        assert not output.exists()
    assert all(not stage.exists() for stage in scenario.stages)


def test_module_entry_uses_current_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    roots: list[Path] = []
    monkeypatch.setattr(package_build, "verify_packages", roots.append)
    runpy.run_module("quality.package_main", run_name="__main__")
    assert roots == [Path.cwd()]
