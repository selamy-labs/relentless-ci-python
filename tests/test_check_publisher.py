"""Native fake transport proves check ownership, exact commit, and readback."""

import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import cast

import pytest

from quality.trusted_policy.check_publisher import (
    CONTEXT,
    GithubChecks,
    Target,
    payload,
    verify_response,
)
from quality.trusted_policy.review_policy import PolicyFailure

HEAD = "a" * 40


def target() -> Target:
    return Target("owner/repo", 41)


def fake_cli(root: Path, mode: str) -> Path:
    script = root / "gh-fake"
    state = root / "gh-check-state.json"
    script.write_text(
        f"#!{sys.executable}\n"
        "import json,os,sys\n"
        f"mode={mode!r}\n"
        "fixed_id=1000 if mode=='large_id' else 77\n"
        f"state={str(state)!r}\n"
        "args=sys.argv[1:]\n"
        "assert args[:4]==['api','--hostname','github.com','--method']\n"
        "route=args[-1]\n"
        "if args[4]=='POST':\n"
        " assert route=='repos/owner/repo/check-runs'\n"
        " assert args[-3:-1]==['--input','-']\n"
        " raw=sys.stdin.read()\n"
        " body=json.loads(raw)\n"
        " assert raw==json.dumps(body,sort_keys=True)\n"
        " assert body['name']=='Relentless trusted policy'\n"
        " assert body['head_sha']=='a'*40\n"
        " assert body['status']=='completed'\n"
        " if mode!='dual':\n"
        "  assert body['conclusion']==('failure' if mode=='failure' else 'success')\n"
        " if mode=='post_failed': sys.exit(2)\n"
        " if mode=='dual':\n"
        "  previous=json.load(open(state)) if os.path.exists(state) else None\n"
        "  identity=77 if previous is None else previous['id']+1\n"
        "  value={**body,'id':identity,'app':{'id':41}}\n"
        "  json.dump(value,open(state,'w'))\n"
        "else:\n"
        " assert args[4]=='GET'\n"
        " if mode=='dual':\n"
        "  value=json.load(open(state))\n"
        "  assert route=='repos/owner/repo/check-runs/'+str(value['id'])\n"
        " else:\n"
        "  assert route=='repos/owner/repo/check-runs/'+str(fixed_id)\n"
        " body={'name':'Relentless trusted policy','head_sha':'a'*40,"
        "'status':'completed','conclusion':"
        "('failure' if mode=='failure' else 'success')}\n"
        "if mode!='dual': value={**body,'id':fixed_id,'app':{'id':41}}\n"
        "if mode=='wrong_app': value['app']['id']=42\n"
        "if mode=='wrong_app_low': value['app']['id']=40\n"
        "if mode=='wrong_head': value['head_sha']='b'*40\n"
        "if mode=='wrong_head_low': value['head_sha']='0'*40\n"
        "if mode=='readback_changed' and args[4]=='GET': value['id']=78\n"
        "if mode=='readback_lower' and args[4]=='GET': value['id']=76\n"
        "print(json.dumps(value))\n"
    )
    script.chmod(0o700)
    return script


def test_native_app_check_is_created_and_read_back(tmp_path: Path) -> None:
    assert GithubChecks(fake_cli(tmp_path, "normal"), target()).create(HEAD, True) == 77


def test_native_app_failure_check_is_created_and_read_back(tmp_path: Path) -> None:
    assert (
        GithubChecks(fake_cli(tmp_path, "failure"), target()).create(HEAD, False) == 77
    )


@pytest.mark.parametrize(
    "mode",
    [
        "post_failed",
        "wrong_app",
        "wrong_app_low",
        "wrong_head",
        "wrong_head_low",
        "readback_changed",
        "readback_lower",
    ],
)
def test_failed_or_unbound_native_check_never_qualifies(
    tmp_path: Path, mode: str
) -> None:
    with pytest.raises(PolicyFailure):
        GithubChecks(fake_cli(tmp_path, mode), target()).create(HEAD, True)


