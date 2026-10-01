"""Native run resolution must bind comments to the current PR head and base."""

from copy import deepcopy
from dataclasses import FrozenInstanceError

import pytest

from quality.trusted_policy.issuer_resolution import (
    ReviewedPolicy,
    matching_run,
    resolve,
)
from quality.trusted_policy.review_policy import PolicyFailure
from quality.trusted_policy.trusted_event import Trigger

ROOT = "repos/owner/repo"
HEAD = "a" * 40
BASE = "b" * 40


def reviewed() -> ReviewedPolicy:
    return ReviewedPolicy("owner/repo", 17, BASE, 23, frozenset({"full", "gate"}))


COMMENT = Trigger("rationale", "owner/repo", 17, 2, None)
COMPLETED = Trigger("completed_run", "owner/repo", 17, 2, 91)
RUNS = ROOT + "/actions/workflows/23/runs?per_page=100&page=1"


class NativeAPI:
    def __init__(self, values: dict[str, object]) -> None:
        self.values = values
        self.routes: list[str] = []

    def __call__(self, endpoint: str) -> object:
        self.routes.append(endpoint)
        return deepcopy(self.values[endpoint])


def run(identity: int, head: str = HEAD) -> dict[str, object]:
    return {
        "id": identity,
        "workflow_id": 23,
        "event": "pull_request",
        "status": "completed",
        "conclusion": "success",
        "head_sha": head,
        "pull_requests": [{"number": 2, "head": {"sha": HEAD}, "base": {"sha": BASE}}],
    }


def source() -> dict[str, object]:
    return {
        ROOT: {"id": 17, "full_name": "owner/repo"},
        ROOT + "/branches/main": {
            "name": "main",
            "protected": True,
            "commit": {"sha": BASE},
        },
        ROOT + "/pulls/2": {
            "head": {"sha": HEAD},
            "base": {"sha": BASE},
            "merge_commit_sha": "c" * 40,
        },
        RUNS: {"total_count": 2, "workflow_runs": [run(90), run(91)]},
        ROOT + "/actions/workflows/23/runs?per_page=100&page=2": {
            "total_count": 2,
            "workflow_runs": [],
        },
    }


def test_rationale_resolves_latest_current_successful_native_run() -> None:
    api = NativeAPI(source())
    policy = resolve(api, COMMENT, reviewed())
    assert (policy.head, policy.base, policy.run_id, policy.required_names) == (
        HEAD,
        BASE,
        91,
        reviewed().required_names,
    )
    assert RUNS in api.routes


def test_completed_run_keeps_event_id_for_subsequent_native_recheck() -> None:
    api = NativeAPI(source())
    assert resolve(api, COMPLETED, reviewed()).run_id == 91
    assert RUNS not in api.routes


def test_reviewed_policy_is_immutable() -> None:
    value = reviewed()
    with pytest.raises(FrozenInstanceError):
        value.repository_id = 18  # type: ignore[misc]


def test_equal_native_values_can_have_distinct_objects() -> None:
    values = source()
    branch = values[ROOT + "/branches/main"]
    pull = values[ROOT + "/pulls/2"]
    assert isinstance(branch, dict) and isinstance(pull, dict)
    branch["commit"] = {"sha": BASE.encode().decode()}
    pull["base"] = {"sha": BASE.encode().decode()}
    candidate = ReviewedPolicy(
        "owner/repo", int("1000"), BASE, 23, reviewed().required_names
    )
    repository = values[ROOT]
    assert isinstance(repository, dict)
    repository["id"] = int("1000")
    event = Trigger("rationale", b"owner/repo".decode(), int("1000"), 2, None)
    assert resolve(NativeAPI(values), event, candidate).run_id == 91


@pytest.mark.parametrize("identifier", [16, 18])
def test_repository_numeric_identity_rejects_both_directions(identifier: int) -> None:
    values = source()
    repository = values[ROOT]
    assert isinstance(repository, dict)
    repository["id"] = identifier
    with pytest.raises(PolicyFailure):
        resolve(NativeAPI(values), COMMENT, reviewed())


def test_lexically_later_repository_name_is_not_reviewed_identity() -> None:
    values = source()
    repository = values[ROOT]
    assert isinstance(repository, dict)
    repository["full_name"] = "z/repo"
    with pytest.raises(PolicyFailure):
        resolve(NativeAPI(values), COMMENT, reviewed())


@pytest.mark.parametrize("field,value", [("id", 18), ("full_name", "other/repo")])
def test_repository_identity_must_match(field: str, value: object) -> None:
    values = source()
    repository = values[ROOT]
    assert isinstance(repository, dict)
    repository[field] = value
    with pytest.raises(PolicyFailure):
        resolve(NativeAPI(values), COMMENT, reviewed())


