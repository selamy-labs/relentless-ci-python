# Full mutation verification

The local verifier initializes a fresh Cosmic Ray session and runs its baseline
before executing the complete mutation plan. Product code and Python verifier
code are included. Every planned mutant must have a normal, killed outcome;
survivors, missing results, execution errors and timeouts fail. Equivalent-mutant
exclusions are not permitted by this template's policy.

The native trial command executes `.quality-results/mutation-trial.py`, generated
byte-for-byte from enrolled `quality/mutation_trial.py` before the baseline and
each worker starts. That source remains fully covered and mutated. The runtime
copy prevents a candidate from changing the launcher before tests can detect it.
Worker requests verify its bytes before and after native execution; stale copies
are replaced, and missing or changed copies fail. The reproduction command is
`python -c 'from pathlib import Path; from quality.trial_launcher import prepare_launcher; prepare_launcher(Path.cwd())'`.

The launcher runs `python -m pytest -x -q --color=no`, optionally followed by
selected test function ids. Before the baseline, the coordinator runs the whole
suite once with `--cov --cov-context=test` and writes
`.quality-results/mutation-coverage.json`: the pristine text of every `src` and
`quality` module and, for each line inside a function body, the test functions
whose execution reached any line of the innermost enclosing statement. Lines in
signatures, decorators, class or module bodies, lines executed during import or
collection, and lines no test executed stay unmapped. The enrolled
`quality.mutation_context` plugin exports `COVERAGE_PROCESS_START` and the
current test id during each test, so Python subprocesses that inherit the
environment are measured with that test's context and native subprocess tests
remain selectable. A subprocess started with a scrubbed environment is not
measured; a mutant killed only there would survive and fail the gate rather
than pass. The map run forces `COVERAGE_CORE=ctrace` because the Python 3.14
default `sysmon` core drops per-test contexts. Coverage startup slows each
measured child by about 0.1 seconds, which can trip sub-second native timing
tests, so the map run accepts pytest's tests-failed status 1 and keeps the
contexts recorded before that failure. Any other status or a timeout still
fails, and the owned supervisor still reaps every descendant. A shortened context can only drop tests from a selection,
which may create a survivor but never a kill. The ordinary test gate and the
complete baseline still require every test to pass. Each worker receives a
byte copy, and every request verifies those bytes before and after native
execution, exactly like the launcher.

A trial compares the workspace with the pristine sources. Only one changed
module whose changed lines keep the original line count and are all mapped
narrows the command to the union of their covering test functions, in the
unchanged conftest order. No map, no change, several changed modules, added or
removed lines, or any unmapped line runs the complete suite. Selection never
changes operators, the mutant plan or result validation, and a mutant that no
selected test kills is still a survivor. The `cosmic-ray baseline` still runs
the complete suite because nothing has changed.

The adapter retains pytest stdout, stderr and its signed exit status in a fresh
JSON record inside the native result. The native trial limit is 60 seconds.
Credit requires actual pytest status 1, empty stderr, a completed `FAILED tests/`
record and the exact one-failure summary. Signals, arbitrary nonzero exits,
runtime diagnostics, duplicate JSON keys and missing or malformed records fail.
The complete native plan, worker outcomes and source restoration remain required.

Each coordinator and worker binds `PYTEST_DEBUG_TEMPROOT` to its own existing
workspace. Pytest therefore keeps temporary tests and cleanup inside that
workspace rather than sharing another worker's numbered directories. Test
selection, strict warnings and deadlines remain unchanged.

Source, tests and protected configuration are copied into a temporary directory.
The verifier compares their bytes with the original snapshot after execution,
including the checkout, so changed inputs or unrestored mutations fail. The raw
SQLite result is retained in `.quality-results/mutation-latest.sqlite`; only a
validated session is also saved as `.quality-results/mutation.sqlite`.
Raw report validation reads a private temporary copy and never opens the
original database for writes. This avoids platform-dependent SQLite URI
handling while preserving the exact complete-result check.

