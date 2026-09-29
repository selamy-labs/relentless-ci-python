"""Independent policy values and native boundaries prevent coupled test oracles."""

import gzip
import io
import stat
import tarfile
from pathlib import Path

import pytest

from quality import package_archive
from quality.package_contents import source_bytes
from quality.package_metadata import record_bytes, verify_record, wheel_metadata
from tests.test_package_archive import tar_member, zip_member


class ReadTrace(io.BytesIO):
    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.requests: list[int | None] = []

    def read(self, size: int | None = -1, /) -> bytes:
        self.requests.append(size)
        return super().read(size)


def test_compressed_allocation_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reader = ReadTrace(bytes(65538))

    def opened(_path: Path, mode: str) -> ReadTrace:
        assert mode == "rb"
        return reader

    monkeypatch.setattr(Path, "open", opened)
    with pytest.raises(ValueError, match="compressed package"):
        package_archive.compressed(tmp_path / "archive")
    assert reader.requests == [65537]


def test_expanded_allocation_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "archive.gz"
    packed = gzip.compress(b"native input")
    path.write_bytes(packed)
    reader = ReadTrace(bytes(524290))

    def expanded(fileobj: io.BytesIO) -> ReadTrace:
        assert fileobj.getvalue() == packed
        return reader

    monkeypatch.setattr(gzip, "GzipFile", expanded)
    with pytest.raises(ValueError, match="raw TAR"):
        package_archive.tar_bytes(path)
    assert reader.requests == [524289]


@pytest.mark.parametrize("size", [511, 512, 513, 1023, 1024, 1025])
def test_native_tar_block_boundaries(tmp_path: Path, size: int) -> None:
    path = tmp_path / "package.tar.gz"
    member = tarfile.TarInfo("data")
    member.mode = 0o644
    data = b"a" * size
    tar_member(path, member, data)
    assert package_archive.sdist_files(path) == {"data": data}


@pytest.mark.parametrize("mode", [0, 0o640, 0o755])
def test_source_permissions_reject_both_directions(tmp_path: Path, mode: int) -> None:
    path = tmp_path / "package.tar.gz"
    member = tarfile.TarInfo("data")
    member.mode = mode
    tar_member(path, member, b"data")
    with pytest.raises(ValueError, match="permissions differ"):
        package_archive.sdist_files(path)


@pytest.mark.parametrize("mode", [0, 0o640, 0o755])
def test_wheel_permissions_reject_both_directions(tmp_path: Path, mode: int) -> None:
    path = tmp_path / "package.whl"
    zip_member(path, "data", stat.S_IFREG | mode, b"data")
    with pytest.raises(ValueError, match="permissions differ"):
        package_archive.wheel_files(path)


def test_one_termination_block_after_an_empty_file_fails(tmp_path: Path) -> None:
    path = tmp_path / "package.tar.gz"
    member = tarfile.TarInfo("empty")
    member.mode = 0o644
    tar_member(path, member, b"")
    raw = gzip.decompress(path.read_bytes())
    path.write_bytes(gzip.compress(raw[:1536]))
    assert package_archive.sdist_files(path) == {"empty": b""}
    path.write_bytes(gzip.compress(raw[:1024]))
    with pytest.raises(ValueError, match="termination"):
        package_archive.sdist_files(path)


def test_two_native_members_include_a_half_record_header_offset(tmp_path: Path) -> None:
    path = tmp_path / "package.tar.gz"
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as archive:
        empty = tarfile.TarInfo("empty")
        empty.mode = 0o644
        archive.addfile(empty, io.BytesIO())
        data = tarfile.TarInfo("data")
        data.mode = 0o644
        data.size = 4
        archive.addfile(data, io.BytesIO(b"data"))
    path.write_bytes(gzip.compress(raw.getvalue()))
    assert package_archive.sdist_files(path) == {"empty": b"", "data": b"data"}


