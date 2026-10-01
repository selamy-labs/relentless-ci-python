"""Missing, skipped, cancelled, forged and stale native execution cannot pass."""

import json

import pytest

from quality.trusted_policy.execution_policy import (
    associated_pull,
    associated_run,
    job_identity,
    require_matrix,
    verify_run,
)
from quality.trusted_policy.review_policy import PolicyFailure, record

HEAD = "a" * 40
BASE = "b" * 40


def mapping(value: object) -> dict[str, object]:
    return record(value)


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


@pytest.mark.parametrize("candidate", [299, 301])
def test_run_and_job_ids_require_exact_numeric_identity(candidate: int) -> None:
    run = {**workflow(), "id": 300, "workflow_id": 300, "run_attempt": 300}
    required_job = {**mapping(jobs()[0]), "run_id": 300, "run_attempt": 300}
    with pytest.raises(PolicyFailure):
        verify_run({**run, "workflow_id": candidate}, 300, HEAD)
    with pytest.raises(PolicyFailure):
        job_identity({**required_job, "run_id": candidate}, run)
    with pytest.raises(PolicyFailure):
        job_identity({**required_job, "run_attempt": candidate}, run)


@pytest.mark.parametrize("candidate", ["0" * 40, "f" * 40])
def test_run_and_job_heads_require_exact_digest(candidate: str) -> None:
    run = workflow()
    with pytest.raises(PolicyFailure):
        verify_run({**run, "head_sha": candidate}, 2, HEAD)
    with pytest.raises(PolicyFailure):
        job_identity({**mapping(jobs()[0]), "head_sha": candidate}, run)


@pytest.mark.parametrize("candidate", [299, 301])
def test_native_pr_association_rejects_both_number_directions(candidate: int) -> None:
    run = workflow()
    run["pull_requests"] = [
        {"number": candidate, "head": {"sha": HEAD}, "base": {"sha": BASE}}
    ]
    assert not associated_pull(run, 300, HEAD, BASE)


def test_native_pr_association_needs_exactly_one_candidate() -> None:
    run = workflow()
    run["pull_requests"] = []
    assert not associated_pull(run, 1, HEAD, BASE)
    run["pull_requests"] = [
        {"number": 1, "head": {"sha": HEAD}, "base": {"sha": BASE}}
    ] * 2
    assert not associated_pull(run, 1, HEAD, BASE)


@pytest.mark.parametrize("field", ["head", "base"])
@pytest.mark.parametrize("candidate", ["0" * 40, "f" * 40])
def test_native_pr_association_rejects_both_digest_directions(
    field: str, candidate: str
) -> None:
    run = workflow()
    pull = {"number": 1, "head": {"sha": HEAD}, "base": {"sha": BASE}}
    pull[field] = {"sha": candidate}
    run["pull_requests"] = [pull]
    assert not associated_pull(run, 1, HEAD, BASE)


def test_unassociated_fork_run_rejects_both_identity_directions() -> None:
    run: dict[str, object] = {
        **workflow(),
        "pull_requests": [],
        "head_branch": "feature",
    }
    run["head_repository"] = {"id": 300, "full_name": "owner/repo"}
    pull: dict[str, object] = {
        "number": 300,
        "base": {"sha": BASE},
        "head": {
            "sha": HEAD,
            "ref": "feature",
            "repo": {"id": 300, "full_name": "owner/repo"},
        },
    }
    assert associated_run(run, pull, 300, HEAD, BASE)
    head = mapping(pull["head"])
    for candidate in (299, 301):
        assert not associated_run(run, {**pull, "number": candidate}, 300, HEAD, BASE)
        changed_head = {
            **head,
            "repo": {"id": candidate, "full_name": "owner/repo"},
        }
        assert not associated_run(run, {**pull, "head": changed_head}, 300, HEAD, BASE)
    for alternate_sha in ("0" * 40, "f" * 40):
        assert not associated_run(
            run, {**pull, "base": {"sha": alternate_sha}}, 300, HEAD, BASE
        )
        assert not associated_run(
            run, {**pull, "head": {**head, "sha": alternate_sha}}, 300, HEAD, BASE
        )
    for alternate_name in ("alpha", "zulu"):
        assert not associated_run(
            run, {**pull, "head": {**head, "ref": alternate_name}}, 300, HEAD, BASE
        )
        assert not associated_run(
            run,
            {
                **pull,
                "head": {**head, "repo": {"id": 300, "full_name": alternate_name}},
            },
            300,
            HEAD,
            BASE,
        )


def fresh(value: str) -> str:
    return "".join((value[: len(value) // 2], value[len(value) // 2 :]))


def test_equal_native_values_do_not_need_shared_python_objects() -> None:
    run = {**workflow(), "id": int("300"), "workflow_id": int("300")}
    run["run_attempt"] = int("300")
    run["head_sha"] = fresh(HEAD)
    assert verify_run(run, int("300"), fresh(HEAD)) == run
    job = {
        **mapping(jobs()[0]),
        "run_id": int("300"),
        "run_attempt": int("300"),
        "head_sha": fresh(HEAD),
    }
    assert job_identity(job, run)[0] == 1
    pull = {
        "number": int("300"),
        "head": {"sha": fresh(HEAD)},
        "base": {"sha": fresh(BASE)},
    }
    assert associated_pull({"pull_requests": [pull]}, int("300"), HEAD, BASE)
    fork_run: dict[str, object] = {"pull_requests": [], "head_branch": fresh("feature")}
    fork_run["head_repository"] = {"id": int("300"), "full_name": fresh("owner/repo")}
    candidate = {
        "number": int("300"),
        "base": {"sha": fresh(BASE)},
        "head": {
            "sha": fresh(HEAD),
            "ref": fresh("feature"),
            "repo": {"id": int("300"), "full_name": fresh("owner/repo")},
        },
    }
    assert associated_run(fork_run, candidate, int("300"), HEAD, BASE)


def test_native_job_count_must_equal_the_declared_matrix() -> None:
    expected = {"first", "second"}
    items = [
        {
            "id": index,
            "run_id": 1,
            "run_attempt": 3,
            "head_sha": HEAD,
            "name": name,
            "status": "completed",
            "conclusion": "success",
        }
        for index, name in enumerate(sorted(expected), 1)
    ]
    require_matrix(workflow(), items, 2, HEAD, expected, 2, True)
    for native_count in (1, 3):
        with pytest.raises(PolicyFailure, match="incomplete"):
            require_matrix(workflow(), items, 2, HEAD, expected, native_count, True)


def test_complete_flag_requires_literal_boolean_true() -> None:
    with pytest.raises(PolicyFailure, match="complete"):
        require_matrix(workflow(), jobs(), 2, HEAD, NAMES, 3, json.loads("1"))


def test_large_paginated_job_inventory_uses_numeric_value_equality() -> None:
    expected = {f"Required job {index}" for index in range(300)}
    items = [
        {
            "id": index + 1,
            "run_id": 1,
            "run_attempt": 3,
            "head_sha": HEAD,
            "name": f"Required job {index}",
            "status": "completed",
            "conclusion": "success",
        }
        for index in range(300)
    ]
    require_matrix(workflow(), items, 2, HEAD, expected, int("300"), True)
