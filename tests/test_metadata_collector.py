"""Collector endpoint and race probes against an independent native-shaped API."""

from copy import deepcopy
from dataclasses import FrozenInstanceError

import pytest

from quality.trusted_policy.metadata_collector import Policy, evaluate, repository_route
from quality.trusted_policy.metadata_pages import sequence
from quality.trusted_policy.review_policy import PolicyFailure
from tests.test_execution_policy import NAMES, jobs, workflow
from tests.test_review_policy import BASE, HEAD, commit, pull_request, review, role

REPOSITORY = "repos/owner/repo"
PR = REPOSITORY + "/pulls/1"
RUN = REPOSITORY + "/actions/runs/1"


def policy() -> Policy:
    return Policy("owner/repo", 1, HEAD, BASE, 2, 1, frozenset(NAMES))


def test_reviewed_policy_is_immutable_during_native_evaluation() -> None:
    value = policy()
    field = "head"
    with pytest.raises(FrozenInstanceError):
        setattr(value, field, BASE)


class NativeAPI:
    def __init__(self, values: dict[str, list[object]]) -> None:
        self.values = values
        self.routes: list[str] = []

    def __call__(self, endpoint: str) -> object:
        self.routes.append(endpoint)
        values = self.values[endpoint]
        return deepcopy(values.pop(0) if len(values) > 1 else values[0])


def source() -> dict[str, list[object]]:
    return {
        PR: [pull_request()],
        PR + "/commits?per_page=100&page=1": [[commit()]],
        PR + "/commits?per_page=100&page=2": [[]],
        PR + "/reviews?per_page=100&page=1": [[review()]],
        PR + "/reviews?per_page=100&page=2": [[]],
        REPOSITORY + "/collaborators/user-2/permission": [role()],
        RUN: [workflow()],
        RUN
        + "/attempts/3/jobs?per_page=100&page=1": [{"total_count": 3, "jobs": jobs()}],
        RUN + "/attempts/3/jobs?per_page=100&page=2": [{"total_count": 3, "jobs": []}],
    }


def test_complete_native_collection_evaluates_current_approved_candidate() -> None:
    api = NativeAPI(source())

    assert evaluate(api, policy()) == 2
    assert api.routes.count(PR) == 2
    assert api.routes.count(RUN) == 2
    assert api.routes.count(PR + "/reviews?per_page=100&page=2") == 2


@pytest.mark.parametrize("head", [BASE, None, "not-a-commit"])
def test_run_must_match_current_native_head(head: object) -> None:
    values = source()
    changed = pull_request()
    changed["head"] = {"sha": head}
    values[PR] = [changed]
    with pytest.raises(PolicyFailure):
        evaluate(NativeAPI(values), policy())


@pytest.mark.parametrize(
    "field,value", [("number", 2), ("head", {"sha": BASE}), ("base", {"sha": HEAD})]
)
def test_run_must_be_associated_with_current_pr(field: str, value: object) -> None:
    values = source()
    changed = workflow()
    association: dict[str, object] = {
        "number": 1,
        "head": {"sha": HEAD},
        "base": {"sha": BASE},
    }
    association[field] = value
    changed["pull_requests"] = [association]
    values[RUN] = [changed]
    with pytest.raises(PolicyFailure, match="associated"):
        evaluate(NativeAPI(values), policy())


def test_run_with_multiple_pr_associations_cannot_qualify() -> None:
    values = source()
    changed = workflow()
    associations = sequence(changed["pull_requests"])
    associations.append(associations[0])
    values[RUN] = [changed]
    with pytest.raises(PolicyFailure, match="associated"):
        evaluate(NativeAPI(values), policy())


def test_test_merge_change_during_collection_fails() -> None:
    values = source()
    changed = pull_request()
    changed["merge_commit_sha"] = HEAD
    values[PR] = [pull_request(), changed]
    with pytest.raises(PolicyFailure, match="candidate metadata changed"):
        evaluate(NativeAPI(values), policy())


@pytest.mark.parametrize(
    "repository",
    ["../repo", "owner/repo?x=1", "a/b/c", "a b/r", "https://evil/repo", "a/.", "a/.."],
)
def test_repository_identity_cannot_redirect_native_reads(repository: str) -> None:
    with pytest.raises(PolicyFailure):
        repository_route(repository)


@pytest.mark.parametrize("field,value", [("state", "closed"), ("commits", 2)])
def test_candidate_readback_changes_fail(field: str, value: object) -> None:
    values = source()
    changed = pull_request()
    changed[field] = value
    values[PR] = [pull_request(), changed]

    with pytest.raises(PolicyFailure):
        evaluate(NativeAPI(values), policy())


def test_review_revocation_during_collection_fails() -> None:
    values = source()
    values[PR + "/reviews?per_page=100&page=1"] = [
        [review()],
        [review(state="DISMISSED")],
    ]

    with pytest.raises(PolicyFailure, match="review inventory changed"):
        evaluate(NativeAPI(values), policy())


def test_workflow_attempt_change_during_collection_fails() -> None:
    values = source()
    changed = workflow()
    changed["run_attempt"] = 4
    values[RUN] = [workflow(), changed]

    with pytest.raises(PolicyFailure, match="workflow run changed"):
        evaluate(NativeAPI(values), policy())


def test_unsafe_reviewer_login_cannot_create_arbitrary_endpoint() -> None:
    values = source()
    changed = review()
    changed["user"] = {"id": 2, "login": "user-2/../attacker"}
    values[PR + "/reviews?per_page=100&page=1"] = [[changed]]

    with pytest.raises(PolicyFailure, match="safe path"):
        evaluate(NativeAPI(values), policy())


def test_truncated_commit_inventory_does_not_authorize_approval() -> None:
    values = source()
    values[PR + "/commits?per_page=100&page=1"] = [[]]

    with pytest.raises(PolicyFailure, match="commit inventory"):
        evaluate(NativeAPI(values), policy())


def test_removed_maintainer_role_during_collection_fails() -> None:
    values = source()
    values[REPOSITORY + "/collaborators/user-2/permission"] = [
        role(),
        role(name="read"),
    ]

    with pytest.raises(PolicyFailure, match="roles changed"):
        evaluate(NativeAPI(values), policy())
