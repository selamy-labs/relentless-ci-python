# Native documentation spelling

`python -m quality.document_spelling_main` runs pinned Typos 1.50.3 on every
authored Markdown file. The gate compares Typos's native `--files` inventory
with independent disk discovery, requires an empty findings report, and writes
a SHA-256-bound receipt. It uses `--isolated` and `--no-ignore`, so an ambient
Typos configuration or Git ignore rule cannot suppress a misspelling. Missing
tools, wrong versions, malformed or incomplete native reports, stale or
redirected receipts and source drift fail the check.

The full hosted Linux analysis matrix runs this gate on every declared Python
version.
