# Local documentation links

`python -m quality.document_links_main` uses the locked CommonMark parser to
discover links and image targets in every authored Markdown file. It rejects
missing or unenrolled local destinations, paths outside the repository,
unsupported URL schemes and missing heading fragments. Duplicate headings get
numbered anchors. The gate rejects symlinked authored entries, invalid UTF-8,
stale or redirected reports and source edits during the check. Its receipt
binds each document to a SHA-256 digest and lists external URLs separately;
external site availability does not affect this local gate.

The full hosted Linux analysis matrix runs this gate on every declared Python
version. The local check records external links without claiming remote
availability.
