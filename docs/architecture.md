# Dependency and architecture gates

The full verifier runs deptry 0.25.1 and the native Grimp 3.17 import graph.
They inspect all independently discovered files in `src`, `tests` and
`quality`, including never-imported modules. The graph's nonsquashed module
inventory must exactly match discovery. Missing, extra or unsupported modules
fail; a partial graph never passes. Analysis does not execute source imports.

Grimp checks direct edges for cycles using its native reachability analysis,
including cycles across package roots. Production modules cannot import tests
or verifier modules. All owned imports of external packages must resolve to
stdlib or explicitly declared distributions; production receives only
`project.dependencies`, while tooling can also use PEP 735 dependency groups.
Distribution names use packaging's PEP 508 parser and canonicalization and
installed package metadata. Type-checking imports are explicitly included.
Grimp caches are disabled and no edges or modules are suppressed.

Run `python -m quality.architecture_main` inside the locked development
environment for this graph gate alone. The full command uses the same
checked-in registry; no separate local/CI definitions exist.

Deptry additionally checks missing, transitive, development-only and unused
runtime dependencies. Its production command is `deptry src`. Its second
command is `deptry src tests quality --non-dev-dependency-groups dev --ignore DEP002`: development tools are available to tests/verifiers, and unused-package
reporting is disabled for that second scan because many declared developer
tools are CLI entry points. Unused production dependencies remain errors in
the first scan. This does not allow production development imports: both the
first deptry command and Grimp's runtime boundary reject them. Explicit
`exclude = ["^$"]` prevents deptry's default omission of tests. Deptry omits
TYPE_CHECKING imports; Grimp closes that gap.

Use regular packages with explicit `__init__.py` files. Grimp has limitations
around standalone root modules and namespace packages. Those shapes must
receive explicit analyzer support before enrollment; exact graph inventory
checks reject omissions instead of silently exempting them. The existing
`tests` directory has an empty package initializer for full native enrollment.
Missing or malformed manifests, parser failures and unavailable tools fail.

Tests exercise real Grimp parsing of clean imports, declared runtime packages,
unimported nested and cross-package cycles, type-checking imports and graph
completeness. Isolated subprocess projects verify actual production-to-verifier
violations and approved developer imports. Real deptry CLI probes reject each
of DEP001, DEP002, DEP003 and DEP004. Unit probes additionally cover source-name
collisions, missing/extra native inventory, import-path restoration, external
provider normalization and both test/verifier production boundaries.

Fix an edge or declare an actual runtime dependency; do not conceal it through
ignore comments, a fake package mapping or policy changes. Every hosted full
analysis job runs the graph gate, and the protected issuer checks policy changes.

References: [Grimp API](https://grimp.readthedocs.io/en/stable/usage.html) and
[deptry configuration](https://deptry.com/usage/).
