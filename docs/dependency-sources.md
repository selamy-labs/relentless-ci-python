# Dependency source and artifact policy

The registered local command and each Linux full-analysis job run
`python -m quality.dependency_policy_main` after `uv lock --check`. The native
UV check verifies manifest/lock consistency but does not reject a changed
registry origin by itself. This independent gate requires every third-party
locked package to use `https://pypi.org/simple` and every locked sdist and
platform wheel to use `https://files.pythonhosted.org/packages/` over HTTPS,
with a canonical SHA-256 digest and positive size. The single editable package
must be this project's root. URL credentials, custom ports, queries, fragments,
nonregistry sources and unlisted artifact formats fail.

The gate reads all locked packages and artifacts, including platform wheels not
installed on the current machine. To change the registry or artifact policy,
update the protected source and tests with an explicit rationale, obtain
independent maintainer approval, and rerun the complete mutation and hosted
matrix. A green UV lock check alone is insufficient. This is source-integrity
policy, not a vulnerability, license or legal compatibility verdict.
