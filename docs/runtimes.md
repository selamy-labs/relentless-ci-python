# Runtime support

The template declares Python 3.11, 3.12, 3.13 and 3.14. The primary
[Python release-cycle API](https://peps.python.org/api/release-cycle.json) was
reviewed on 2026-09-29. Its canonical LF snapshot is in
`quality/python-releases.json`; `quality/runtime-support.json` records its
SHA-256 digest, approved branches and review window.
Windows checkout CRLF is normalized to LF before digest comparison; all other
bytes must match the reviewed snapshot.

The [developer guide](https://devguide.python.org/versions/) at commit
`d9adc4f23cfad7e9e366f4fec408bdea18f99cc2` lists upstream support. Its generator
uses the primary release-cycle API. The pinned guide identifies the review's
source context; the saved API digest binds the actual dates used by this gate.
A matching digest proves local consistency, not that a contributor's changed
snapshot came from upstream. Trusted policy-change protection remains pending.

Run `python -m quality.runtime_support_main` in the locked development environment.
The full local command and each installed-behavior job require this check.
It uses the current UTC date without accounts or live network requests.
The current review is valid from 2026-09-29 through 2026-12-27; future and expired
reviews fail. Only stable upstream bugfix/security branches are accepted.
Release start dates are included, and end-of-support dates are excluded.

The upstream API supplies scheduled end-of-life months for these branches.
The gate conservatively stops accepting a branch on the first day of that month.
This is a review deadline, not a claim that upstream has specified that exact
end-of-life day. Recheck the official schedule before that boundary and update
or remove the branch through reviewed policy changes.

| Python | Upstream scheduled end of life | Conservative local cutoff |
| ------ | ------------------------------ | ------------------------- |
| 3.11   | 2027-10                        | 2027-10-01                |
| 3.12   | 2028-10                        | 2028-10-01                |
| 3.13   | 2029-10                        | 2029-10-01                |
| 3.14   | 2030-10                        | 2030-10-01                |

Package `requires-python` and both workflow matrices must exactly match the
reviewed ordered contiguous branch inventory. Missing declarations, unsupported
branches, duplicate keys, altered canonical snapshot bytes and malformed dates fail.
Workflow parsing uses PyYAML's safe loader. Aliases, anchors, duplicate mapping
keys, non-string keys, multiple documents and invalid UTF-8 are rejected.
The local typed adapter declares documented parser results missing from the
upstream stubs; it does not change the parser or suppress analyzer findings.
An offline native strict Mypy consumer checks the adapter's documented scan,
composition and safe-load result types. It disables incremental reads so a
changed annotation cannot reuse an earlier valid type-check result. Missing or
failed checker execution fails the test. Calendar forms are checked explicitly
as YYYY-MM-DD before native date parsing; basic and week-date ISO forms fail.
The adapter defers annotation evaluation on all declared Python versions.
This keeps a malformed annotation from failing import before the strict native
type consumer can reject it, including on Python 3.11 through 3.13.

The workflow requests full Linux analysis, coverage and every mutation for each
branch, plus build/install/product behavior on Linux, macOS and Windows.
A declared matrix is not proof that its jobs passed. Native local clean and
negative probes qualify the runtime gate; its full coverage/mutation admission,
current complete runtime/platform matrices and final hosted enforcement remain
pending. Local Python 3.14.6 evidence for earlier slices remains revision-bound.

Before publication or a policy renewal, verify upstream support, review current
patch releases and run the complete replacement matrix. This branch-support
gate does not establish that an installed patch has no known vulnerabilities.
Dependency scans and the [security policy](security.md) remain independently
required. Do not silently omit a failing runtime or operating system.
