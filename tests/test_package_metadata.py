"""Check package identity, Python support, pure-wheel tags and CSV hash inventory."""

import pytest

from quality.package_metadata import (
    identity,
    metadata,
    record_bytes,
    verify_record,
    wheel_metadata,
)
from tests.test_package_contents import META, PROJECT


def test_identity_normalizes_names_and_versions() -> None:
    assert (
        identity({"name": "Sample__Project.NAME", "version": "v1.0.0"})
        == "sample_project_name-1.0.0"
    )


@pytest.mark.parametrize(
    "field",
    [
        "Name",
        "Version",
        "Summary",
        "License-Expression",
        "License-File",
        "Requires-Python",
    ],
)
@pytest.mark.parametrize("kind", ["missing", "wrong", "duplicate"])
def test_metadata_corruption(field: str, kind: str) -> None:
    lines = META.decode().splitlines()
    original = next(line for line in lines if line.startswith(field + ":"))
    lines.remove(original)
    if kind == "wrong":
        lines.append(field + ": other")
    if kind == "duplicate":
        lines.extend([original, original])
    with pytest.raises(ValueError):
        metadata(("\n".join(lines) + "\n").encode(), PROJECT)


def test_runtime_dependencies_and_invalid_utf8_fail() -> None:
    with pytest.raises(ValueError, match="dependency-free"):
        metadata(META + b"Requires-Dist: undeclared\n", PROJECT)
    with pytest.raises(UnicodeDecodeError):
        metadata(META + b"X-Data: \xff\n", PROJECT)


def test_changed_valid_python_support_fails() -> None:
    with pytest.raises(ValueError, match="Python support differs"):
        metadata(META.replace(b"<3.15,>=3.11", b">=3.14"), PROJECT)


@pytest.mark.parametrize("field", ["Wheel-Version", "Root-Is-Purelib", "Tag"])
def test_wheel_format_corruption(field: str) -> None:
    values = {"Wheel-Version": "1.0", "Root-Is-Purelib": "true", "Tag": "py3-none-any"}
    values[field] = "wrong"
    with pytest.raises(ValueError, match="unsupported"):
        wheel_metadata(
            "\n".join(f"{key}: {value}" for key, value in values.items()).encode()
        )


def test_record_hashes_sizes_and_unique_complete_members() -> None:
    files = {"file": b"content", "empty": b"", "RECORD": b""}
    files["RECORD"] = record_bytes(files, "RECORD")
    verify_record(files, "RECORD")
    for value in (
        b"",
        files["RECORD"] * 2,
        b"file,sha256=wrong,7\nempty,,\nRECORD,,\n",
    ):
        corrupted = {**files, "RECORD": value}
        with pytest.raises(ValueError, match="RECORD differs"):
            verify_record(corrupted, "RECORD")
