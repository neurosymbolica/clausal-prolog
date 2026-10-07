# Closing a query part-way leaves setup_call_cleanup's cleanup to the garbage collector

Found 2026-10-06 while fixing the asyncio review (PR on branch
`claude/sweet-lamport-p1cfxe-async`). Pre-existing; not async-specific.

## What / Repro

```python
import gc; gc.disable()
# cl.seam:  g(R) <- setup_call_cleanup(true, member(R, [1, 2]), assertz(cleaned))
s = solve(("g", r), M); next(s)
s.close()                       # cleaned/0 still false
gc.collect()                    # now true
```

`solve`'s `close()` closes the root `StepGenerator`'s generator. It does not
close the frames below it: the query body and the `_tramp_call` loop that
runs the cleanup. Those sit in reference cycles and are finalised only by
the cyclic garbage collector. So the cleanup runs at an arbitrary later
moment. The same goes for an `await_each/2` iterator, which is closed in
its generator's `finally`.

## Why it matters more under asyncio

When the cleanup finally runs, it is outside the query that owned it. Under
`clausal.aio.asolve`, a cleanup that waits (`sleep/1`, an async adapter) then
cannot wait. With a loop running it raises
`permission_error(await, synchronous_query, _)`, printed as "Exception
ignored"; with none, it blocks on the private loop. Cancelling the query
that owns the cleanup is fine: the exception unwinds through the frames, so
cleanups run in place (pinned by
`tests/test_aio.py::test_cancelling_unwinds_the_query_and_runs_cleanup`).

A stray cleanup that the cyclic GC runs inside ANOTHER async query's
greenlet used to suspend that query on the cleanup's behalf; a cancellation
or timeout aimed at it was then delivered into the cleanup and lost (ninth
review, 2026-10-07: a 0.05 s timeout ignored, the query ran 1.59 s).
`clausal.aio` now refuses a wait while the GC is collecting
(`permission_error(await, finalisation, _)`), so the stray cleanup aborts
instead. Pinned by
`tests/test_aio.py::test_a_gc_run_cleanup_cannot_wait_inside_another_query`.

A query parked at a wait when its event loop closes is never freed at all:
suspended greenlets are not collectable, so its task, trail and table
entries stay for the thread's life. It no longer holds its tables (a query
whose loop is closed is not live), but nothing reclaims the memory.

## Options

- Close the generator chain eagerly on `close()`: the drive core keeps the
  frames it has parked and closes them innermost-first. This needs C and
  Python parity in the trampoline.
- Break the cycles so reference counting frees, and so closes, the frames
  at once.
