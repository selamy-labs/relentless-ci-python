# Incomplete and disabled Python source

The common local and hosted check registry runs
`python -m quality.incomplete_main` before build, test and mutation work. It
scans every authored `.py` file discovered under `src`, `tests` and `quality`,
including nested and never-imported files. A missing source inventory fails.
The checker parses Python syntax and comments separately, so words inside
strings and test fixtures do not become false positives.

The gate rejects debugger calls (`breakpoint`, `pdb.set_trace`,
`pytest.set_trace`), direct pytest skip/xfail APIs, unittest
skip/expected-failure decorators, and their directly imported aliases.
Literal `getattr` access to these named APIs also fails. Definitions containing
only `pass` or ellipsis, even after a docstring, and explicit
`raise NotImplementedError` fail as unfinished implementations. A `pass` used
to handle a known exception remains valid. Bare `print` is not classified as
debug output because the verifier and CLI use stdout for protocol results;
output correctness has separate tests.

Lexical comments containing TODO, FIXME or XXX, or suppression directives for
Ruff, typing, coverage, formatting and security scanning fail. Quoted examples
do not count as comments. The gate has no per-file or inline exemptions. Fix
the code, remove disabled tests, or add the missing assertions rather than
suppressing analysis. The independent pytest JSON validator also rejects
skipped, xfailed, deselected and uncollected tests at runtime; this source gate
closes common static routes that runtime receipts cannot detect when a disabled
path is never collected.

Native temporary-source probes cover clean handling, imported aliases,
decorators, literal dynamic access, placeholders, comment markers, suppression
directives, nested inventory and an empty inventory. This gate is in an isolated
candidate: full mutation on every supported Python runtime, hosted
installation/behavior, protected review and publication remain pending.
Arbitrary computed attribute names are outside this syntactic rule; the
repository also runs strict type/lint, security, coverage, complete test-result
and full mutation gates.
