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
not select tests or change operators. The native trial bound is 60 seconds.
Credit requires actual pytest status 1, empty stderr, a completed `FAILED tests/`
record and the exact one-failure summary. Signals, arbitrary nonzero exits,
runtime diagnostics, duplicate JSON keys and missing or malformed records fail.
The complete native plan, worker outcomes and source restoration remain required.

Each coordinator and worker binds `PYTEST_DEBUG_TEMPROOT` to its own existing
workspace. Pytest therefore keeps temporary tests and cleanup inside that
workspace rather than sharing another worker's numbered directories. Test
selection and strict warnings remain unchanged.

Source, tests and protected configuration are copied into a temporary directory.
The verifier compares their bytes with the original snapshot after execution,
including the checkout, so changed inputs or unrestored mutations fail. The raw
SQLite result is retained in `.quality-results/mutation-latest.sqlite`; only a
validated session is also saved as `.quality-results/mutation.sqlite`.

Individual trials have a 60-second limit. Initialization and baseline use the
ordinary 1,800-second command deadline. Full mutation execution has a separate
21,240-second deadline in `quality/mutation-timeout.json`. These deadlines bound
execution; reaching one never counts as a killed mutant or a successful gate.
The 3,600-second pool bound failed after 3,800 of 3,951 bootstrap mutants were
killed; its failure archive is retained. The expanded bound and 359-minute CI
job ceiling match the independently audited publication candidate's recorded
runtime policy. Neither mutation scope nor kill classification changes.

Run the same full local verifier described in the README. It requires no paid
service or account credentials for mutation analysis. Hosted matrix enforcement
is pending publication of this template.
