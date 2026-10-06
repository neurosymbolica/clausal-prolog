# Asyncio: tabled waits, concurrent subgoals, a native await step

Filed 2026-10-06 with the first `clausal.aio` (docs/asyncio.md). The shipped
driver runs `solve` in a greenlet; these are the parts it deliberately left
out.

## 1. Waiting inside tabled evaluation

Under `asolve`, `await_only` refuses while the query has a table under
evaluation (`permission_error(await, tabled_evaluation, _)`). Without that
guard, two concurrent queries calling the same tabled predicate whose body
waits give the second query **no solution** (measured: `['found', 'NO
SOLUTION']`). It finds the entry `evaluating`, treats itself as a consumer
of an SCC it does not lead, and suspends with no answers.

Options:
- **Per-table wait.** A query that meets a table another query is evaluating
  awaits that table's completion. Like XSB's shared completed tables, this
  needs deadlock handling when two queries' SCCs depend on each other.
- **Private tables per query** while one is under evaluation, merged on
  completion.
- Keep the refusal (current).

Pinned by `tests/test_aio.py::test_awaiting_inside_tabled_evaluation_is_refused`.

## 2. Concurrent independent subgoals

At the moment, concurrency comes only from Python (`asyncio.gather` of
`aonce` calls). A predicate such as `concurrent_all(Goals)` would run each
goal on a `copy_term` as its own task and unify the results back. It needs a
meta-call from an adapter that resolves goals in the calling module, as
`call/N` does through the builtin registry's `db`; py adapters have no such
context today.

## 3. A native await step (no greenlet)

Prototyped 2026-10-06 (not committed). A predicate yields `(None,
AwaitRequest(this_generator, awaitable))` to the root, and an async twin of
the drive core awaits and resumes that generator. This works where the root
driver sees the yield. It does not work under nested synchronous drivers
(`_tramp_call`, `_naf_has_solution`, the tabling spawns), in simple-mode
`for` loops (`findall`'s inner goal), or in the C trampoline. Those would
all have to forward the request. The payoff is no greenlet dependency and no
C-stack switching. Worth doing only if either becomes a problem.
