# Command deadlines and test order

The full command runs tools with structured arguments, the requested working
directory and environment, and finite deadlines. Missing tools and nonzero exits
fail. A timeout never counts as a mutation kill.

For ordinary tools on POSIX, each tool starts a new session. On timeout the runner
kills the owned process group, including children that remain in that group,
and reaps the direct child before temporary-directory cleanup. An already-gone
group is harmless; other
termination failures propagate. Reaping has a separate 20-second bound. A
termination failure still triggers direct-child cleanup and cannot pass.
Windows timeout handling invokes the native `taskkill /T /F` tree operation and
checks its status before reaping. Its command contract has unit witnesses;
native Windows evidence must come from the declared hosted matrix. Local Linux
execution does not establish that platform result.

The native Linux descendant probe starts a child that would write after its
parent times out. Successful cleanup leaves no delayed marker. The prior Linux
mutation run exceeded its unchanged 3600-second execution deadline; direct-child
termination raced pytest cache creation and masked the timeout with a temporary
cleanup error. The failed run and partial raw database remain preserved as
failure evidence, not a passing mutation result.

A second full run exposed the remaining limit: Cosmic Ray starts each pytest
trial in a separate session. Its trial-group cleanup occurs only on its own
trial timeout. Killing the Cosmic Ray parent group at the full execution
deadline leaves that separately started trial alive, so cache creation can still
race temporary cleanup. The second timeout and complete retained partial raw
database are failure evidence.

Mutation initialization, baseline and execution now use a dedicated Linux
supervisor. It enables and reads back kernel subreaper and creator-death settings,
launches the command in its own session, and adopts orphaned descendants across
sessions. It signals only positive PIDs in its current direct-child inventory,
then kills and reaps all owned descendants before returning. Signed exit codes
and timeouts remain failures; a successful command that leaves children fails.
The tool deadline is unchanged. Cleanup has a separate 20-second bound.

Fresh completion receipts bind a unique request nonce and require complete
reaping evidence. Missing, malformed or stale receipts cannot pass. A caller
interrupt requests graceful cleanup with a bounded wait and raises an unproven
supervision failure. It never hard-kills the supervisor before descendant cleanup.
Failure workspaces are copied with their database, sidecars, source and receipts
before deletion. Unproven cleanup or a failed archive keeps the original workspace.

Successful workspaces also remain available in a fresh
`.quality-results/mutation-success-*/workspace` archive before temporary cleanup.
This retains the complete native database, worker journals, supervision requests
and receipts, exact input copies and generated trial launchers. Each run has its
own archive; old reports cannot substitute for the current run. If copying fails,
the verifier fails and leaves the original workspace intact. Hosted artifact
uploads include successful and failing archives with hidden receipt directories.

Native Linux probes cover separate-session timeout/root-exit children, signed
failures, interrupts with warnings treated as errors, and creator death. Actual
Cosmic Ray timeout probes reap its separate trial session and retain the partial
database as failure evidence. These establish lifecycle behavior, not a complete
mutation pass. Native non-Linux lifecycle contracts remain pending.

The full mutation command now initializes and baselines the unchanged native
configuration, then starts up to eight isolated HTTP worker copies. Each worker
uses its own source and Python import path. The coordinator derives only the
HTTP transport settings and reads them back independently; source scope,
operators and test command remain unchanged. Complete execution now uses a
60-second native trial and a 14,400-second whole-pool deadline. Worker service
lifetime and shutdown allowances bound startup and cleanup, and cannot turn a
failed execution into a pass.

Every worker is registered before readiness. Readiness and stop markers use a
fresh private nonce and atomic publication. All workers receive a stop request
before shutdown waits; failures are aggregated, including any unproven owner.
Before success, every input copy must be restored and completed worker journals
must match the complete native mutation plan exactly. Missing, duplicate or extra
jobs and changed trial settings fail. A small native corpus qualifies the pool;
complete product mutation remains required before claiming full verification.

Collected tests are sorted deterministically by node identifier, with costly
native pytest-receipt probes and the native descendant probe last. No case is
filtered, renamed, retried or exempted. Native collector/completion inventories
still have to match exactly. The ordering function remains in coverage and
mutation scope. An independent probe kept all 490 prior completed identifiers
and baseline success while reducing one workflow-defect failure from 7.33 to
4.21 seconds. That optimization did not change the then-current 3600-second
pool or 30-second trial deadlines, and did not use cached outcomes. The later
hosted throughput review and current 14,400-second pool bound are documented in
`docs/mutation.md`; the per-mutant bound is now 60 seconds.
