# A quad's timeout does not stop a spinning query in a long pytest session

**Status: FIXED 2026-11-04 (commit COMMIT).** Two causes, both fixed.
Pinned by `tests/test_quads.py::test_a_lost_alarm_does_not_leave_the_query_unbounded`
(both ways of losing an alarm, deterministically, in a child process),
`tests/test_quads.py::test_a_timed_out_quad_leaves_no_alarm_behind` and
`tests/test_iso_tail_recursion.py`.

1. Why memory grew: no tail-recursion rewrite. The ISO front ends call
   `is/2` (and `=/2`, the comparisons) as built-in predicates, and
   `compiler/tro.py` did not count them as deterministic, so each `spin/1`
   step kept its generator frame, waiting on the next (about 140 MB/s).
   Nothing leaked: the frames were live. Now they count, and `spin/1` runs
   in constant memory (47 MB after 5 s, was 714 MB).
2. Why the alarm was lost: no earlier test left signal state behind. The
   instrumented runs (two of four quarters of the files before
   `test_quads.py`, run under a faulthandler watchdog) showed SIG_DFL as
   the previous handler, an empty signal mask, one thread, only the C
   `gc_phase_note` in `gc.callbacks`, and the alarm DID fire: its handler
   ran inside a weakref callback that the collector ran, once
   `cells.register_compiled_constants.<locals>._drop` (the code object of a
   clause compiled by an earlier test dying), once `WeakKeyDictionary`'s
   `remove` (an earlier test's module dying). CPython reports an exception
   raised there as unraisable and drops it. The growing heap of (1) made
   full collections long and frequent, and a long session leaves many dead
   modules and code objects for them to free, so the alarm, arriving during
   a collection, was handled in the first Python code after it: the
   callback. The quad runner armed ONE alarm and cancelled the timer in its
   handler, so nothing fired again. It now repeats every 0.1 s after the
   limit until the quad's code has seen it (`quad_runner._Alarm`), and
   restores the timer and handler even when an alarm strikes during the
   disarm. The callbacks themselves are left as they are:
   `todo/python-the-gc-runs-can-still-lose-a-signal-2026-10-25.md`.

Found 2026-11-03 while running a set of test files in one pytest process
(tests/test_meta_goal_tables_agree.py ... tests/iso_l3, tests/test_pycache.py,
tests/test_quads.py, ... tests/test_database.py: about 2770 tests). The same
on main 4e352fe4 and on a branch of it, so no recent change caused it.

`tests/test_quads.py::test_a_query_that_never_answers_times_out` runs
`?- spin(0).` (`spin(N) :- N1 is N + 1, spin(N1).`) with
`run_quads(..., timeout=0.5)`, which bounds it with SIGALRM
(`clausal/quad_runner._run_quad`). Run alone it passes in 1.5 s at about
150 MB RSS, on both trees. Late in the long session the alarm does not end
the query: it keeps running and memory grows without bound.

Measured per test (RSS after each test; a watchdog stopped the run at
12 GB):

| tree | RSS before the test | in the test |
|---|---|---|
| branch of 4e352fe4 | 579 MB (flat from about 400 MB through tests/iso_l3) | over 12 GB, stopped by the watchdog |
| main 4e352fe4, under `ulimit -v 16000000` | | segmentation fault; the faulting thread is in `spin__1` <- `solve._drive_trampoline` <- `quad_runner._run_alternative` <- this test |
| main 4e352fe4, second run | 559 MB | 589 MB: it passed |

So it is intermittent. Without a limit, the kernel kills the whole pytest
process (exit 137) at about 91% of the run. Why the alarm does not stop
the query was not investigated (the faulting frame is the compiled Python
`spin__1`, so the handler should get a chance to run).
