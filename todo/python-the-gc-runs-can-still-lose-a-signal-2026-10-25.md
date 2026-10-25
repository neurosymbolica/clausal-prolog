# Python code the garbage collector runs can still lose a signal

A signal handler runs at the next bytecode boundary, and whatever it raises
inside a callback CPython reports as "unraisable" (printed, then dropped) is
lost. Until 1.2.0 the main case was `clausal.aio`'s `gc.callbacks` entry, a
Python function that ran on every collection: under an allocating search a
single SIGINT or SIGALRM was often lost and the search ran on until memory ran
out. 1.2.0 made that callback C (`clausal.logic.variables.gc_phase_note`,
pinned by `tests/test_async_exception_propagation.py`, which also refuses any
clausal Python function in `gc.callbacks`).

## What remains

Other Python the collector runs can lose a signal the same way, more rarely:

- `__del__` finalisers of engine objects;
- weakref callbacks;
- generator `close()` run by the collector, e.g. the cleanup of an abandoned
  `setup_call_cleanup/3` query.

Found while diagnosing the 2026-10-24 lost-alarm report (a quad runner's
timeout and the `?-` top-level's Ctrl-C).

## Repro (to write)

An allocating search (`spin(N) :- N1 is N+1, spin(N1).`) that also creates and
abandons objects whose finaliser or weakref callback is Python, under a single
0.5 s SIGALRM whose handler raises; count the trials whose alarm is lost, under
both trampolines.

## Options

1. Audit the engine's `__del__`, weakref callbacks and collector-run generator
   closes, and move the hot ones to C or make them bytecode-free.
2. Accept the residue and document that a timeout should repeat
   (`setitimer(ITIMER_REAL, t, interval)`), as the quad runner does.

Recommendation: measure with the repro first; do (1) for any path that loses
signals at a measurable rate, and (2) in the docs either way.
