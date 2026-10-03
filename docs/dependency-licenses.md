# Locked component and license inventory

The registered `python -m quality.component_inventory_main` gate runs after
the approved-source check and before package installation checks. It reads
every registry distribution in `uv.lock`, including platform-specific wheels
absent from the current environment. It rejects a new, removed, duplicate or
changed name/version without an exact entry in `quality/license-policy.json`.
Unknown SPDX expressions, incomplete provenance and a changed project
`LICENSE` file fail. A stale inventory is removed before validation, so a
failed gate cannot leave a current-looking receipt.

The policy is a reviewed snapshot. Each locked release has an explicit SPDX
expression and a SHA-256 fingerprint of either the official version-specific
PyPI metadata response or a license file in its locked source archive. Five
legacy packages needed source-file inspection: `colorama`, `gitdb`,
`mypy-extensions`, `nodeenv` and `yattag`. The output binds this snapshot to
the exact lock and policy hashes, names, versions, source artifact URLs and
hashes, wheel inventories and project notice. CI uploads the fresh
`.quality-results/component-inventory.json` beside security and mutation
reports. A dependency update must renew the matching policy entry and pass
trusted policy-file review.

PyPI's legacy `License` field and classifiers are not always SPDX expressions.
The recorded expressions are explicit review decisions for this lock, not a
legal compatibility verdict or permission to omit third-party notices. The
gate uses pinned local data and needs no network or credentials. Release
attestations remain a separate capability, since this template does not
publish a registry release.

Sources: [PyPI JSON API](https://docs.pypi.org/api/json/),
[Python core metadata](https://packaging.python.org/en/latest/specifications/core-metadata/),
and [SPDX expression syntax](https://packaging.python.org/en/latest/specifications/license-expression/).
