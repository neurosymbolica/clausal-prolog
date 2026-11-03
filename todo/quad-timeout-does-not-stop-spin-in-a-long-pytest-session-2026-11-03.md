# A quad's timeout does not stop a spinning query in a long pytest session

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
