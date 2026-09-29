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
`persist-credentials: true` as intentional. The checked-in workflow uses `false`;
enforcing that policy against contributor changes requires the still-pending
trusted policy gate. See the [credential audit](https://docs.zizmor.sh/audits/#artipacked).

The checked-in workflow runs the same complete local command, including full
mutation, on Linux for Python 3.11, 3.12, 3.13 and 3.14. All four versions also
run product unit/property/CLI tests, native archive checks and isolated installed
consumers on Linux, macOS and Windows. Standard hosted runners use read-only
permissions, no persisted checkout credentials and actions pinned to commits.
Mise and UV installers have exact version and artifact digest pins. Installer
caches are disabled and runtime downloads are disabled after setup-python.

The aggregate job runs after both matrices and accepts only two `success`
results. Failed, skipped, cancelled or missing results fail its shell check.
Analysis receipts are retained for seven days even on failure. Daily main runs
repeat the checks to detect newly disclosed dependency vulnerabilities.

The local native gate has passed on Linux with the pinned tools. Hosted runs,
the complete runtime/platform matrix, trusted policy-change approval and live
required-check protections remain pending. Local scanner success does not prove
that a contributor cannot alter a workflow or forge its status context.
