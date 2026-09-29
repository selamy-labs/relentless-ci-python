"""Real archives exercise byte budgets, permissions and unsafe member rejection."""

import gzip
import io
import stat
import tarfile
import zipfile
from pathlib import Path

import pytest

from quality.package_archive import (
    compressed,
    content_size,
    insert,
    sdist_files,
    sdist_member,
    tar_bytes,
    tar_container,
    wheel_files,
)

COMPRESSED_BUDGET = 65536
CONTENT_BUDGET = 262144
TAR_BUDGET = 524288


def test_compressed_boundary(tmp_path: Path) -> None:
    path = tmp_path / "archive"
    data = b"a" * COMPRESSED_BUDGET
    path.write_bytes(data)
    assert compressed(path) == data
    path.write_bytes(data + b"a")
    with pytest.raises(ValueError, match="compressed package"):
        compressed(path)


def test_content_boundary() -> None:
    content_size([CONTENT_BUDGET - 1, 1])
    content_size([])
    with pytest.raises(ValueError, match="unpacked package"):
        content_size([CONTENT_BUDGET, 1])


def test_raw_tar_boundary(tmp_path: Path) -> None:
    path = tmp_path / "archive.gz"
    data = b"a" * TAR_BUDGET
    path.write_bytes(gzip.compress(data))
    assert tar_bytes(path) == data
    path.write_bytes(gzip.compress(data + b"a"))
    with pytest.raises(ValueError, match="raw TAR"):
        tar_bytes(path)


def test_duplicate_insertion_retains_original() -> None:
    files: dict[str, bytes] = {}
    insert(files, "name", b"original")
    assert files == {"name": b"original"}
    with pytest.raises(ValueError, match="duplicate"):
        insert(files, "name", b"substitution")
    assert files == {"name": b"original"}


def zip_member(path: Path, name: str, mode: int, data: bytes) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        member = zipfile.ZipInfo(name)
        member.external_attr = mode << 16
        archive.writestr(member, data, compress_type=zipfile.ZIP_DEFLATED)


@pytest.mark.parametrize("mode", [0o644, stat.S_IFREG | 0o644])
def test_native_wheel_regular_types(tmp_path: Path, mode: int) -> None:
    path = tmp_path / "package.whl"
    zip_member(path, "empty", mode, b"")
    assert wheel_files(path) == {"empty": b""}


@pytest.mark.parametrize(
    ("name", "mode"),
    [("directory/", 0o644), ("link", stat.S_IFLNK | 0o644), ("file", 0o100755)],
)
def test_unsafe_wheel_members(tmp_path: Path, name: str, mode: int) -> None:
    path = tmp_path / "package.whl"
    zip_member(path, name, mode, b"target")
    with pytest.raises(ValueError):
        wheel_files(path)


def test_native_wheel_content_budget(tmp_path: Path) -> None:
    path = tmp_path / "package.whl"
    data = b"a" * CONTENT_BUDGET
    zip_member(path, "data", 0o100644, data)
    assert wheel_files(path) == {"data": data}
    zip_member(path, "data", 0o100644, data + b"a")
    with pytest.raises(ValueError, match="unpacked package"):
        wheel_files(path)


def tar_member(path: Path, member: tarfile.TarInfo, data: bytes) -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        member.size = len(data)
        archive.addfile(member, io.BytesIO(data))
    with tarfile.open(fileobj=io.BytesIO(buffer.getvalue()), mode="r:") as archive:
        assert archive.getmember(member.name).type == member.type
    path.write_bytes(gzip.compress(buffer.getvalue()))


def test_native_source_content_budget(tmp_path: Path) -> None:
    path = tmp_path / "package.tar.gz"
    member = tarfile.TarInfo("data")
    member.mode = 0o644
    data = b"a" * CONTENT_BUDGET
    tar_member(path, member, data)
    assert sdist_files(path) == {"data": data}
    tar_member(path, member, data + b"a")
    with pytest.raises(ValueError, match="unpacked package"):
        sdist_files(path)


@pytest.mark.parametrize("kind", ["directory", "symlink", "hardlink", "pax", "mode"])
def test_unsafe_source_members(tmp_path: Path, kind: str) -> None:
    member = tarfile.TarInfo("data")
    member.mode = 0o644
    types = {
        "directory": tarfile.DIRTYPE,
        "symlink": tarfile.SYMTYPE,
        "hardlink": tarfile.LNKTYPE,
    }
    member.type = types.get(kind, tarfile.REGTYPE)
    if kind == "pax":
        member.pax_headers = {"comment": "unexpected metadata"}
    if kind == "mode":
        member.mode = 0o755
    path = tmp_path / "package.tar.gz"
    tar_member(path, member, b"")
    with pytest.raises(ValueError):
        sdist_files(path)


