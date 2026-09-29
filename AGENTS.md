# Working in this template

- Run `mise --yes --locked exec -- uv run --locked --group dev python -m quality.verify` from the repository root before proposing a merge.
- Preserve 399 physical lines, cognitive complexity 5 and cyclomatic complexity
  10 for all authored code, including tests and verifier/config code.
- Preserve 100% line and branch coverage and complete raw mutation accounting.
  Timeouts, errors, missing outcomes or excluded scope cannot count as kills.
- Use the same checked-in gate definitions locally and in CI. Keep all new
  source enrolled; generated exemptions need a reproduction and freshness proof.
- Test behavior and negative gate cases. Maintain native report/inventory checks.
- Do not weaken policies or add suppressions without rationale and trusted
  maintainer approval. PR changes cannot grant their own approval.
- Never execute untrusted PR code with privileged credentials or repository
  secrets. Use isolated hosted runners with explicit least permissions.
- Consult `docs/` for analyzer semantics, remediation and current limitations.
- Report actual evidence and remaining work; a local pass does not prove hosted
  repository enforcement or an untested runtime/platform combination.
