"""A native-shaped issuer publishes the current App-owned check decision."""

from copy import deepcopy
from pathlib import Path

import pytest

from quality.trusted_policy.check_publisher import GithubChecks, Target
from quality.trusted_policy.issuer_resolution import ReviewedPolicy
from quality.trusted_policy.metadata_pages import sequence
from quality.trusted_policy.review_policy import PolicyFailure, record
from quality.trusted_policy.trusted_issuer import issue
from tests.test_check_publisher import fake_cli
from tests.test_comment_collector import comment_source
from tests.test_execution_policy import NAMES, workflow
from tests.test_metadata_collector import PR, REPOSITORY, RUN, NativeAPI
from tests.test_review_policy import BASE, HEAD, review

REVIEWED = ReviewedPolicy("owner/repo", 17, BASE, 2, frozenset(NAMES))
RUNS = REPOSITORY + "/actions/workflows/2/runs?per_page=100&page=1"


class Publisher:
    def __init__(self) -> None:
        self.decisions: list[tuple[str, bool]] = []

    def create(self, head: str, passed: bool) -> int:
        self.decisions.append((head, passed))
        return 91


def native_source() -> dict[str, list[object]]:
    values = comment_source()
    values[REPOSITORY] = [{"id": 17, "full_name": "owner/repo"}]
    values[REPOSITORY + "/branches/main"] = [
        {"name": "main", "protected": True, "commit": {"sha": BASE}}
    ]
    values[RUNS] = [{"total_count": 1, "workflow_runs": [workflow()]}]
    values[REPOSITORY + "/actions/workflows/2/runs?per_page=100&page=2"] = [
        {"total_count": 1, "workflow_runs": []}
    ]
    return values


def comment_event() -> dict[str, object]:
    return {
        "repository": {"full_name": "owner/repo", "id": 17},
        "action": "created",
        "issue": {"number": 1, "pull_request": {"url": "native"}},
    }


def completed_event() -> dict[str, object]:
    return {
        "repository": {"full_name": "owner/repo", "id": 17},
        "action": "completed",
        "workflow_run": {
            "id": 1,
            "event": "pull_request",
            "pull_requests": [{"number": 1}],
        },
    }


def fork_source() -> dict[str, list[object]]:
    values = native_source()
    candidate = deepcopy(values[PR][0])
    assert isinstance(candidate, dict)
    candidate["number"] = 1
    candidate["head"] = {
        "sha": HEAD,
        "ref": "feature",
        "repo": {"id": 99, "full_name": "contributor/copy"},
    }
    values[PR] = [candidate]
    native_run = workflow()
    native_run["pull_requests"] = []
    native_run["head_branch"] = "feature"
    native_run["head_repository"] = {"id": 99, "full_name": "contributor/copy"}
    values[RUN] = [native_run]
    values[REPOSITORY + "/pulls?per_page=100&page=1"] = [[candidate]]
    values[REPOSITORY + "/pulls?per_page=100&page=2"] = [[]]
    return values


@pytest.mark.parametrize(
    "name,event",
    [("issue_comment", comment_event()), ("workflow_run", completed_event())],
)
def test_current_native_approval_publishes_success(name: str, event: object) -> None:
    publisher = Publisher()
    assert (
        issue(NativeAPI(native_source()), publisher.create, name, event, REVIEWED) == 91
    )
    assert publisher.decisions == [(HEAD, False), (HEAD, True)]


def test_reevaluation_after_review_dismissal_publishes_failure() -> None:
    values = native_source()
    values[PR + "/reviews?per_page=100&page=1"] = [[review(state="DISMISSED")]]
    publisher = Publisher()
    assert (
        issue(
            NativeAPI(values),
            publisher.create,
            "issue_comment",
            comment_event(),
            REVIEWED,
        )
        == 91
    )
    assert publisher.decisions == [(HEAD, False)]


def test_untrusted_event_cannot_trigger_publication() -> None:
    event = deepcopy(comment_event())
    event["repository"] = {"full_name": "other/repo", "id": 17}
    publisher = Publisher()
    with pytest.raises(PolicyFailure):
        issue(
            NativeAPI(native_source()),
            publisher.create,
            "issue_comment",
            event,
            REVIEWED,
        )
    assert publisher.decisions == []


