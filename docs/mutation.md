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
not select tests, change operators or change the native 30-second trial limit.
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

Individual trials have a 30-second limit. Initialization and baseline use the
ordinary 1,800-second command deadline. Full mutation execution has a separate
9,000-second deadline in `quality/mutation-timeout.json`. These deadlines bound
execution; reaching one never counts as a killed mutant or a successful gate.
The separate execution budget accommodates the complete verifier mutation plan.
The first hosted Linux matrix, on standard four-CPU runners, retained between
2,178 and 2,783 of 2,798 raw results at the former 3,600-second deadline.
All four jobs failed. The first 6,000-second repair passed the source template's
hosted PR matrix, but a renamed private instantiation of the same 2,769-mutant
plan exceeded 6,000 seconds on Python 3.11, 3.12 and 3.13. With a 9,000-second
pool, Python 3.11 completed 2,769/2,769 native kills, while the other three
jobs hit the former 120-minute outer hosted limit before their pools ended.
The 9,000-second pool and 200-minute hosted job limit leave measured capacity
for runner variance and report preservation. The 30-second individual trial,
mutation scope, operators, tests and result-integrity checks remain unchanged;
timeouts and cancellations still fail.

Run the same full local verifier described in the README. It requires no paid
service or account credentials for mutation analysis. Hosted matrix enforcement
requires a green run on the repaired published main revision.
