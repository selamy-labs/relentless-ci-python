# Relentless CI — Python

A framework-neutral starting point for a small typed library and JSON CLI,
with strict quality checks that also test their executable verifiers.

This is an implementation draft. Local gates are verified; public hosted CI,
the runtime/platform matrix and live repository protections are still being
completed. See individual gate documents for precise scope and limitations.

## Run the full local verifier

Prerequisites: Python 3.11–3.14, Node.js (for Pyright), Git and [Mise](https://mise.jdx.dev/). Run from the repository root:

```sh
mise --yes --locked exec -- uv run --locked --group dev python -m quality.verify
```

The full command installs locked development tools, runs the checked-in gate
definitions, scans secrets/dependencies/source security, and runs full mutation
testing. Tool downloads and vulnerability queries need network access; code
checks require no accounts or credentials. Mise pins native scanner versions
and platform artifact hashes. A missing tool, failed command, malformed report
or incomplete inventory fails verification.

The configured local tools include Black, Ruff, strict mypy/Pyright, Vulture, Complexipy, pytest/Hypothesis and Cosmic Ray. Strict policy values are
399 physical lines per authored file, cognitive complexity 5, cyclomatic
complexity 10, and 100% line and branch coverage. Mutation must conclusively
kill every planned valid mutant. No equivalent-mutant exceptions are in use.

## Example behavior

The example normalizes bounded integer half-open intervals `[start, end)`.
Endpoints range from -1,000,000 through 1,000,000 and `start < end`. It sorts
and merges overlapping or adjacent intervals without changing its input.

```sh
mise --yes --locked exec -- uv build
printf '[[5,8],[1,3],[2,6]]' | mise --yes --locked exec -- uv run --locked relentless-example
```

Output is `[[1,8]]` followed by a newline. Valid input exits 0; malformed input
writes a useful error to stderr and exits 2. Boolean, fractional and nonfinite
endpoints are invalid. Integral JSON numeric values are accepted.

Product code is in `src/relentless_example`. Tests include behavior/boundary examples,
CLI streams and exit statuses, idempotence and permutation properties, and an
independent bounded set-union model. Keep the verifier tests when replacing
the example library with your own application.

## Understand a failure

- [Source enrollment and physical lines](docs/source-scope.md)
- [Mutation outcomes and completeness](docs/mutation.md)
- [Secret, vulnerability and static security scans](docs/security.md)
- [Workflow syntax, shell checks and security](docs/workflows.md)
- [Reviewed runtime support and required matrices](docs/runtimes.md)
- [Dependency and architecture boundaries](docs/architecture.md)
- [Support-file syntax and conditional shell checks](docs/support-files.md)
- [README example execution](docs/readme-example.md)
- [Local documentation links](docs/document-links.md)
- [Native documentation spelling](docs/document-spelling.md)
- [Markdown style](docs/document-style.md)
- [Bounded CLI fuzzing](docs/bounded-fuzz.md)
- [Incomplete and disabled source](docs/incomplete-source.md)
- [Native duplication detection](docs/duplication.md)
- [Public archives and installed consumers](docs/packages.md)
- [Policy inspirations and chosen thresholds](docs/policy-provenance.md)

Fix the underlying defect and rerun the full command. Do not shrink source
scope, lower thresholds, add broad suppressions, ignore unsuccessful mutants
or substitute a faster profile for required verification. Changes to policy
need explicit rationale and approval from trusted maintainer/platform state;
that hosted enforcement is not yet installed in this draft.

## Adapt the starting point

Replace the example in small steps, update package names and entry points, and
regenerate the dependency lock using the native package manager. Keep authored
code inside enrolled locations. New extensions, generated paths and analyzer
limitations must be enrolled explicitly before verification can accept them.

MIT licensed; see [LICENSE](LICENSE).

See [command deadlines and test ordering](docs/processes.md).
