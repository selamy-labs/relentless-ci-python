# Native test discovery and completed results

The full verifier removes the old `.quality-results/tests.json` before the
check registry runs. Its pytest coverage command enables locked
pytest-json-report and writes a new receipt. Missing, malformed or invalid
UTF-8 output fails independently of the runner's exit status.

The validator requires the requested repository root and a successful session
exit. Every test must pass, with completed passing setup, call and teardown
stages. Duplicate node identifiers, empty discovery and incomplete collection
reports fail. The collector leaf identifiers must match the completed test
identifiers exactly, including parameterized cases; missing or duplicate
collected cases fail even if a modified runner hides deselection counts.
Warnings, skip, xfail, unexpected xpass, failed and error results
are forbidden. Collected, total and passed summary counts must equal the
number of completed test records; any additional nonzero outcome or deselected
count fails.

Test-file enrollment independently uses all discovered Python source under
`tests` whose filename matches pytest's `test_*.py` or `*_test.py` convention.
The completed cases must cover exactly that file inventory. Missing and
duplicate expected paths fail, including a new test file omitted by a narrower
runner command. A matching file with no runnable tests also fails.

Seven isolated native subprocess probes exercise complete execution, skip,
xfail, unexpected xpass, keyword deselection, empty discovery and collection
errors. Faulty fixtures live outside the checkout in temporary projects.
Receipt probes separately exercise malformed fields, missing stages, summary
mismatches, stale files and omitted source files.

Custom collection conventions, retry overrides and hosted trusted-policy
enforcement remain pending. The isolated incomplete-source gate now rejects
common static skip, debug, placeholder and suppression forms; see
[incomplete-source.md](incomplete-source.md). Results alone do not establish
assertion quality; independent behavioral properties, coverage and mutation
gates provide additional evidence.

Remediation is to repair failures, remove skip/xfail or selection markers,
restore omitted tests or fix reporter configuration. Do not narrow the
discovered inventory or accept incomplete reports to make verification pass.

Report semantics: [pytest-json-report](https://github.com/numirias/pytest-json-report).
