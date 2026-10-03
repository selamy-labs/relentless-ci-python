# Markdown style

`python -m quality.document_style_main` checks every authored Markdown file
against locked mdformat 1.0.0 with the mdformat-gfm 1.0.0 plugin. The gate
compares the pinned formatter's output without editing source files. Missing
formatters or plugins, version drift, noncanonical Markdown, invalid UTF-8,
symlinked authored entries, stale or redirected reports and source edits fail.
The receipt binds each checked document to its SHA-256 digest.

The style gate checks canonical GFM formatting. Local links and spelling have
separate native gates. Full Linux analysis runs all three gates on every declared
Python version.
