# The TRO determinism table is a hand-written list (A03 audit note)

**Status: open, low priority.** One of the A03 "worth a look" notes of the
2026-07-05 audit, split out of
todo/done/investigate-A03-parked-design-decisions.md on 2026-10-20.

## What

`_DETERMINISTIC_BUILTINS` (`clausal/logic/compiler/tro.py:380`) serves both
tail-recursion optimisation and the shared determinism classifier. An
entry is safe only if the builtin is semidet in EVERY mode; A03-F001/F002
were entries that were not (`member`-like goals, `length/2` with an open
list; fixed 2026-07-07, todo/done/fix-A03-tro-nondet-prefix.md). The list
is still kept by hand, so a builtin that gains a nondeterministic mode
silently breaks TRO again. Option: derive the table from per-builtin mode
declarations.

## Also noted (unconfirmed)

The signal-mode TRO state `_tro_state` is one list per compiled function
(clausal/logic/compiler/README.md, the `_tro_state` row), written and read
around each re-dispatch. Under free-threaded CPython two threads running
the same predicate would share it. Not probed (needs a 3.13t/3.14t build);
see also todo/cross_cutting_issues.md §4.
