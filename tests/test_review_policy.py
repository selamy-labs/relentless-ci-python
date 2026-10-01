"""Platform-shaped clean and bypass cases for the preliminary approval decision."""

import json
from collections.abc import Sequence
from datetime import datetime

import pytest

from quality.trusted_policy.review_policy import (
    PolicyFailure,
    contributor_ids,
    digest,
    identifier,
    latest_reviews,
    matching_role,
    rationale,
    record,
    require_approval,
    retain_review,
    same_text,
    timestamp,
)

HEAD = "a" * 40
BASE = "b" * 40
MERGE = "c" * 40
BODY = (
    "Policy rationale: This preserves complete source enrollment "
    "and validates the changed gate."
)


def test_native_text_compares_value_not_identity() -> None:
    expected = "completed"
    native = expected.encode().decode()
    assert native is not expected
    assert same_text(native, expected)
    assert not same_text(native, "other")
    with pytest.raises(PolicyFailure):
        same_text(native, "")


def pull_request() -> dict[str, object]:
    return {
        "user": {"id": 1},
        "head": {"sha": HEAD},
        "base": {"sha": BASE},
        "merge_commit_sha": MERGE,
        "state": "open",
        "draft": False,
        "commits": 1,
    }


def review(
    identity: int = 10, user: int = 2, state: str = "APPROVED"
) -> dict[str, object]:
    return {
        "id": identity,
        "user": {"id": user, "login": f"user-{user}"},
        "state": state,
        "submitted_at": "2026-09-29T15:00:00Z",
        "commit_id": HEAD,
        "body": BODY,
    }


def role(user: int = 2, name: str = "maintain") -> dict[str, object]:
    return {"user": {"id": user, "login": f"user-{user}"}, "role_name": name}


def commit() -> dict[str, object]:
    return {"sha": HEAD, "author": {"id": 1}, "committer": {"id": 4}}


def decide(
    pr: object,
    reviews: Sequence[object],
    roles: dict[int, object],
    complete: bool = True,
) -> int:
    return require_approval(pr, reviews, roles, HEAD, BASE, complete, [commit()])


@pytest.mark.parametrize("name", ["admin", "maintain"])
def test_current_non_author_maintainer_rationale_passes(name: str) -> None:
    assert decide(pull_request(), [review()], {2: role(name=name)}) == 2


@pytest.mark.parametrize(
    "state", ["CHANGES_REQUESTED", "DISMISSED", "COMMENTED", "PENDING"]
)
def test_unapproved_states_do_not_authorize(state: str) -> None:
    with pytest.raises(PolicyFailure, match="missing"):
        decide(pull_request(), [review(state=state)], {2: role()})


def test_author_cannot_approve_own_change_even_as_admin() -> None:
    with pytest.raises(PolicyFailure, match="missing"):
        decide(pull_request(), [review(user=1)], {1: role(1, "admin")})


@pytest.mark.parametrize(
    "field,value",
    [
        ("state", "closed"),
        ("draft", True),
        ("draft", 0),
        ("head", {"sha": "c" * 40}),
        ("base", {"sha": "d" * 40}),
    ],
)
def test_changed_candidate_or_base_and_unready_pr_fail(
    field: str, value: object
) -> None:
    pr = {**pull_request(), field: value}
    with pytest.raises(PolicyFailure):
        decide(pr, [review()], {2: role()})


@pytest.mark.parametrize("name", ["write", "triage", "read", "none", "custom"])
def test_non_maintainer_role_cannot_approve(name: str) -> None:
    with pytest.raises(PolicyFailure, match="missing"):
        decide(pull_request(), [review()], {2: role(name=name)})


@pytest.mark.parametrize(
    "body", [None, "", "Approved", "Policy rationale: too short", "prefix " + BODY]
)
def test_missing_or_inadequate_rationale_fails(body: object) -> None:
    with pytest.raises(PolicyFailure, match="missing"):
        decide(pull_request(), [{**review(), "body": body}], {2: role()})


def test_review_on_previous_head_is_stale() -> None:
    with pytest.raises(PolicyFailure, match="missing"):
        decide(pull_request(), [{**review(), "commit_id": "c" * 40}], {2: role()})


