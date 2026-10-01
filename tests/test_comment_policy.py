"""Proposed native comment contract and fail-closed boundary probes."""

import pytest

from quality.trusted_policy.comment_policy import comment_reason, require_comment
from quality.trusted_policy.review_policy import PolicyFailure

HEAD = "a" * 40
ISSUE = "https://api.github.com/repos/owner/repo/issues/7"
BODY = f"Policy rationale for {HEAD}: Complete mutation scope stays protected."


def comment(
    identity: int = 1, author: int = 2, body: object = BODY
) -> dict[str, object]:
    return {
        "id": identity,
        "user": {"id": author},
        "issue_url": ISSUE,
        "body": body,
        "author_association": "OWNER",
    }


def test_current_head_approved_author_comment_qualifies() -> None:
    assert require_comment([comment(), comment(2, 3)], 2, HEAD, ISSUE, True) == 1
    assert comment_reason(BODY, HEAD) == "Complete mutation scope stays protected."


def test_latest_qualifying_native_identity_is_returned() -> None:
    assert require_comment([comment(), comment(3)], 2, HEAD, ISSUE, True) == 3


@pytest.mark.parametrize(
    "body",
    [
        None,
        "",
        "Policy rationale for " + "b" * 40 + ": reason",
        f"Policy rationale for {HEAD}: short",
    ],
)
def test_missing_stale_or_short_reason_fails(body: object) -> None:
    with pytest.raises(PolicyFailure):
        require_comment([comment(body=body)], 2, HEAD, ISSUE, True)


def test_author_association_cannot_replace_native_reviewer_identity() -> None:
    with pytest.raises(PolicyFailure, match="missing"):
        require_comment([comment(author=4)], 2, HEAD, ISSUE, True)
    with pytest.raises(PolicyFailure, match="missing"):
        require_comment([comment(author=1)], 2, HEAD, ISSUE, True)


def test_unrelated_comments_do_not_hide_valid_comment() -> None:
    assert require_comment([comment(1, 4), comment(2)], 2, HEAD, ISSUE, True) == 2


def test_duplicate_comment_identity_fails_even_when_valid() -> None:
    with pytest.raises(PolicyFailure, match="duplicate"):
        require_comment([comment(), comment()], 2, HEAD, ISSUE, True)


def test_foreign_issue_comment_fails_inventory() -> None:
    for url in (ISSUE + "8", ISSUE[:-1]):
        foreign = {**comment(), "issue_url": url}
        with pytest.raises(PolicyFailure, match="another issue"):
            require_comment([foreign], 2, HEAD, ISSUE, True)


def test_reason_length_boundary_is_exact() -> None:
    prefix = f"Policy rationale for {HEAD}: "
    with pytest.raises(PolicyFailure, match="substantive"):
        comment_reason(prefix + "x" * 29, HEAD)
    assert comment_reason(prefix + "x" * 30, HEAD) == "x" * 30


def test_equal_reviewer_identifiers_do_not_require_object_identity() -> None:
    author = int("1001")
    reviewer = int("1001")
    assert author == reviewer and author is not reviewer
    assert require_comment([comment(author=author)], reviewer, HEAD, ISSUE, True) == 1


def test_equal_issue_urls_do_not_require_object_identity() -> None:
    url = "".join((ISSUE[:-1], ISSUE[-1]))
    assert url == ISSUE and url is not ISSUE
    assert require_comment([{**comment(), "issue_url": url}], 2, HEAD, ISSUE, True) == 1


@pytest.mark.parametrize("complete", [False, None, 1])
def test_partial_inventory_never_authorizes(complete: object) -> None:
    with pytest.raises(PolicyFailure, match="complete"):
        require_comment([comment()], 2, HEAD, ISSUE, complete)


def test_missing_comment_does_not_authorize() -> None:
    with pytest.raises(PolicyFailure, match="missing"):
        require_comment([], 2, HEAD, ISSUE, True)


def test_invalid_platform_identity_fails() -> None:
    with pytest.raises(PolicyFailure, match="positive"):
        require_comment([comment()], 0, HEAD, ISSUE, True)