Individual trials have a 60-second limit. Initialization and baseline use the
ordinary 1,800-second command deadline. Full mutation execution has a separate
21,240-second deadline in `quality/mutation-timeout.json`. These deadlines bound
execution; reaching one never counts as a killed mutant or a successful gate.
The separate execution budget accommodates the complete verifier mutation plan.
The first hosted Linux matrix, on standard four-CPU runners, retained between
2,178 and 2,783 of 2,798 raw results at the former 3,600-second deadline.
All four jobs failed. The first 6,000-second repair passed the source template's
hosted PR matrix, but a renamed private instantiation of the same 2,769-mutant
plan exceeded 6,000 seconds on Python 3.11, 3.12 and 3.13. With a 9,000-second
pool, Python 3.11 completed all 2,769 native kills, while the other three jobs
hit the former 120-minute hosted limit. A later run completed 3.11, 3.13 and
3.14, but 3.12 reached the 9,000-second deadline with 141 results missing. The
12,000-second pool and 240-minute hosted job subsequently passed the private
instance and public PR matrices for that narrower plan.

Broad gate enrollment then expanded the plan to 4,142 mutants. An isolated
9,000-second run completed its native plan but retained 299 literal `timeout`
outputs, which the strict validator rejected even where Cosmic Ray labelled
them killed. The full baseline takes about 20 seconds on this host, leaving
little headroom under a 30-second trial limit for a surviving mutant or worker
contention. The 60-second individual trial, former 14,400-second whole-pool bound and
260-minute hosted job allowed classification of the earlier broader plan. They
do not reduce the test inventory, source scope, operators or result validation;
timeouts, cancellations and partial outcomes still fail. The broader inventory
must qualify independently before its hosted result can be credited.

The public 4,318-mutant PR run completed Python 3.14 but hit the 14,400-second
pool deadline on 3.12 with only 3,927 recorded results. Python 3.11 and 3.13
reported uncreditable pytest collection errors from mutation of an evaluated
type annotation. The annotation is quoted in this candidate so its static
meaning remains intact. The private renamed-copy matrix also timed out with
partial raw sessions on all four Linux runtimes. The owned pool allowance is
now 354 minutes and the standard hosted analysis job 359 minutes, below the
six-hour hosted job ceiling. A timeout still fails, and every source, operator,
test, and raw-result integrity check remains enrolled.

A complete 4,318-result local session identifies each mutant's first failing
test, and a hosted Python 3.13 baseline supplies all 1,378 test timings. The 30
cheapest high-yield witness files now run first while the entire collected test
inventory and `pytest -x` trial command remain unchanged. The historical model
reduces mean time before a known failure from 7.69 to 2.67 seconds; process
startup and mutation interactions are not modeled. The fixed rank and unknown
file fallback are source-bound and tested. A fresh full local run and all four
hosted Linux runtimes must prove the actual speed and strict kills.

The separate protected-base bootstrap candidate also exceeded the former
3,600-second pool bound after 3,800 of 3,951 native kills. Its failure
archive was retained; the expanded deadline then passed all 3,951 local
trials without changing source scope, operators, or kill classification.

This historical note is retained as a changelog-style record of a removed
trusted-policy bootstrap candidate; the issuer itself has been removed.

Hosted CI runs this mutation phase once, inside the Python 3.14 full-analysis
job; Python 3.11, 3.12 and 3.13 run every other gate through
`python -m quality.analysis_main`. Before this change each of the four jobs
repeated the identical mutant plan for about 3.5 to 4 hours. The plan, operators,
kill requirement and receipts are unchanged. A mutant that only an older
runtime's behavior would kill is therefore not checked there; 100% line and
branch coverage and the whole test suite still run on every declared version.
The aggregate gate requires the 3.14 job, so mutation still blocks merges.

Run the same full local verifier described in the README. It requires no paid
service or account credentials for mutation analysis. Hosted matrix enforcement
requires a green run on the repaired published main revision.
