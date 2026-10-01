"""Native-shaped comment inventory and race probes for the proposed carrier."""

import pytest

from quality.trusted_policy.metadata_collector import evaluate_comment
from quality.trusted_policy.review_policy import PolicyFailure
from tests.test_comment_policy import BODY, comment
from tests.test_metadata_collector import POLICY, PR, REPOSITORY, NativeAPI, source
from tests.test_review_policy import review

COMMENTS = REPOSITORY + "/issues/1/comments?per_page=100&page=1"
EMPTY = REPOSITORY + "/issues/1/comments?per_page=100&page=2"
ISSUE = "https://api.github.com/repos/owner/repo/issues/1"


def comment_source() -> dict[str, list[object]]:
    values = source()
    values[PR + "/reviews?per_page=100&page=1"] = [[{**review(), "body": ""}]]
    values[COMMENTS] = [[{**comment(body=BODY), "issue_url": ISSUE}]]
    values[EMPTY] = [[]]
    return values


def test_native_comment_inventory_qualifies_without_review_body_reason() -> None:
    api = NativeAPI(comment_source())
    assert evaluate_comment(api, POLICY) == 2
    assert api.routes.count(COMMENTS) == 2
    assert api.routes.count(EMPTY) == 2


def test_deleted_or_edited_rationale_during_evaluation_fails() -> None:
    values = comment_source()
    values[COMMENTS] = [values[COMMENTS][0], []]
    with pytest.raises(PolicyFailure, match="comment inventory changed"):
        evaluate_comment(NativeAPI(values), POLICY)


def test_edited_rationale_during_evaluation_fails() -> None:
    values = comment_source()
    changed = {**comment(body=BODY + " Updated"), "issue_url": ISSUE}
    values[COMMENTS] = [values[COMMENTS][0], [changed]]
    with pytest.raises(PolicyFailure, match="comment inventory changed"):
        evaluate_comment(NativeAPI(values), POLICY)


def test_missing_comment_fails() -> None:
    values = comment_source()
    values[COMMENTS] = [[]]
    with pytest.raises(PolicyFailure, match="rationale comment is missing"):
        evaluate_comment(NativeAPI(values), POLICY)


@pytest.mark.parametrize("author", [1, 3])
def test_author_or_other_maintainer_comment_cannot_replace_approver(
    author: int,
) -> None:
    values = comment_source()
    values[COMMENTS] = [[{**comment(author=author), "issue_url": ISSUE}]]
    with pytest.raises(PolicyFailure, match="rationale comment is missing"):
        evaluate_comment(NativeAPI(values), POLICY)


def test_stale_head_comment_cannot_authorize() -> None:
    values = comment_source()
    values[COMMENTS] = [
        [{**comment(body=BODY.replace("a" * 40, "b" * 40)), "issue_url": ISSUE}]
    ]
    with pytest.raises(PolicyFailure, match="rationale comment is missing"):
        evaluate_comment(NativeAPI(values), POLICY)


def test_revoked_review_still_blocks_comment_route() -> None:
    values = comment_source()
    values[PR + "/reviews?per_page=100&page=1"] = [[review(state="DISMISSED")]]
    with pytest.raises(PolicyFailure, match="approval is missing"):
        evaluate_comment(NativeAPI(values), POLICY)
