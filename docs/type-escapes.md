# Type escape policy

The registered `mypy` gate uses strict mode and rejects explicit `Any` in
authored Python. The registered incomplete-source gate independently scans every
enrolled file for `typing.Any`, including imported aliases, and for calls to
`typing.cast`. A new cast fails unless its file and exact expression appear in
the protected `APPROVED_CASTS` table in `quality/incomplete.py`. Comment-based
type suppressions fail the same source gate.

Two pinned third-party adapters need a variadic `Callable[..., T]` cast because
their runtime call signatures are broader than the local call. The narrow mypy
overrides for `quality.mutation_coordinator` and `quality.document_style` allow
that ellipsis; the independent AST gate still rejects explicit `Any` in those
files. Four other casts narrow pinned external APIs or an exception group. Each
allowed cast records its reason in the protected table, and changing an
expression requires a reviewed policy edit.

These static checks cannot prove that a cast's runtime claim is true. Native
behavior tests and the full mutation and coverage gates exercise the adapters.
The focused negative probes establish detection of explicit `Any`, aliases and
new casts; they do not replace the complete hosted matrix or exact-main proof.
