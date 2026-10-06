# Asyncio: tabled waits, concurrent subgoals, a native await step

Filed 2026-10-06 with the first `clausal.aio` (docs/asyncio.md). The shipped
driver runs `solve` in a greenlet; these are the parts it deliberately left
out.

## 1. Sharing a table that another query is still building

**Status: PARTLY RESOLVED 2026-10-06.** The first version refused any wait
inside tabled evaluation. The Fable review found that this was not enough:
a query streaming a tabled goal's answers is suspended between answers
with the table still `evaluating`, and another query then silently lost
answers. Table entries now carry their owning query
(`TableEntry.owner`, `tabling._foreign`). Waiting is allowed anywhere, and
a query that reaches another live query's unfinished table raises
`permission_error(access, tabled_evaluation, P/N)`. Pinned by
`tests/test_aio.py::test_a_table_another_query_is_building_is_refused_not_partial`
and `::test_a_table_still_streaming_answers_is_exclusive`.

What remains is to wait instead of refusing:
- **Per-table wait.** A query that meets a table another query is evaluating
  awaits that table's completion. Like XSB's shared completed tables, this
  needs deadlock handling when two queries' SCCs depend on each other, and
  a query cannot wait for a table it is itself streaming (the refusal stays
  for that case).
- **Private tables per query** while one is under evaluation, merged on
  completion.

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