def test_missing_native_run_replaces_stale_success_with_failure() -> None:
    values = native_source()
    values[RUNS] = [{"total_count": 0, "workflow_runs": []}]
    values[REPOSITORY + "/actions/workflows/2/runs?per_page=100&page=2"] = [
        {"total_count": 0, "workflow_runs": []}
    ]
    publisher = Publisher()
    assert (
        issue(
            NativeAPI(values),
            publisher.create,
            "issue_comment",
            comment_event(),
            REVIEWED,
        )
        == 91
    )
    assert publisher.decisions == [(HEAD, False)]


def test_missing_run_publishes_failure_for_closed_pull_request() -> None:
    values = native_source()
    values[RUNS] = [{"total_count": 0, "workflow_runs": []}]
    pull = deepcopy(values[PR][0])
    assert isinstance(pull, dict)
    pull["state"] = "closed"
    values[PR] = [pull]
    publisher = Publisher()
    assert (
        issue(
            NativeAPI(values),
            publisher.create,
            "issue_comment",
            comment_event(),
            REVIEWED,
        )
        == 91
    )
    assert publisher.decisions == [(HEAD, False)]


def test_missing_run_cannot_publish_when_base_identity_changed() -> None:
    values = native_source()
    values[RUNS] = [{"total_count": 0, "workflow_runs": []}]
    branch = deepcopy(values[REPOSITORY + "/branches/main"][0])
    assert isinstance(branch, dict)
    branch["commit"] = {"sha": HEAD}
    values[REPOSITORY + "/branches/main"] = [branch]
    publisher = Publisher()
    with pytest.raises(PolicyFailure, match="no longer current"):
        issue(
            NativeAPI(values),
            publisher.create,
            "issue_comment",
            comment_event(),
            REVIEWED,
        )
    assert publisher.decisions == []


def test_native_run_failure_publishes_failure_check() -> None:
    values = native_source()
    failed = workflow()
    failed["conclusion"] = "failure"
    values[RUN] = [failed]
    publisher = Publisher()
    assert (
        issue(
            NativeAPI(values),
            publisher.create,
            "workflow_run",
            completed_event(),
            REVIEWED,
        )
        == 91
    )
    assert publisher.decisions == [(HEAD, False)]


def test_success_cannot_publish_when_initial_failure_check_fails() -> None:
    def reject_failure(head: str, passed: bool) -> int:
        assert head == HEAD and passed is False
        raise PolicyFailure("initial App check was not created")

    with pytest.raises(PolicyFailure, match="not created"):
        issue(
            NativeAPI(native_source()),
            reject_failure,
            "issue_comment",
            comment_event(),
            REVIEWED,
        )


@pytest.mark.parametrize("approved", [True, False])
def test_composed_decision_uses_app_owned_native_check_readback(
    tmp_path: Path, approved: bool
) -> None:
    values = native_source()
    if not approved:
        values[PR + "/reviews?per_page=100&page=1"] = [[review(state="DISMISSED")]]
    mode = "dual" if approved else "failure"
    checks = GithubChecks(fake_cli(tmp_path, mode), Target("owner/repo", 41))
    assert issue(
        NativeAPI(values), checks.create, "issue_comment", comment_event(), REVIEWED
    ) == (78 if approved else 77)


def test_empty_fork_association_recovers_unique_pr_and_issues_app_check(
    tmp_path: Path,
) -> None:
    event = completed_event()
    run = event["workflow_run"]
    assert isinstance(run, dict)
    run["pull_requests"] = []
    checks = GithubChecks(fake_cli(tmp_path, "dual"), Target("owner/repo", 41))
    assert (
        issue(NativeAPI(fork_source()), checks.create, "workflow_run", event, REVIEWED)
        == 78
    )


def test_ambiguous_fork_association_never_publishes() -> None:
    event = completed_event()
    run = event["workflow_run"]
    assert isinstance(run, dict)
    run["pull_requests"] = []
    values = fork_source()
    first = sequence(values[REPOSITORY + "/pulls?per_page=100&page=1"][0])
    duplicate = record(deepcopy(first[0]))
    duplicate["number"] = 2
    first.append(duplicate)
    publisher = Publisher()
    with pytest.raises(PolicyFailure, match="exactly one"):
        issue(NativeAPI(values), publisher.create, "workflow_run", event, REVIEWED)
    assert publisher.decisions == []
