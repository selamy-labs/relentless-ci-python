# Security gates

The full verifier runs pinned Gitleaks, OSV-Scanner and Opengrep, then independently validates their reports. Tool failure, timeout, malformed/missing output, findings and incomplete scan inventories fail. Reports under `.quality-results` are deleted before each run; existing results cannot substitute for a new scan. No severity threshold or vulnerability exception is configured.

Gitleaks checks the working tree and all locally available Git history, redacts output and ignores inline suppression comments. Hosted checkouts must fetch full history. An explicitly empty ignore file prevents accidental use of a contributor's root fingerprint-ignore file. The config extends the default rules and exempts only protected generated/cache paths. Source enrollment rejects tracked files in generated root exemptions and authored Python in nested generated directories. These exemptions are not a license to store maintained source there.

OSV scans the complete UV lock graph, including development, transitive and platform-specific packages. Its report must identify the requested lockfile and every distinct locked name/version/ecosystem tuple. Findings, scanner errors, duplicate or substituted package records, omitted packages and empty inventories fail independently of the scanner exit code. Unknown future report fields do not authorize exceptions.

Opengrep uses six local rules, three applicable to Python: dynamic evaluation, unsafe deserialization and input-to-shell taint. This is an explicit baseline, not an exhaustive catalogue of security weaknesses. Input crossing helper functions is analyzed using intrafile taint. The engine disables inline suppressions, bypasses Git/Opengrep ignore files and file-size skipping, and treats warnings/errors/findings as failures. The reported scanned-file set must exactly equal independent source discovery. Skipped rules fail. The internal ignore-bypass option is pinned with the engine; changing it requires completeness probes.

`mise.toml` and `mise.lock` pin Gitleaks 8.30.1, OSV-Scanner 2.6.0, Opengrep 1.30.0 and UV 0.11.26 with exact platform URLs and checksums for Linux x64, macOS arm64/x64 and Windows x64. Run with Git, Mise 2026.9.16 and a supported Node runtime (for Pyright) installed:

```sh
mise --yes --locked exec -- uv run --locked --group dev python -m quality.verify
```

This selects a compatible Python through UV. Python 3.11–3.14 are the declared
target runtimes. Hosted full-analysis jobs run the same command independently
for each version, and installed behavior runs on Linux, macOS and Windows. The
separate App-owned check and native branch protection enforce policy changes.

The language lock audit does not cover native analyzer binaries; their artifact hashes are pinned separately. Security tooling cannot prove absence of all vulnerabilities, and unreported upstream vulnerabilities are outside known-vulnerability scans.

Primary references: [OSV report/exit semantics](https://github.com/google/osv-scanner/blob/main/docs/output.md), [Opengrep engine](https://github.com/opengrep/opengrep), [Mise locks](https://mise.jdx.dev/dev-tools/mise-lock.html), [Gitleaks usage](https://github.com/gitleaks/gitleaks).
