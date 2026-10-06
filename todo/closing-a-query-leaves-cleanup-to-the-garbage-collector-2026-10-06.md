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
ignored"; with none, it blocks on the private loop. Cancellation is fine:
the exception unwinds through the frames, so cleanups run in place (pinned
by `tests/test_aio.py::test_cancelling_unwinds_the_query_and_runs_cleanup`).

## Options

- Close the generator chain eagerly on `close()`: the drive core keeps the
  frames it has parked and closes them innermost-first. This needs C and
  Python parity in the trampoline.
- Break the cycles so reference counting frees, and so closes, the frames
  at once.
