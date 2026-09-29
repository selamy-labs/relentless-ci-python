"""Incomplete or stale cleanup evidence never turns tool failure into success."""

import json
import subprocess
from pathlib import Path

import pytest

from quality.owned_process import Cleanup, Completion
from quality.owned_receipt import (
    boolean,
    cleanup,
    integer,
    no_duplicate_keys,
    parse_completion,
    positive_pid,
    positive_timeout,
    read_completion,
    reaped_pair,
    require_success,
)


def complete() -> dict[str, object]:
    return {
        "nonce": "fresh",
        "returncode": 0,
        "timed_out": False,
        "cleanup": {"killed": [], "reaped": []},
    }


@pytest.mark.parametrize("value", [True, False, None, "1", 1.5])
def test_integer_fields_do_not_coerce_json_values(value: object) -> None:
    with pytest.raises(ValueError, match="integer field"):
        integer(value)


@pytest.mark.parametrize("value", [-1000, -1, 0, 1, 257])
def test_signed_integer_values_are_retained(value: int) -> None:
    assert integer(value) == value


@pytest.mark.parametrize("value", [0, -1, -123, False])
def test_pid_fields_cannot_be_group_selectors(value: object) -> None:
    with pytest.raises(ValueError):
        positive_pid(value)


def test_positive_pid_and_exact_boolean_fields() -> None:
    assert positive_pid(257) == 257
    assert positive_pid(1) == 1
    assert boolean(True) is True
    assert boolean(False) is False
    for value in [0, 1, "false", None]:
        with pytest.raises(ValueError, match="boolean field"):
            boolean(value)


@pytest.mark.parametrize(
    "timeout", [0, -1, True, float("inf"), float("-inf"), float("nan")]
)
def test_invalid_deadlines_fail_before_any_launch(timeout: float) -> None:
    with pytest.raises(ValueError, match="positive and finite"):
        positive_timeout(timeout)


@pytest.mark.parametrize("timeout", [0.001, 1, 3600])
def test_finite_positive_deadline_is_preserved(timeout: float) -> None:
    positive_timeout(timeout)


@pytest.mark.parametrize("value", [[], [1], [1, 2, 3], {}, [0, -9], [12, True]])
def test_reaping_record_requires_positive_pid_and_exact_signed_status(
    value: object,
) -> None:
    with pytest.raises(ValueError):
        reaped_pair(value)


def test_complete_reaping_retains_negative_and_positive_outcomes() -> None:
    assert reaped_pair([257, -15]) == (257, -15)
    assert cleanup({"killed": [12, 12, 13], "reaped": [[13, 3], [12, -9]]}) == Cleanup(
        [12, 12, 13], [(13, 3), (12, -9)]
    )


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"killed": []},
        {"killed": [], "reaped": [], "extra": 1},
        {"killed": [12], "reaped": []},
        {"killed": [], "reaped": [[12, 0], [12, -9]]},
        {"killed": [12], "reaped": [[13, -9]]},
    ],
)
def test_missing_duplicate_or_unreaped_cleanup_fails(value: object) -> None:
    with pytest.raises(ValueError):
        cleanup(value)


def test_fresh_nonce_and_complete_schema_bind_receipt_to_one_run() -> None:
    assert parse_completion(complete(), "fresh") == Completion(
        0, False, Cleanup([], [])
    )
    for value in [
        None,
        {},
        {**complete(), "extra": True},
        {**complete(), "nonce": "stale"},
        {**complete(), "nonce": "early"},
        {**complete(), "returncode": True},
    ]:
        with pytest.raises(ValueError):
            parse_completion(value, "fresh")


def test_missing_corrupt_duplicate_key_and_stale_file_cannot_pass(
    tmp_path: Path,
) -> None:
    path = tmp_path / "receipt.json"
    with pytest.raises(FileNotFoundError):
        read_completion(path, "fresh")
    for text in [
        "bad JSON",
        '{"nonce":"fresh","nonce":"fresh"}',
        json.dumps({**complete(), "nonce": "old"}),
        json.dumps({**complete(), "nonce": "early"}),
    ]:
        path.write_text(text)
        with pytest.raises(ValueError):
            read_completion(path, "fresh")
    path.write_text(json.dumps(complete()))
    assert read_completion(path, "fresh") == Completion(0, False, Cleanup([], []))
    assert no_duplicate_keys([("one", 1), ("two", 2)]) == {"one": 1, "two": 2}


@pytest.mark.parametrize("status", [-15, -1, 1, 3])
def test_every_signed_nonzero_tool_exit_fails(status: int) -> None:
    with pytest.raises(subprocess.CalledProcessError) as error:
        require_success(Completion(status, False, Cleanup([], [])), ["tool"], 7)
    assert error.value.returncode == status
    assert error.value.cmd == ["tool"]


def test_timeout_is_failure_even_with_zero_status_or_complete_reaping() -> None:
    with pytest.raises(subprocess.TimeoutExpired) as error:
        require_success(Completion(0, True, Cleanup([], [])), ["tool"], 7)
    assert error.value.cmd == ["tool"]
    assert error.value.timeout == 7


def test_clean_tool_passes_and_success_with_resource_leak_fails() -> None:
    require_success(Completion(0, False, Cleanup([], [])), ["tool"], 7)
    with pytest.raises(RuntimeError, match="leaked owned descendants"):
        require_success(Completion(0, False, Cleanup([12], [(12, -9)])), ["tool"], 7)


def test_large_unique_reaped_inventory_passes_without_identity_assumptions() -> None:
    pids = list(range(1, 258))
    records = [[pid, -9] for pid in pids]

    assert cleanup({"killed": pids, "reaped": records}) == Cleanup(
        pids, [(pid, -9) for pid in pids]
    )
