"""Native safe YAML and JSON parsing reject ambiguous policy representations."""

from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from yaml.nodes import ScalarNode

from quality.runtime_data import YAML_STRING_TAG, mapping_key, read_json, read_yaml


@pytest.mark.parametrize(
    "source",
    [
        "",
        "a: 1\na: 2\n",
        "outer: {a: 1, a: 2}",
        "1: value",
        "2026-09-29: value",
        "? [a, b]\n: value",
        "a: &branch [3.11]\nb: *branch",
        "a: &unused 1",
        "---\na: 1\n---\nb: 2",
        "a: [",
        "a: !!python/object:object {}",
        "a: &cycle [*cycle]",
    ],
)
def test_invalid_or_ambiguous_yaml_fails(tmp_path: Path, source: str) -> None:
    path = tmp_path / "policy.yml"
    path.write_text(source)
    with pytest.raises((ValueError, yaml.YAMLError)):
        read_yaml(path)


def test_real_yaml_collections_and_strings_are_retained(tmp_path: Path) -> None:
    path = tmp_path / "policy.yml"
    path.write_text('jobs:\n  a: {versions: ["3.11", "3.12"], enabled: true}\n')
    assert read_yaml(path) == {
        "jobs": {"a": {"versions": ["3.11", "3.12"], "enabled": True}}
    }


@pytest.mark.parametrize("source", ['{"a": 1, "a": 2}', '{"a": {"b": 1, "b": 2}}'])
def test_duplicate_json_keys_fail(tmp_path: Path, source: str) -> None:
    path = tmp_path / "policy.json"
    path.write_text(source)
    with pytest.raises(ValueError, match="duplicate"):
        read_json(path)


def test_json_nested_values_are_preserved(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    path.write_text('{"a": [1, null, {"b": true}]}')
    assert read_json(path) == {"a": [1, None, {"b": True}]}


@pytest.mark.parametrize("reader", [read_json, read_yaml])
def test_invalid_utf8_is_not_repaired(
    tmp_path: Path, reader: Callable[[Path], object]
) -> None:
    path = tmp_path / "policy"
    path.write_bytes(b"\xff")
    with pytest.raises(UnicodeDecodeError):
        reader(path)


@pytest.mark.parametrize("tag", [YAML_STRING_TAG, YAML_STRING_TAG.encode().decode()])
def test_native_string_node_tag_uses_value_equality(tag: str) -> None:
    node = ScalarNode(tag, "jobs")
    assert mapping_key(node) == "jobs"
