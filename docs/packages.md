# Public archives and installed consumers

The required `quality.package_main` gate builds in a fresh temporary directory
using the protected, hash-locked build constraints. It stages every product
source file and the public README, license, project metadata and lock. Generated
bytecode is omitted. Repository state, verifier code and local indexes stay out
of the published archives.

The actual wheel ZIP and source TAR are read without filesystem extraction.
Compressed bytes are limited to 64 KiB, unpacked content to 256 KiB and raw TAR
bytes to 512 KiB. These are project budgets for this small dependency-free sample.
Plain regular files must have mode 0644; duplicate members, links, directories,
sparse/continuation members and TAR extended headers fail. Native readers reject
malformed archives.
The exact member inventory, source bytes, license, entry points, project metadata,
Python compatibility and pure-wheel tags are checked. Wheel RECORD must account
for every member with its actual SHA-256 digest and size.

The wheel must also match a native canonical ZIP reconstruction, without extra
member metadata, archive comments, prefixes or trailing data. TAR headers must
be contiguous, with exactly one 512-byte header before each member's data.
File padding must be zero. A bounded native byte reader requires the complete
1,024-byte prefix of two zero termination blocks before checking the remaining
zero padding.
Data that native archive readers would otherwise ignore cannot
hide outside the checked file inventory. This profile targets the declared
Hatch build output; changing archive producers requires a reviewed policy update.

Each wheel is installed offline without dependencies in a new virtual environment
outside the checkout. A child interpreter exercises the public import; the
registered console script must produce exact stdout, stderr and exit statuses for
valid input, malformed JSON and out-of-bounds endpoints. Strict mypy checks an
external consumer using `assert_type`, so missing typing metadata or an `Any`
return cannot satisfy the declared public type. Import-path overrides are removed,
user-site imports are disabled and warnings fail consumer processes. Consumer
behavior receives an allowlisted platform environment with home and temporary
paths bound to its owned directory, so caller credentials do not reach installed
code. A temporary `sitecustomize.py` denies Python sockets, child processes and
writes outside that directory. Native probes attempt network, subprocess and
outside-write operations and require the denial. The owned environment and guard
are removed on every outcome.

The source archive is rebuilt using the same hash constraints. Its wheel must
match the original wheel byte for byte and pass a second isolated installation.
The gate saves fresh artifacts in `.quality-results/dist` only after every check
passes. Each subprocess has a 120-second deadline; tool errors and timeouts fail.
Archive reads are independently capped at 65,537 compressed bytes and 524,289
expanded TAR bytes: one byte beyond each acceptance budget detects overflow
without an unbounded read. Boundary tests use fixed policy values and known
digest receipts, independently of the helper being tested.

When replacing the example, update the protected public source inventory and
consumer behavior together. Adding a module or package data cannot silently drop
it from distribution checks. Installed behavior runs on Linux, macOS and Windows
for every declared Python version in the hosted matrix.