def test_missing_native_file_object_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def omitted(_member: object) -> None:
        return None

    member = tarfile.TarInfo("data")
    member.mode = 0o644
    path = tmp_path / "package.tar.gz"
    tar_member(path, member, b"data")
    with tarfile.open(fileobj=io.BytesIO(tar_bytes(path)), mode="r:") as archive:
        monkeypatch.setattr(archive, "extractfile", omitted)
        with pytest.raises(ValueError, match="omitted a regular file"):
            sdist_member(archive, member, {})


def test_corrupt_native_archives_fail(tmp_path: Path) -> None:
    path = tmp_path / "archive"
    path.write_bytes(b"not a ZIP")
    with pytest.raises(zipfile.BadZipFile):
        wheel_files(path)
    with pytest.raises(gzip.BadGzipFile):
        sdist_files(path)
    path.write_bytes(gzip.compress(b"not a TAR"))
    with pytest.raises(tarfile.ReadError):
        sdist_files(path)


def test_native_duplicate_archives_fail(tmp_path: Path) -> None:
    path = tmp_path / "archive"
    with zipfile.ZipFile(path, "w") as archive:
        member = zipfile.ZipInfo("duplicate")
        member.external_attr = 0o100644 << 16
        archive.writestr(member, b"one")
        with pytest.warns(UserWarning, match="Duplicate name"):
            second = zipfile.ZipInfo("duplicate")
            second.external_attr = 0o100644 << 16
            archive.writestr(second, b"two")
    with pytest.raises(ValueError, match="duplicate"):
        wheel_files(path)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as source:
        tar_entry = tarfile.TarInfo("duplicate")
        tar_entry.mode = 0o644
        tar_entry.size = 3
        source.addfile(tar_entry, io.BytesIO(b"one"))
        source.addfile(tar_entry, io.BytesIO(b"two"))
    path.write_bytes(gzip.compress(buffer.getvalue()))
    with pytest.raises(ValueError, match="duplicate"):
        sdist_files(path)


@pytest.mark.parametrize(
    "kind", ["prefix", "trailer", "archive-comment", "member-comment", "extra"]
)
def test_noncanonical_zip_bytes_fail(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "package.whl"
    zip_member(path, "file", 0o100644, b"data")
    if kind == "prefix":
        path.write_bytes(b"hidden" + path.read_bytes())
    if kind == "trailer":
        path.write_bytes(path.read_bytes() + b"hidden")
    if kind == "archive-comment":
        with zipfile.ZipFile(path, "a") as archive:
            archive.comment = b"hidden"
    if kind in {"member-comment", "extra"}:
        annotated_zip(path, kind)
    with pytest.raises(ValueError):
        wheel_files(path)


def annotated_zip(path: Path, kind: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        member = zipfile.ZipInfo("file")
        member.external_attr = 0o100644 << 16
        if kind == "member-comment":
            member.comment = b"hidden"
        else:
            member.extra = b"\x01\x99\x04\x00data"
        archive.writestr(member, b"data")


@pytest.mark.parametrize(
    "kind", ["trailer", "padding", "partial-block", "missing-termination"]
)
def test_noncanonical_tar_bytes_fail(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "package.tar.gz"
    member = tarfile.TarInfo("file")
    member.mode = 0o644
    tar_member(path, member, b"data")
    data = bytearray(gzip.decompress(path.read_bytes()))
    if kind == "trailer":
        data[-512:] = b"x" * 512
    if kind == "padding":
        data[516] = 1
    if kind == "partial-block":
        data.pop()
    if kind == "missing-termination":
        del data[1024:]
    path.write_bytes(gzip.compress(data))
    with pytest.raises(ValueError, match="unaccounted bytes"):
        sdist_files(path)


def test_tar_header_gaps_and_exact_termination() -> None:
    member = tarfile.TarInfo("file")
    member.offset_data = 512
    member.size = 0
    tar_container(bytes(1536), [member])
    member.offset = 512
    with pytest.raises(ValueError, match="unaccounted header"):
        tar_container(bytes(2048), [member])
    tar_container(bytes(1024), [])
