# Authored source enrollment

The full local command discovers Python source independently of Git ignore rules before running any tool. All authored Python, including tests and executable verification code, must live in `src`, `tests`, or `quality`. New root Python files and `.pyi`/`.pyw`/uppercase variants fail until their complete analysis scope is enrolled through reviewed policy changes. Discovery includes nested and never-imported files; normal analysis and mutation commands cover the supported roots.

Every enrolled file has at most 399 physical lines, including blank lines and comments. LF and CRLF input and an optional terminal newline are covered by boundary probes. Symlinks fail. Python source in bytecode caches or nested generated directories fails because downstream analyzers may ignore those locations. Generated exemptions apply only at the repository root. Tracked files in exempt directories fail even if forced past Git ignore rules.

The same local/CI pipeline reads the complete NUL-delimited Git index and
rejects empty or incomplete inventories, duplicate entries, file or directory
prefixes that collide after NFC and casefold normalization, Windows device
names and reserved characters, dot components, and trailing dots or spaces.
All discovered Python modules and package directories under the supported
roots use snake_case; `__init__.py` and `__main__.py` retain their standard
Python names. These rules prevent a checkout from silently selecting different
files on Linux, macOS and Windows. Fix the actual filenames instead of adding
an ignore entry; new names remain subject to the same source, coverage and
mutation scope.

Protected root-generated areas are `.git` (Git metadata), `.venv` (`uv sync --locked --group dev`), `.codegraph` (local indexing), `.pytest_cache` (`python -m pytest`), `.hypothesis` (Hypothesis tests), `.mypy_cache` (`mypy`), `.ruff_cache` (`ruff`), `.quality-results` (mutation and gate reports), `node_modules` (optional local Node tooling), `dist` (`uv build`), and `coverage` (coverage reports). None may contain tracked inputs. These entries authorize local generated state, not maintained-source exclusions. Hosted jobs must recreate environments and artifacts from protected inputs; the complete hosted freshness checks are still being implemented.

The checker itself is covered and mutated with the rest of `quality`. Hosted enforcement and trusted policy-change approval are pending. This does not claim that the remaining security, architecture, compatibility or packaging gates have been delivered.
