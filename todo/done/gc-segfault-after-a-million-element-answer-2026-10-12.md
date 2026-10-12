# Segfault during garbage collection after a very long answer (2026-10-12)

Reproduces on main a3fbb271 and later. It predates the inline-drain and rope work.

```prolog
recl(0, []).
recl(N, [f(N)|T]) :- N > 0, M is N - 1, recl(M, T).
```

1. One process runs `solve(recl(1000000, V))` and then builds text: `recs(16000)`, `recs(64000)`, ...
   It exits 139. faulthandler prints `Fatal Python error: Segmentation fault / Garbage-collecting /
   <no Python frame>`.
2. A single `solve(recl(1000000, V))` alone segfaults the same way at exit.

Suspect: a C type whose dealloc or tp_clear recurses down a 1M-long chain without CPython's trashcan
(`Py_TRASHCAN_BEGIN`/`END`), triggered from the cycle collector. The chain could be Vars, trail
entries, list cells or suspended frames.

A 250k-node rope chain inside a reference cycle is freed by `gc.collect()` without trouble, so the
rope type is not the cause.

Next: get a C backtrace (gdb or `-X faulthandler` plus a debug build), find the type, then add a
trashcan or iterative clear. Add a subprocess regression test at 1M.

**Update (after the rope, 9ecfb760):** text builders now reach this too. `rec(N, [a|T])` at 300k
chars or more used to run out of memory; it now builds, then segfaults while garbage-collecting. A
rope of depth 1M frees cleanly, so the rope is not the cause. `recl` (no text) crashes between 200k
and 300k on both trees.

**Observed before the fix (parity harness, slice 8.1, on a tree without the trashcan fix):** `tests/iso_diff/prelude.pl` under the native front end reaches
it too. Calling `nvt/3` (or `nv_/3`) with fresh variables runs away. When a SIGALRM-raised exception
ended that call after about 30 s, the process segfaulted in the garbage collector during a LATER call
(faulthandler: `Garbage-collecting`, inside `vix__4`). It left a 2.4 GB core. The same call left to
run for 100 s without the alarm did not crash. `clausal/tools/pl_parity.py` now runs each test and
call in a forked child that is killed on timeout, so the harness no longer reaches this. The engine
still does.

## Resolution (2026-10-13)

Fixed by "fix(runtime): free long StepGenerator and Var chains through the trashcan".

Root cause: `StepGen_dealloc` (clausal/logic/runtime/_trampoline.c) released `catcher`, the
parent link, with a plain `Py_XDECREF` and no trashcan. A suspended 1M-deep answer keeps one
StepGenerator per level, so freeing it recursed once per link and overflowed the C stack. A
SIGSEGV-handler backtrace showed every captured frame at `StepGen_dealloc`
`Py_XDECREF(self->catcher)`. The threshold scales with `ulimit -s` (2 MiB: <100k; 4 MiB: 100k-200k;
8 MiB: 200k-300k; 64 MiB and up: 1M clean). An acyclic chain crashes on a plain `del` with gc
disabled. The collector only provides the trigger: its `tp_clear` on the leaf starts the cascade.

`Var_dealloc`/`AttVar_dealloc` had the same flaw for binding chains (a 999,999-link chain
segfaulted on `del`). All three now use `Py_TRASHCAN_BEGIN/END`.

Regression: tests/test_dealloc_long_chains.py (5 fast subprocess cases under a 2 MiB stack cap,
plus recl 1M and rec 500k behind CLAUSAL_SLOW_TESTS=1). The rope was never involved.
