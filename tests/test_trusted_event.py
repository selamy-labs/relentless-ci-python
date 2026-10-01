"""Fail-closed issuer event parsing before authenticated metadata reads."""

import copy

import pytest

from quality.trusted_policy.review_policy import PolicyFailure
from quality.trusted_policy.trusted_event import Trigger, parse_event

NAME = "selamy-labs/relentless-ci-python"
IDENTITY = 1234


def comment() -> dict[str, object]:
    return {
        "repository": {"full_name": NAME, "id": IDENTITY},
        "action": "created",
        "issue": {"number": 2, "pull_request": {"url": "native"}},
    }


def run() -> dict[str, object]:
    return {
        "repository": {"full_name": NAME, "id": IDENTITY},
        "action": "completed",
        "workflow_run": {
            "id": 77,
            "event": "pull_request",
            "pull_requests": [{"number": 2}],
        },
    }


def dispatch() -> dict[str, object]:
    return {
        "repository": {"full_name": NAME, "id": IDENTITY},
        "action": "relentless-policy-reevaluate",
        "client_payload": {"pull_number": 2},
    }


def test_dispatch_supplies_only_pr_lookup_number() -> None:
    assert parse_event("repository_dispatch", dispatch(), NAME, IDENTITY) == Trigger(
        "dispatch", NAME, IDENTITY, 2, None
    )


@pytest.mark.parametrize(
    "change",
    [
        {"action": "other"},
        {"client_payload": {}},
        {"client_payload": {"pull_number": 0}},
        {"client_payload": {"pull_number": "2"}},
        {"client_payload": {"pull_number": 2, "verdict": "pass"}},
        {"client_payload": {"pull_number": 2, "head": "a" * 40}},
    ],
)
def test_dispatch_rejects_extra_verdict_and_invalid_lookup(
    change: dict[str, object],
) -> None:
    with pytest.raises(PolicyFailure):
        parse_event("repository_dispatch", {**dispatch(), **change}, NAME, IDENTITY)


@pytest.mark.parametrize("action", ["created", "edited", "deleted"])
def test_comment_actions_recheck_current_native_state(action: str) -> None:
    event = comment()
    event["action"] = action
    assert parse_event("issue_comment", event, NAME, IDENTITY) == Trigger(
        "rationale", NAME, IDENTITY, 2, None
    )


def test_completed_run_supplies_only_native_ids() -> None:
    assert parse_event("workflow_run", run(), NAME, IDENTITY) == Trigger(
        "completed_run", NAME, IDENTITY, 2, 77
    )


def test_unassociated_run_defers_pull_identity_to_native_recovery() -> None:
    event = run()
    payload = event["workflow_run"]
    assert isinstance(payload, dict)
    payload["pull_requests"] = []
    assert parse_event("workflow_run", event, NAME, IDENTITY) == Trigger(
        "completed_run", NAME, IDENTITY, None, 77
    )


INVALID_EVENTS: list[tuple[str, tuple[str, object]]] = [
    ("issue_comment", ("action", "transferred")),
    ("issue_comment", ("issue", {"number": 2})),
    ("issue_comment", ("issue", {"number": 0, "pull_request": {}})),
    ("workflow_run", ("action", "requested")),
    (
        "workflow_run",
        (
            "workflow_run",
            {"id": 77, "event": "push", "pull_requests": [{"number": 2}]},
        ),
    ),
    (
        "workflow_run",
        (
            "workflow_run",
            {
                "id": 77,
                "event": "pull_request",
                "pull_requests": [{"number": 2}, {"number": 3}],
            },
        ),
    ),
    (
        "workflow_run",
        (
            "workflow_run",
            {"id": 0, "event": "pull_request", "pull_requests": [{"number": 2}]},
        ),
    ),
]


@pytest.mark.parametrize(("event_name", "change"), INVALID_EVENTS)
def test_event_rejects_unqualified_identity(
    event_name: str, change: tuple[str, object]
) -> None:
    event = comment() if event_name == "issue_comment" else run()
    event[change[0]] = change[1]
    with pytest.raises(PolicyFailure):
        parse_event(event_name, event, NAME, IDENTITY)


@pytest.mark.parametrize(
    ("field", "value"),
    [("full_name", "other/repo"), ("id", 999), ("id", True)],
)
def test_repository_must_match_both_native_id_and_name(
    field: str, value: object
) -> None:
    event = comment()
    repository = copy.copy(event["repository"])
    assert isinstance(repository, dict)
    repository[field] = value
    event["repository"] = repository
    with pytest.raises(PolicyFailure):
        parse_event("issue_comment", event, NAME, IDENTITY)


def test_unknown_event_is_rejected() -> None:
    with pytest.raises(PolicyFailure, match="unsupported trusted issuer event"):
        parse_event("pull_request_review", comment(), NAME, IDENTITY)