def test_lexically_earlier_review_head_is_stale() -> None:
    with pytest.raises(PolicyFailure, match="missing"):
        decide(pull_request(), [{**review(), "commit_id": "0" * 40}], {2: role()})


def test_equal_commit_values_with_distinct_objects_qualify() -> None:
    native_head = HEAD.encode().decode()
    assert native_head is not HEAD
    assert (
        decide(pull_request(), [{**review(), "commit_id": native_head}], {2: role()})
        == 2
    )


def test_equal_candidate_digests_with_distinct_objects_qualify() -> None:
    native_head = HEAD.encode().decode()
    native_base = BASE.encode().decode()
    assert native_head is not HEAD and native_base is not BASE
    candidate = {
        **pull_request(),
        "head": {"sha": native_head},
        "base": {"sha": native_base},
    }
    assert decide(candidate, [review()], {2: role()}) == 2


@pytest.mark.parametrize("field", ["head", "base"])
def test_lexically_earlier_candidate_digest_is_rejected(field: str) -> None:
    with pytest.raises(PolicyFailure):
        decide({**pull_request(), field: {"sha": "0" * 40}}, [review()], {2: role()})


def test_latest_decision_wins_independent_of_api_order() -> None:
    original = review()
    revoked = {
        **review(11, state="CHANGES_REQUESTED"),
        "submitted_at": "2026-09-29T16:00:00Z",
    }
    for values in [[original, revoked], [revoked, original]]:
        with pytest.raises(PolicyFailure, match="missing"):
            decide(pull_request(), values, {2: role()})


def test_newer_approval_replaces_revocation_and_comments_preserve_decision() -> None:
    revoked = review(state="CHANGES_REQUESTED")
    approved = {**review(11), "submitted_at": "2026-09-29T16:00:00Z"}
    comment = {**review(12, state="COMMENTED"), "submitted_at": "2026-09-29T17:00:00Z"}
    assert decide(pull_request(), [comment, approved, revoked], {2: role()}) == 2


def test_equal_timestamp_platform_identity_orders_reviews() -> None:
    with pytest.raises(PolicyFailure, match="missing"):
        decide(pull_request(), [review(), review(11, state="DISMISSED")], {2: role()})


def test_retain_review_does_not_replace_equal_native_order_key() -> None:
    latest: dict[int, tuple[tuple[datetime, int], dict[str, object]]] = {}
    retain_review(latest, 2, 10, review())
    retain_review(latest, 2, 10, review(state="DISMISSED"))
    assert latest[2][1]["state"] == "APPROVED"


def test_unqualified_review_does_not_hide_a_separate_valid_maintainer() -> None:
    assert (
        decide(
            pull_request(),
            [review(), review(11, 3)],
            {2: role(name="read"), 3: role(3)},
        )
        == 3
    )
    assert (
        decide(
            pull_request(),
            [{**review(), "body": ""}, review(11, 3)],
            {2: role(), 3: role(3)},
        )
        == 3
    )


@pytest.mark.parametrize(
    "user", [{"id": 3, "login": "user-2"}, {"id": 2, "login": "impostor"}]
)
def test_role_response_must_identify_exact_reviewer(user: dict[str, object]) -> None:
    with pytest.raises(PolicyFailure, match="identity"):
        decide(pull_request(), [review()], {2: {**role(), "user": user}})


def test_role_identity_checks_both_lexical_directions() -> None:
    reviewer: dict[str, object] = {"id": 2, "login": "user-2"}
    for user in ({"id": 1, "login": "user-2"}, {"id": 2, "login": "z-user"}):
        with pytest.raises(PolicyFailure, match="identity"):
            matching_role({"user": user, "role_name": "maintain"}, reviewer)


def test_role_identity_compares_large_values_instead_of_objects() -> None:
    reviewer: dict[str, object] = {"id": int("1000"), "login": "user-1000"}
    response = {
        "user": {"id": int("1000"), "login": "user-1000"},
        "role_name": "maintain",
    }
    assert matching_role(response, reviewer)


