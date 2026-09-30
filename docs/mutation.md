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

The launcher runs exactly `python -m pytest -x -q --color=no`.
The adapter retains pytest stdout, stderr and
its signed exit status in a fresh JSON record inside the native result. It does
not select tests or change operators. The native trial limit is 60 seconds.
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
14,400-second deadline in `quality/mutation-timeout.json`. These deadlines bound
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
contention. The 60-second individual trial, 14,400-second whole-pool bound and
260-minute hosted job allow complete classification of the broader plan. They
do not reduce the test inventory, source scope, operators or result validation;
timeouts, cancellations and partial outcomes still fail. The broader inventory
must qualify independently before its hosted result can be credited.

Run the same full local verifier described in the README. It requires no paid
service or account credentials for mutation analysis. Hosted matrix enforcement
requires a green run on the repaired published main revision.
