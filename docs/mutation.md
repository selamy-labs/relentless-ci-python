# Full mutation verification

The local verifier initializes a fresh Cosmic Ray session and runs its baseline
before executing the complete mutation plan. Product code and Python verifier
code are included. Every planned mutant must have a normal, killed outcome;
survivors, missing results, execution errors and timeouts fail. Equivalent-mutant
exclusions are not permitted by this template's policy.

Source, tests and protected configuration are copied into a temporary directory.
The verifier compares their bytes with the original snapshot after execution,
including the checkout, so changed inputs or unrestored mutations fail. The raw
SQLite result is retained in `.quality-results/mutation-latest.sqlite`; only a
validated session is also saved as `.quality-results/mutation.sqlite`.

Individual trials have a 30-second limit. Initialization and baseline use the
ordinary 1,800-second command deadline. Full mutation execution has a separate
3,600-second deadline in `quality/mutation-timeout.json`. These deadlines bound
execution; reaching one never counts as a killed mutant or a successful gate.
The separate execution budget accommodates the complete verifier mutation plan.

Run the same full local verifier described in the README. It requires no paid
service or account credentials for mutation analysis. Hosted matrix enforcement
is pending publication of this template.
