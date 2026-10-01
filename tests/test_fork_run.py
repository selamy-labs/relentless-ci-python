"""Empty native PR associations recover only a unique exact fork identity."""

from collections.abc import Sequence
from copy import deepcopy

import pytest

from quality.trusted_policy.fork_run import unique_pull
from quality.trusted_policy.review_policy import PolicyFailure
from tests.test_metadata_collector import REPOSITORY, NativeAPI
from tests.test_review_policy import BASE, HEAD

PAGE1 = REPOSITORY + "/pulls?per_page=100&page=1"
PAGE2 = REPOSITORY + "/pulls?per_page=100&page=2"


def run() -> dict[str, object]:
    return {
        "id": 77,
        "workflow_id": 2,
        "event": "pull_request",
        "status": "completed",
        "head_sha": HEAD,
        "head_branch": "feature",
        "head_repository": {"id": 99, "full_name": "contributor/copy"},
        "pull_requests": [],
    }


def pull(number: int = 1) -> dict[str, object]:
    return {
        "number": number,
        "state": "open",
        "head": {
            "sha": HEAD,
            "ref": "feature",
            "repo": {"id": 99, "full_name": "contributor/copy"},
        },
        "base": {"sha": BASE},
    }


def api(pulls: Sequence[object]) -> NativeAPI:
    return NativeAPI({PAGE1: [list(pulls)], PAGE2: [[]]})


def test_unique_exact_fork_pr_is_resolved_from_complete_native_list() -> None:
    native = api([pull()])
    assert unique_pull(native, REPOSITORY, run(), 77, 2, BASE) == 1
    assert native.routes == [PAGE1, PAGE2]


@pytest.mark.parametrize(
    "field,value",
    [
        ("state", "closed"),
        ("base", {"sha": HEAD}),
        (
            "head",
            {
                "sha": BASE,
                "ref": "feature",
                "repo": {"id": 99, "full_name": "contributor/copy"},
            },
        ),
        (
            "head",
            {
                "sha": HEAD,
                "ref": "other",
                "repo": {"id": 99, "full_name": "contributor/copy"},
            },
        ),
        (
            "head",
            {
                "sha": HEAD,
                "ref": "feature",
                "repo": {"id": 100, "full_name": "contributor/copy"},
            },
        ),
        (
            "head",
            {
                "sha": HEAD,
                "ref": "feature",
                "repo": {"id": 99, "full_name": "other/copy"},
            },
        ),
    ],
)
def test_other_pr_cannot_supply_fork_identity(field: str, value: object) -> None:
    candidate = pull()
    candidate[field] = value
    with pytest.raises(PolicyFailure, match="exactly one"):
        unique_pull(api([candidate]), REPOSITORY, run(), 77, 2, BASE)


def test_ambiguous_or_absent_fork_identity_fails_closed() -> None:
    for candidates in ([], [pull(1), pull(2)]):
        with pytest.raises(PolicyFailure, match="exactly one"):
            unique_pull(api(candidates), REPOSITORY, run(), 77, 2, BASE)


@pytest.mark.parametrize(
    "field,value",
    [("id", 78), ("workflow_id", 3), ("event", "push"), ("status", "in_progress")],
)
def test_run_identity_must_be_current_and_completed(field: str, value: object) -> None:
    changed = deepcopy(run())
    changed[field] = value
    with pytest.raises(PolicyFailure, match="native completed"):
        unique_pull(api([pull()]), REPOSITORY, changed, 77, 2, BASE)


def test_incomplete_pull_pagination_fails_closed() -> None:
    native = NativeAPI({PAGE1: [[pull() for _ in range(101)]]})
    with pytest.raises(PolicyFailure):
        unique_pull(native, REPOSITORY, run(), 77, 2, BASE)