@pytest.mark.parametrize(
    "field,value",
    [("name", "elsewhere"), ("protected", False), ("commit", {"sha": HEAD})],
)
def test_current_protected_main_is_required(field: str, value: object) -> None:
    values = source()
    branch = values[ROOT + "/branches/main"]
    assert isinstance(branch, dict)
    branch[field] = value
    with pytest.raises(PolicyFailure):
        resolve(NativeAPI(values), COMMENT, reviewed())


def test_numeric_true_is_not_protected_branch_boolean() -> None:
    values = source()
    branch = values[ROOT + "/branches/main"]
    assert isinstance(branch, dict)
    branch["protected"] = 1
    with pytest.raises(PolicyFailure):
        resolve(NativeAPI(values), COMMENT, reviewed())


@pytest.mark.parametrize("other_base", ["0" * 40, "c" * 40])
def test_changed_native_main_fails_in_both_lexical_directions(other_base: str) -> None:
    values = source()
    branch = values[ROOT + "/branches/main"]
    pull = values[ROOT + "/pulls/2"]
    assert isinstance(branch, dict) and isinstance(pull, dict)
    branch["commit"] = {"sha": other_base}
    pull["base"] = {"sha": other_base}
    with pytest.raises(PolicyFailure, match="reviewed policy base"):
        resolve(NativeAPI(values), COMMENT, reviewed())


def test_pr_base_must_equal_current_reviewed_main() -> None:
    values = source()
    pull = values[ROOT + "/pulls/2"]
    assert isinstance(pull, dict)
    pull["base"] = {"sha": HEAD}
    with pytest.raises(PolicyFailure):
        resolve(NativeAPI(values), COMMENT, reviewed())


def test_lexically_later_pr_base_cannot_qualify() -> None:
    values = source()
    pull = values[ROOT + "/pulls/2"]
    assert isinstance(pull, dict)
    pull["base"] = {"sha": "c" * 40}
    with pytest.raises(PolicyFailure, match="candidate base"):
        resolve(NativeAPI(values), COMMENT, reviewed())


@pytest.mark.parametrize(
    "change",
    [
        {"event": "push"},
        {"status": "in_progress"},
        {"conclusion": "failure"},
        {"head_sha": BASE},
        {"head_sha": "0" * 40},
        {"workflow_id": 24},
        {"workflow_id": 22},
        {"pull_requests": []},
    ],
)
def test_comment_cannot_use_unrelated_or_failed_run(change: dict[str, object]) -> None:
    values = source()
    bad = run(91)
    bad.update(change)
    values[RUNS] = {"total_count": 1, "workflow_runs": [bad]}
    page = ROOT + "/actions/workflows/23/runs?per_page=100&page=2"
    values[page] = {"total_count": 1, "workflow_runs": []}
    with pytest.raises(PolicyFailure):
        resolve(NativeAPI(values), COMMENT, reviewed())


def test_trigger_repository_and_matrix_cannot_be_supplied_by_pr() -> None:
    api = NativeAPI(source())
    with pytest.raises(PolicyFailure):
        resolve(api, Trigger("rationale", "other/repo", 17, 2, None), reviewed())
    with pytest.raises(PolicyFailure):
        resolve(api, COMMENT, ReviewedPolicy("owner/repo", 17, BASE, 23, frozenset()))


@pytest.mark.parametrize(
    "repository,identity", [("z/repo", 17), ("owner/repo", 16), ("owner/repo", 18)]
)
def test_trigger_identity_rejects_lexical_and_numeric_mismatches(
    repository: str, identity: int
) -> None:
    with pytest.raises(PolicyFailure, match="trigger differs"):
        resolve(
            NativeAPI(source()),
            Trigger("rationale", repository, identity, 2, None),
            reviewed(),
        )


def test_matching_run_compares_values_not_object_identity() -> None:
    candidate = source()[ROOT + "/pulls/2"]
    assert isinstance(candidate, dict)
    native_run = run(91, HEAD.encode().decode())
    assert matching_run(native_run, reviewed(), candidate, 2, HEAD) == 91
    large = ReviewedPolicy(
        "owner/repo", 17, BASE, int("1000"), reviewed().required_names
    )
    native_run["workflow_id"] = int("1000")
    assert matching_run(native_run, large, candidate, 2, HEAD) == 91


def test_incomplete_native_run_inventory_fails_closed() -> None:
    values = source()
    values[RUNS] = {"total_count": 3, "workflow_runs": [run(90), run(91)]}
    with pytest.raises(PolicyFailure):
        resolve(NativeAPI(values), COMMENT, reviewed())
