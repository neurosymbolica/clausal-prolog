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
