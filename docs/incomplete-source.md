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
Literal `getattr` access to these named APIs also fails. Concrete functions and
methods containing only `pass` or ellipsis, even after a docstring, and explicit
`raise NotImplementedError` fail as unfinished implementations. Empty classes
are valid declarations, including marker and exception classes. A `pass` used
to handle a known exception remains valid. Bare `print` is not classified as
debug output because the verifier and CLI use stdout for protocol results;
output correctness has separate tests.

Direct Protocol methods and methods decorated with `abc.abstractmethod` may
declare a stub with `pass`, ellipsis or a sole `raise NotImplementedError`.
Explicit imports from `typing`, `typing_extensions` and `abc`, their import
aliases and Protocol subscripts are recognized. Recognition requires an
unambiguous binding in the relevant lexical scope; relative or wildcard
imports, rebinding and arbitrary assignment aliases cannot establish an
exemption. Unrelated child scopes do not invalidate parent imports. Nested
concrete definitions and other forbidden APIs remain checked. This narrow
recognition does not infer inheritance or resolve general dynamic data flow;
the native type checkers remain authoritative for typing.

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
directives, nested inventory and an empty inventory. The full hosted matrix
runs this gate, and protected changes require the App-owned policy check.
Arbitrary computed attribute names are outside this syntactic rule; the
repository also runs strict type/lint, security, coverage, complete test-result
and full mutation gates.
