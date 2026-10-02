# Locked build dependencies and archive scope

The required local registry regenerates `quality/build-constraints.txt` from
`uv.lock` and compares the fresh export byte for byte with the committed file.
Missing, empty or stale exports fail. The native build then uses that file with
`uv build --build-constraints quality/build-constraints.txt --require-hashes`.
Each build dependency has an exact version and the approved wheel and source
archive SHA-256 digests from the lock. A dependency update must regenerate the
protected hash file; changing only one side fails verification.

Hatchling and its complete supported-runtime dependency closure are exact
requirements in `[build-system]`. They are also enrolled in the lock and its
known-vulnerability scan. The `build` dependency group supplies the native UV
export, and Hatchling is available to the development environment for auditing.
Native UV 0.11.26 enforces the standard hashed requirements file; its TOML build
constraint field accepts requirement strings rather than newer hash tables.

The source archive uses an explicit public product allowlist: source, license,
README and project metadata. A native probe found that the previous default
source archive included `.codegraph/codegraph.db` and `.complexipy_cache`.
The allowlist removes these local artifacts. The wheel contains the library,
CLI, type marker, license and generated distribution metadata.

The separate package gate validates actual wheel and source archives, rebuilds
the wheel byte for byte, and tests isolated installed consumers. The hosted
matrix runs those gates across the declared runtimes and operating systems.

Native command semantics: [UV build](https://docs.astral.sh/uv/reference/cli/#uv-build).
