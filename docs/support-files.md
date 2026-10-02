# Support-file correctness

The common local and hosted check registry runs
`python -m quality.support_files_main` before build, test and mutation work. The
gate walks authored paths, including hidden and ignored files, while excluding
only protected top-level generated roots. Symlinked or unsupported filesystem
entries fail. A nonempty inventory is required, and a fresh success receipt
lists the SHA-256 digest of every checked file. Missing, redirected, stale or
changed-input receipts cannot pass.

Every present `.json`, `.toml`, `.yml`, `.yaml` and `.ini` file is decoded as
strict UTF-8 and parsed. Native `mise.lock` and `uv.lock` are parsed as TOML.
JSON rejects duplicate keys and nonfinite constants. YAML rejects duplicate
mapping keys, anchors and aliases. INI rejects duplicate sections and options.
The existing workflow gate separately validates Actions semantics and embedded
shell with pinned Actionlint, ShellCheck and Zizmor; syntax parsing here does
not replace those checks.

If an authored `.sh` file appears, this gate verifies the pinned ShellCheck
version and runs ShellCheck with `--norc` over every discovered shell path.
Inline `shellcheck disable` directives fail as well. No standalone
shell file is currently present, so the clean template receipt records the
format inventory without claiming a shell run. Native temporary projects prove
both clean and defective shell behavior, missing tool, wrong version, malformed
formats, stale receipt, hidden inventory, symlink and changed-input failures.

Fix malformed or duplicate configuration, repair shell diagnostics, and rerun
the common full command. The hosted full-analysis matrix runs this gate on every
declared Python version; protected policy changes require the App-owned check.
