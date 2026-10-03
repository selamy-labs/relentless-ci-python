# Exception handling gate

The registered Ruff command rejects `return` inside `finally` (`B012`) because
it can silence an active exception. It also rejects a `try`/`except` body that
only passes (`S110`). Both rules cover authored `src`, `tests` and `quality`
Python. The pinned Ruff configuration is protected by repository ownership;
no inline suppression is currently approved.

The sample JSON CLI turns invalid input into a documented stderr message and
nonzero status. Its native CLI tests cover those paths. These static rules and
tests do not prove that every resource will close or that every exception is
handled well. Replacing the sample requires fresh behavior tests and a review
of any proposed policy exception.