@pytest.mark.parametrize("offset_data", [0, 1024])
def test_native_header_metadata_requires_exactly_one_block(offset_data: int) -> None:
    member = tarfile.TarInfo("data")
    member.offset = 0
    member.offset_data = offset_data
    with pytest.raises(ValueError, match="extended header"):
        package_archive.tar_member_end(bytes(2048), member, 0)


@pytest.mark.parametrize("offset", [0, 512, 1024])
def test_each_termination_block_must_be_zero(offset: int) -> None:
    tail = bytearray(1536)
    tail[offset] = 1
    with pytest.raises(ValueError, match="termination"):
        package_archive.tar_container(bytes(tail), [])


def test_native_gnu_extension_header_is_not_a_public_member(tmp_path: Path) -> None:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.GNU_FORMAT) as archive:
        header = tarfile.TarInfo("././@LongLink")
        header.type = tarfile.GNUTYPE_LONGNAME
        name = b"data\x00"
        header.size = len(name)
        archive.addfile(header, io.BytesIO(name))
        member = tarfile.TarInfo("placeholder")
        member.mode = 0o644
        member.size = 4
        archive.addfile(member, io.BytesIO(b"data"))
    path = tmp_path / "package.tar.gz"
    path.write_bytes(gzip.compress(raw.getvalue()))
    with pytest.raises(ValueError, match="extended header"):
        package_archive.sdist_files(path)


def test_native_tar_termination_exactly_two_blocks_and_one_short(
    tmp_path: Path,
) -> None:
    path = tmp_path / "package.tar.gz"
    member = tarfile.TarInfo("data")
    member.mode = 0o644
    tar_member(path, member, bytes(512))
    data = gzip.decompress(path.read_bytes())
    path.write_bytes(gzip.compress(data[:2048]))
    assert package_archive.sdist_files(path) == {"data": bytes(512)}
    path.write_bytes(gzip.compress(data[:1536]))
    with pytest.raises(ValueError, match="termination"):
        package_archive.sdist_files(path)


def test_overlapping_native_header_metadata_fails() -> None:
    member = tarfile.TarInfo("data")
    member.offset = 0
    member.offset_data = 512
    with pytest.raises(ValueError, match="unaccounted header"):
        package_archive.tar_member_end(bytes(2048), member, 512)


@pytest.mark.parametrize("prefix", [b"!hidden", b"zzhidden"])
def test_zip_container_rejects_both_byte_order_directions(
    tmp_path: Path, prefix: bytes
) -> None:
    path = tmp_path / "package.whl"
    zip_member(path, "file", 0o100644, b"data")
    path.write_bytes(prefix + path.read_bytes())
    with pytest.raises(ValueError, match="noncanonical"):
        package_archive.wheel_files(path)


@pytest.mark.parametrize("data", [b"a", b"z"])
def test_source_substitutions_reject_both_byte_order_directions(data: bytes) -> None:
    with pytest.raises(ValueError, match="source"):
        source_bytes({"file": data}, {"file": b"middle"})


@pytest.mark.parametrize("field", ["Wheel-Version", "Root-Is-Purelib", "Tag"])
def test_missing_wheel_header_is_not_a_compatibility_declaration(field: str) -> None:
    values = {"Wheel-Version": "1.0", "Root-Is-Purelib": "true", "Tag": "py3-none-any"}
    del values[field]
    with pytest.raises(ValueError, match="unsupported"):
        wheel_metadata(
            "\n".join(f"{key}: {value}" for key, value in values.items()).encode()
        )


def test_record_matches_independent_known_digests_and_csv_bytes() -> None:
    files = {"A": b"content", "empty": b"", "RECORD": b""}
    golden = (
        b"A,sha256=7XACtDnprIRfIjV9giusFERzD722AW0-yUMil7nsn3M,7\n"
        b"empty,sha256=47DEQpj8HBSa-_TImW-5JCeuQeRkm5NMpJWZG3hSuFU,0\n"
        b"RECORD,,\n"
    )
    assert record_bytes(files, "RECORD") == golden
    files["RECORD"] = golden
    verify_record(files, "RECORD")
