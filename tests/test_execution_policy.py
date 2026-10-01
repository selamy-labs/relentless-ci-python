"""Missing, skipped, cancelled, forged and stale native execution cannot pass."""

import pytest

from quality.trusted_policy.execution_policy import require_matrix
from quality.trusted_policy.review_policy import PolicyFailure

HEAD = "a" * 40
BASE = "b" * 40
NAMES = {
    "Full analysis (Python 3.11)",
    "Installed behavior (Linux, Python 3.11)",
    "Relentless CI gate",
}


def workflow() -> dict[str, object]:
    return {
        "id": 1,
        "workflow_id": 2,
        "run_attempt": 3,
        "head_sha": HEAD,
        "event": "pull_request",
        "status": "completed",
        "conclusion": "success",
        "pull_requests": [{"number": 1, "head": {"sha": HEAD}, "base": {"sha": BASE}}],
    }


def jobs() -> list[object]:
    return [
        {
            "id": index,
            "run_id": 1,
            "run_attempt": 3,
            "head_sha": HEAD,
            "name": name,
            "status": "completed",
            "conclusion": "success",
        }
        for index, name in enumerate(sorted(NAMES), 1)
    ]


def test_complete_current_workflow_matrix_passes() -> None:
    require_matrix(workflow(), jobs(), 2, HEAD, NAMES, 3, True)


@pytest.mark.parametrize(
    "field,value",
    [
        ("workflow_id", 99),
        ("head_sha", BASE),
        ("event", "workflow_dispatch"),
        ("status", "queued"),
        ("status", "in_progress"),
        ("conclusion", "skipped"),
        ("conclusion", "cancelled"),
        ("conclusion", None),
        ("conclusion", "failure"),
    ],
)
def test_unrelated_or_unfinished_run_fails(field: str, value: object) -> None:
    with pytest.raises(PolicyFailure):
        require_matrix({**workflow(), field: value}, jobs(), 2, HEAD, NAMES, 3, True)


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_id", 99),
        ("run_attempt", 2),
        ("head_sha", BASE),
        ("status", "queued"),
        ("conclusion", "skipped"),
        ("conclusion", "cancelled"),
        ("conclusion", "failure"),
        ("conclusion", None),
        ("name", "forged gate"),
    ],
)
def test_each_job_must_be_current_and_successful(field: str, value: object) -> None:
    items = jobs()
    first = items[0]
    assert isinstance(first, dict)
    items[0] = {**first, field: value}
    with pytest.raises(PolicyFailure):
        require_matrix(workflow(), items, 2, HEAD, NAMES, 3, True)


def test_missing_unexpected_and_duplicate_jobs_fail() -> None:
    for items, total in [(jobs()[:-1], 3), (jobs()[:-1], 2), (jobs() + [jobs()[0]], 4)]:
        with pytest.raises(PolicyFailure):
            require_matrix(workflow(), items, 2, HEAD, NAMES, total, True)


@pytest.mark.parametrize("field", ["id", "name"])
def test_duplicate_identity_or_name_independently_fails(field: str) -> None:
    items = jobs()
    first, second = items[:2]
    assert isinstance(first, dict) and isinstance(second, dict)
    items[1] = {**second, field: first[field]}
    with pytest.raises(PolicyFailure, match="duplicate"):
        require_matrix(workflow(), items, 2, HEAD, NAMES, 3, True)


def test_partial_or_empty_policy_cannot_pass() -> None:
    with pytest.raises(PolicyFailure, match="complete"):
        require_matrix(workflow(), jobs(), 2, HEAD, NAMES, 3, False)
    with pytest.raises(PolicyFailure, match="complete"):
        require_matrix(workflow(), [], 2, HEAD, set(), 0, True)
