# Bounded CLI fuzzing

`tests/test_fuzz_cli.py` generates malformed JSON and invalid typed interval
endpoints with a fixed Hypothesis seed. The public parser receives 200 generated
examples per family; the installed `interval-normalizer-generated-py` command receives 32
generated examples per family. Explicit boundary examples run in addition.
Each input is at most 512 UTF-8 bytes. Both boundaries must exit or return 2,
leave stdout empty and emit the precise diagnostic on stderr. The process test
has a ten-second deadline for each input. Those explicit examples ensure all four
malformed JSON shapes and each invalid endpoint class are exercised even if
the generated distribution changes.

This local candidate still needs full mutation and hosted runtime
qualification. The separate package gate verifies archives and isolated wheel
consumers; this fuzz test targets the locked development environment's command.
