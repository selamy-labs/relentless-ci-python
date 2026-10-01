"""Native fake transport proves check ownership, exact commit, and readback."""

import sys
from pathlib import Path

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
TARGET = Target("owner/repo", 41)


def fake_cli(root: Path, mode: str) -> Path:
    script = root / "gh-fake"
    state = root / "gh-check-state.json"
    script.write_text(
        f"#!{sys.executable}\n"
        "import json,os,sys\n"
        f"mode={mode!r}\n"
        f"state={str(state)!r}\n"
        "args=sys.argv[1:]\n"
        "assert args[:4]==['api','--hostname','github.com','--method']\n"
        "route=args[-1]\n"
        "if args[4]=='POST':\n"
        " assert route=='repos/owner/repo/check-runs'\n"
        " assert args[-3:-1]==['--input','-']\n"
        " body=json.load(sys.stdin)\n"
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
        "  assert route=='repos/owner/repo/check-runs/77'\n"
        " body={'name':'Relentless trusted policy','head_sha':'a'*40,"
        "'status':'completed','conclusion':"
        "('failure' if mode=='failure' else 'success')}\n"
        "if mode!='dual': value={**body,'id':77,'app':{'id':41}}\n"
        "if mode=='wrong_app': value['app']['id']=42\n"
        "if mode=='wrong_head': value['head_sha']='b'*40\n"
        "if mode=='readback_changed' and args[4]=='GET': value['id']=78\n"
        "print(json.dumps(value))\n"
    )
    script.chmod(0o700)
    return script


def test_native_app_check_is_created_and_read_back(tmp_path: Path) -> None:
    assert GithubChecks(fake_cli(tmp_path, "normal"), TARGET).create(HEAD, True) == 77


def test_native_app_failure_check_is_created_and_read_back(tmp_path: Path) -> None:
    assert GithubChecks(fake_cli(tmp_path, "failure"), TARGET).create(HEAD, False) == 77


@pytest.mark.parametrize(
    "mode", ["post_failed", "wrong_app", "wrong_head", "readback_changed"]
)
def test_failed_or_unbound_native_check_never_qualifies(
    tmp_path: Path, mode: str
) -> None:
    with pytest.raises(PolicyFailure):
        GithubChecks(fake_cli(tmp_path, mode), TARGET).create(HEAD, True)


@pytest.mark.parametrize("passed,conclusion", [(True, "success"), (False, "failure")])
def test_compiled_check_has_terminal_decision(passed: bool, conclusion: str) -> None:
    body = payload(TARGET, HEAD, passed)
    assert (body["name"], body["status"], body["conclusion"]) == (
        CONTEXT,
        "completed",
        conclusion,
    )


@pytest.mark.parametrize("head,passed", [("b" * 39, True), (HEAD, 1), (HEAD, "yes")])
def test_uncompiled_head_or_decision_is_rejected(head: str, passed: object) -> None:
    with pytest.raises(PolicyFailure):
        payload(TARGET, head, passed)


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
        verify_response(response, TARGET, payload(TARGET, HEAD, True))
