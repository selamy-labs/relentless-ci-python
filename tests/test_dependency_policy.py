"""Complete-lock origin, digest and source-shape regression probes."""

import runpy
import shutil
from pathlib import Path

import pytest

from quality.dependency_policy import artifact, package, record, text, verify


def lock_root(tmp_path: Path) -> Path:
    """Copy real reviewed inputs so fixtures exercise the native UV schema."""
    for name in ("pyproject.toml", "uv.lock"):
        shutil.copy2(Path.cwd() / name, tmp_path / name)
    return tmp_path


def change(root: Path, old: str, new: str) -> None:
    """Make exactly one reviewable change to the complete lock graph."""
    path = root / "uv.lock"
    source = path.read_text()
    assert source.count(old) > 0
    path.write_text(source.replace(old, new, 1))


def test_complete_real_lock_passes(tmp_path: Path) -> None:
    assert verify(lock_root(tmp_path)) == (64, 65)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            'source = { registry = "https://pypi.org/simple" }',
            'source = { registry = "https://example.invalid/simple" }',
            "approved PyPI registry",
        ),
        (
            "https://files.pythonhosted.org/packages/",
            "https://example.invalid/packages/",
            "approved PyPI origin",
        ),
        ('hash = "sha256:', 'hash = "sha256:Z', "canonical SHA-256"),
        ("size = 24757", "size = 0", "positive size"),
        (
            'source = { editable = "." }',
            'source = { editable = "../other" }',
            "approved PyPI registry",
        ),
    ],
)
def test_changed_dependency_origin_or_integrity_fails(
    tmp_path: Path, old: str, new: str, message: str
) -> None:
    root = lock_root(tmp_path)
    change(root, old, new)
    with pytest.raises(ValueError, match=message):
        verify(root)


def test_missing_or_extra_editable_root_fails(tmp_path: Path) -> None:
    root = lock_root(tmp_path)
    source = (root / "uv.lock").read_text()
    root_block = 'source = { editable = "." }'
    assert source.count(root_block) == 1
    (root / "uv.lock").write_text(
        source.replace(root_block, 'source = { registry = "https://pypi.org/simple" }')
    )
    with pytest.raises(ValueError):
        verify(root)


def test_empty_lock_inventory_fails(tmp_path: Path) -> None:
    root = lock_root(tmp_path)
    (root / "uv.lock").write_text("version = 1\n")
    with pytest.raises(ValueError, match="inventory must be nonempty"):
        verify(root)


def test_duplicate_editable_root_fails(tmp_path: Path) -> None:
    root = lock_root(tmp_path)
    with (root / "uv.lock").open("a") as output:
        output.write(
            '\n[[package]]\nname = "relentless-ci-python"\n'
            'version = "0.1.0"\nsource = { editable = "." }\n'
        )
    with pytest.raises(ValueError, match="one editable project root"):
        verify(root)


def test_registered_main_runs_on_real_lock(capsys: pytest.CaptureFixture[str]) -> None:
    runpy.run_module("quality.dependency_policy_main", run_name="__main__")
    assert "approved dependency sources: (64, 65)" in capsys.readouterr().out


@pytest.mark.parametrize("value", [None, [], "text", 1])
def test_non_table_rejected(value: object) -> None:
    with pytest.raises(ValueError, match="table"):
        record(value)


@pytest.mark.parametrize("value", [None, "", 0, []])
def test_non_text_rejected(value: object) -> None:
    with pytest.raises(ValueError, match="nonempty text"):
        text(value)


@pytest.mark.parametrize(
    "url",
    [
        "http://files.pythonhosted.org/packages/a.whl",
        "https://files.pythonhosted.org.evil/packages/a.whl",
        "https://user@files.pythonhosted.org/packages/a.whl",
        "https://files.pythonhosted.org:443/packages/a.whl",
        "https://files.pythonhosted.org/other/a.whl",
        "https://files.pythonhosted.org/packages/a.zip",
        "https://files.pythonhosted.org/packages/a.whl?download=1",
        "https://files.pythonhosted.org/packages/a.whl#fragment",
    ],
)
def test_noncanonical_artifact_url_rejected(url: str) -> None:
    with pytest.raises(ValueError, match="approved PyPI origin"):
        artifact({"url": url, "hash": "sha256:" + "a" * 64, "size": 1})


@pytest.mark.parametrize("size", [0, -1, True, "1"])
def test_nonpositive_or_nonnumeric_size_rejected(size: object) -> None:
    with pytest.raises(ValueError, match="positive size"):
        artifact(
            {
                "url": "https://files.pythonhosted.org/packages/a.whl",
                "hash": "sha256:" + "a" * 64,
                "size": size,
            }
        )


def test_wheels_must_be_array() -> None:
    item: dict[str, object] = {
        "name": "dep",
        "version": "1",
        "source": {"registry": "https://pypi.org/simple"},
        "sdist": {
            "url": "https://files.pythonhosted.org/packages/a.tar.gz",
            "hash": "sha256:" + "a" * 64,
            "size": 1,
        },
        "wheels": {},
    }
    with pytest.raises(ValueError, match="wheels must be an array"):
        package(item, "project")
