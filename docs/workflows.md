# Workflow validation and execution

The full local verifier runs `python -m quality.workflows_main` from its shared
check registry. The gate independently enumerates `.github/workflows`, including
hidden and Git-ignored files. At least one regular `.yml` or `.yaml` file is
required. Linked parent directories, symlinks, subdirectories and unsupported
extensions fail before native analysis. Absolute paths identify every workflow.

Mise pins Actionlint 1.7.12, ShellCheck 0.11.0 and Zizmor 1.30.1 with platform
artifact hashes. The exact ShellCheck version receipt is required before
Actionlint checks YAML, expressions, action inputs and embedded shell scripts.
Zizmor runs offline with pedantic audits, strict collection and ignore bypass.
Each native child has a 30-second deadline and receives no stdin. Tool failures,
timeouts, invalid UTF-8, malformed reports and any finding fail verification.
The previous success receipt is removed before discovery; only a current clean
JSON array is saved to `.quality-results/workflows-security.json`.

Offline audits require no GitHub credentials. Remote API-dependent action
vulnerability checks are outside this gate's verified scope. Consult
[Actionlint](https://github.com/rhysd/actionlint),
[ShellCheck](https://www.shellcheck.net) and
[Zizmor](https://docs.zizmor.sh/usage/) for analyzer semantics and remediation.
Fix reported workflow or shell defects, then rerun the full command. Contributor
ignore files and inline Zizmor ignores cannot substitute for a clean result.
The native credential audit flags implicit persistence but accepts an explicit
`persist-credentials: true` as intentional. The checked-in workflow uses `false`.
See the [credential audit](https://docs.zizmor.sh/audits/#artipacked).

The checked-in workflow runs the same complete local command, including full
mutation, on Linux for Python 3.14, the newest declared version. Python 3.11,
3.12 and 3.13 run `python -m quality.analysis_main`: every gate of that command
in the same order except the final mutation phase. The shared
`quality.pipeline.analyze` function defines that prefix, so the two commands
cannot drift. The matrix `include` entry sets `mutation: true` only for 3.14,
and job names stay `Full analysis (Python X)` for every version. All four
versions also run product unit/property/CLI tests, native archive checks and
isolated installed consumers on Linux, macOS and Windows. Standard hosted runners use read-only
permissions, no persisted checkout credentials and actions pinned to commits.
Mise and UV installers have exact version and artifact digest pins. Installer
caches are disabled and runtime downloads are disabled after setup-python.

The aggregate job runs after both matrices and accepts only two `success`
results. The analysis result covers the 3.14 mutation job, so a failed,
cancelled or skipped mutation phase fails the aggregate gate. Failed, skipped, cancelled or missing results fail its shell check.
Analysis receipts are retained for seven days even on failure. Daily main runs
repeat the checks to detect newly disclosed dependency vulnerabilities.

The source repository's protected branch requires pull requests, the aggregate
`Relentless CI gate` check from the GitHub Actions App (strict and up to date),
conversation resolution and administrator enforcement; no approving review is
required. The `CODEOWNERS` file assigns the whole repository, including `.github`,
to two administrators. Generated copies must configure and read back their own
protection settings; the checked-in workflow alone does not establish live
enforcement.

The offline [runtime-support gate](runtimes.md) also requires both Python
matrices and package metadata to match a current reviewed upstream snapshot.
Each compatibility job runs it after installing the locked environment.