def test_partial_or_absent_metadata_never_passes() -> None:
    with pytest.raises(PolicyFailure, match="complete"):
        decide(pull_request(), [review()], {2: role()}, False)
    with pytest.raises(PolicyFailure, match="complete"):
        decide(pull_request(), [review()], {2: role()}, json.loads("1"))
    with pytest.raises(PolicyFailure, match="missing"):
        decide(pull_request(), [], {})
    with pytest.raises(KeyError):
        decide(pull_request(), [review()], {})


def test_duplicate_or_unknown_review_inventory_fails() -> None:
    with pytest.raises(PolicyFailure, match="duplicate"):
        latest_reviews([review(), review()])
    with pytest.raises(PolicyFailure, match="unknown"):
        latest_reviews([review(state="SUCCESS")])


@pytest.mark.parametrize("value", [True, False, 0, -1, 1.5, "2", None])
def test_platform_identities_are_positive_integers(value: object) -> None:
    with pytest.raises(PolicyFailure):
        identifier(value)


def test_platform_identity_rejects_classes_that_compare_equal_to_int() -> None:
    class EqualInt(type):
        def __eq__(cls, other: object) -> bool:
            return other is int

        def __ne__(cls, other: object) -> bool:
            return other is not int

    class FakeInteger(metaclass=EqualInt):
        def __le__(self, other: object) -> bool:
            return False

    with pytest.raises(PolicyFailure):
        identifier(FakeInteger())


@pytest.mark.parametrize("value", [[], 1, None, "object"])
def test_metadata_records_are_objects(value: object) -> None:
    with pytest.raises(PolicyFailure):
        record(value)


@pytest.mark.parametrize("value", ["", None, "a" * 39, "A" * 40, "g" * 40])
def test_commit_identities_are_exact(value: object) -> None:
    with pytest.raises(PolicyFailure):
        digest(value)


@pytest.mark.parametrize(
    "value",
    ["", None, "2026-09-29", "2026-09-29T15:00:00+00:00", "2026-02-30T15:00:00Z"],
)
def test_submission_dates_use_native_valid_utc_format(value: object) -> None:
    with pytest.raises(ValueError):
        timestamp(value)


def test_positive_rationale_and_timestamp_boundaries() -> None:
    assert (
        rationale("  Policy rationale: " + "x" * 30 + "  ")
        == "Policy rationale: " + "x" * 30
    )
    assert timestamp("2024-02-29T00:00:00Z") == datetime.fromisoformat(
        "2024-02-29T00:00:00+00:00"
    )
    with pytest.raises(PolicyFailure, match="rationale"):
        rationale("Policy rationale: " + "x" * 29)


def test_complete_commit_inventory_compares_values_not_integer_objects() -> None:
    commits = [
        {"sha": f"{number:040x}", "author": {"id": 1}, "committer": {"id": 4}}
        for number in range(1, 258)
    ]
    assert contributor_ids({"commits": int("257")}, commits, 1) == {1, 4}
    with pytest.raises(PolicyFailure, match="complete"):
        contributor_ids({"commits": 1}, commits, 1)


@pytest.mark.parametrize("field", ["author", "committer"])
def test_review_cannot_approve_its_own_commit_through_another_pr_actor(
    field: str,
) -> None:
    value = {**commit(), field: {"id": 2}}
    with pytest.raises(PolicyFailure, match="missing"):
        require_approval(
            pull_request(), [review()], {2: role()}, HEAD, BASE, True, [value]
        )


def test_incomplete_duplicate_or_unmapped_commit_authorship_fails() -> None:
    with pytest.raises(PolicyFailure, match="complete"):
        require_approval(pull_request(), [review()], {2: role()}, HEAD, BASE, True, [])
    with pytest.raises(PolicyFailure, match="duplicate"):
        require_approval(
            {**pull_request(), "commits": 2},
            [review()],
            {2: role()},
            HEAD,
            BASE,
            True,
            [commit(), commit()],
        )
    with pytest.raises(PolicyFailure, match="object"):
        require_approval(
            pull_request(),
            [review()],
            {2: role()},
            HEAD,
            BASE,
            True,
            [{**commit(), "author": None}],
        )
