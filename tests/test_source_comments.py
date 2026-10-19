"""Comment words are advisory; disabling an analyzer remains prohibited."""

from pathlib import Path

import pytest

from tests.test_incomplete import authored, native_command


@pytest.mark.parametrize("word", ["TODO", "FIXME", "XXX", "todo", "fixme", "xxx"])
def test_advisory_comment_words_do_not_make_completed_source_incomplete(
    tmp_path: Path, word: str
) -> None:
    from quality.incomplete import verify_file

    source = f"# {word}: discuss a future improvement\nvalue = 1  # {word}\n"
    verify_file(authored(tmp_path, "quality/comment.py", source))


def test_native_comment_policy_accepts_notes_and_rejects_suppression(
    tmp_path: Path,
) -> None:
    path = authored(tmp_path, "quality/comment.py", "# TODO: future work\nvalue = 1\n")
    allowed = native_command(tmp_path)
    assert allowed.returncode == 0, allowed.stdout + allowed.stderr

    path.write_text("value = 1  # TODO: future work; noqa\n")
    forbidden = native_command(tmp_path)
    assert forbidden.returncode == 1
    assert "suppressed comment" in forbidden.stderr
