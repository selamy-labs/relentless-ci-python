"""Archive inventories, source identity, metadata and RECORD cannot be weakened."""

import gzip
import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from quality.package_contents import (
    ENTRY_POINTS,
    public_sources,
    verify_sdist,
    verify_wheel,
)
from quality.package_metadata import record_bytes

PROJECT: dict[str, object] = {
    "name": "sample",
    "version": "1.0.0",
    "description": "Sample project",
    "license": "MIT",
    "requires-python": ">=3.11,<3.15",
}
META = (
    b"Metadata-Version: 2.5\nName: sample\nVersion: 1.0.0\n"
    b"Summary: Sample project\nLicense-Expression: MIT\nLicense-File: LICENSE\n"
    b"Requires-Python: <3.15,>=3.11\n"
)
INFO = "sample-1.0.0.dist-info/"


def sources(root: Path) -> None:
    directory = root / "src/relentless_example"
    directory.mkdir(parents=True)
    for name in (
        "__init__.py",
        "cli.py",
        "normalization.py",
        "validation.py",
        "py.typed",
    ):
        (directory / name).write_bytes(name.encode())
    for name in ("README.md", "LICENSE", "pyproject.toml"):
        (root / name).write_bytes(name.encode())


def wheel_values(root: Path) -> dict[str, bytes]:
    files = public_sources(root)
    files[INFO + "licenses/LICENSE"] = (root / "LICENSE").read_bytes()
    files[INFO + "entry_points.txt"] = ENTRY_POINTS
    files[INFO + "METADATA"] = META
    files[INFO + "WHEEL"] = (
        b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    )
    files[INFO + "RECORD"] = record_bytes(files, INFO + "RECORD")
    return files


def write_wheel(path: Path, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items():
            member = zipfile.ZipInfo(name)
            member.external_attr = 0o100644 << 16
            archive.writestr(member, data)


def sdist_values(root: Path) -> dict[str, bytes]:
    prefix = "sample-1.0.0/"
    files = {
        prefix + "src/" + name: data for name, data in public_sources(root).items()
    }
    for name in ("README.md", "LICENSE", "pyproject.toml"):
        files[prefix + name] = (root / name).read_bytes()
    files[prefix + "PKG-INFO"] = META
    return files


def write_sdist(path: Path, files: dict[str, bytes]) -> None:
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w") as archive:
        for name, contents in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(contents)
            member.mode = 0o644
            archive.addfile(member, io.BytesIO(contents))
    path.write_bytes(gzip.compress(data.getvalue()))


def test_complete_wheel_and_source_archives(tmp_path: Path) -> None:
    sources(tmp_path)
    wheel = tmp_path / "package.whl"
    write_wheel(wheel, wheel_values(tmp_path))
    verify_wheel(wheel, tmp_path, PROJECT)
    sdist = tmp_path / "package.tar.gz"
    write_sdist(sdist, sdist_values(tmp_path))
    verify_sdist(sdist, tmp_path, PROJECT)
    cache = tmp_path / "src/relentless_example/__pycache__"
    cache.mkdir()
    (cache / "bytecode.pyc").write_bytes(b"generated")
    verify_wheel(wheel, tmp_path, PROJECT)


@pytest.mark.parametrize(
    "kind", ["extra", "missing", "changed", "record", "entry-point"]
)
def test_wheel_defects_fail(tmp_path: Path, kind: str) -> None:
    sources(tmp_path)
    files = wheel_values(tmp_path)
    if kind == "extra":
        files["hidden.txt"] = b"hidden"
    if kind == "missing":
        del files["relentless_example/py.typed"]
    if kind == "changed":
        files["relentless_example/cli.py"] = b"changed"
    if kind == "record":
        files[INFO + "RECORD"] = b"wrong,,\n"
    if kind == "entry-point":
        files[INFO + "entry_points.txt"] = b"wrong"
    path = tmp_path / "package.whl"
    write_wheel(path, files)
    with pytest.raises(ValueError):
        verify_wheel(path, tmp_path, PROJECT)


@pytest.mark.parametrize("kind", ["extra", "missing", "changed"])
def test_source_defects_fail(tmp_path: Path, kind: str) -> None:
    sources(tmp_path)
    files = sdist_values(tmp_path)
    if kind == "extra":
        files["sample-1.0.0/.codegraph/private.db"] = b"hidden"
    if kind == "missing":
        del files["sample-1.0.0/README.md"]
    if kind == "changed":
        files["sample-1.0.0/src/relentless_example/cli.py"] = b"changed"
    path = tmp_path / "package.tar.gz"
    write_sdist(path, files)
    with pytest.raises(ValueError):
        verify_sdist(path, tmp_path, PROJECT)


def test_unenrolled_source_cannot_disappear_from_a_distribution(tmp_path: Path) -> None:
    sources(tmp_path)
    (tmp_path / "src/new_module.py").write_text("unexpected = 1\n")
    with pytest.raises(ValueError, match="inventory differs"):
        public_sources(tmp_path)