def test_native_check_readback_compares_large_ids_by_value(tmp_path: Path) -> None:
    assert (
        GithubChecks(fake_cli(tmp_path, "large_id"), target()).create(HEAD, True)
        == 1000
    )


def test_check_transport_has_exact_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    native_run = subprocess.run

    def tracked_run(
        *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        assert kwargs["timeout"] == 30
        return cast(subprocess.CompletedProcess[bytes], native_run(*args, **kwargs))  # type: ignore[call-overload]

    monkeypatch.setattr(subprocess, "run", tracked_run)
    assert GithubChecks(fake_cli(tmp_path, "normal"), target()).create(HEAD, True) == 77


def test_negative_native_exit_is_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupted(
        *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(["gh"], -1, b"")

    monkeypatch.setattr(subprocess, "run", interrupted)
    with pytest.raises(PolicyFailure, match="creation failed"):
        GithubChecks(fake_cli(tmp_path, "normal"), target()).create(HEAD, True)


@pytest.mark.parametrize("passed,conclusion", [(True, "success"), (False, "failure")])
def test_compiled_check_has_terminal_decision(passed: bool, conclusion: str) -> None:
    body = payload(target(), HEAD, passed)
    assert (body["name"], body["status"], body["conclusion"]) == (
        CONTEXT,
        "completed",
        conclusion,
    )
    output = body["output"]
    assert isinstance(output, dict)
    assert output["title"] == (
        "Trusted policy qualified" if passed else "Trusted policy rejected"
    )
    assert output["summary"] == (
        "Native run, review, and protected policy evidence qualified."
        if passed
        else "Required trusted policy evidence is absent or invalid."
    )


@pytest.mark.parametrize("head,passed", [("b" * 39, True), (HEAD, 1), (HEAD, "yes")])
def test_uncompiled_head_or_decision_is_rejected(head: str, passed: object) -> None:
    with pytest.raises(PolicyFailure):
        payload(target(), head, passed)


def test_compiled_decision_rejects_class_that_compares_equal_to_bool() -> None:
    class EqualBool(type):
        def __eq__(cls, other: object) -> bool:
            return other is bool

        def __ne__(cls, other: object) -> bool:
            return other is not bool

    class FakeBool(metaclass=EqualBool):
        pass

    with pytest.raises(PolicyFailure):
        payload(target(), HEAD, FakeBool())


def test_context_compares_text_values_in_both_directions() -> None:
    native_context = CONTEXT.encode().decode()
    assert native_context is not CONTEXT
    assert payload(Target("owner/repo", 41, native_context), HEAD, True)
    GithubChecks(Path("/bin/true"), Target("owner/repo", 41, native_context))
    for context in ("A", "z"):
        with pytest.raises(PolicyFailure):
            payload(Target("owner/repo", 41, context), HEAD, True)
        with pytest.raises(PolicyFailure):
            GithubChecks(Path("/bin/true"), Target("owner/repo", 41, context))


def test_trusted_check_records_are_immutable() -> None:
    target = Target("owner/repo", 41)
    with pytest.raises(FrozenInstanceError):
        target.app_id = 42  # type: ignore[misc]
    checks = GithubChecks(Path("/bin/true"), target)
    with pytest.raises(FrozenInstanceError):
        checks.target = Target("other/repo", 41)  # type: ignore[misc]


def test_context_and_app_identity_are_fixed() -> None:
    with pytest.raises(PolicyFailure):
        GithubChecks(Path("/bin/true"), Target("owner/repo", 41, "caller-selected"))
    with pytest.raises(PolicyFailure):
        GithubChecks(Path("/bin/true"), Target("owner/repo", 0))
    response = {
        "id": 77,
        "name": CONTEXT,
        "head_sha": HEAD,
        "status": "completed",
        "conclusion": "success",
        "app": {"id": 42},
    }
    with pytest.raises(PolicyFailure):
        verify_response(response, target(), payload(target(), HEAD, True))
    large = Target("owner/repo", int("1000"))
    assert (
        verify_response(
            {**response, "app": {"id": int("1000")}}, large, payload(large, HEAD, True)
        )
        == 77
    )
