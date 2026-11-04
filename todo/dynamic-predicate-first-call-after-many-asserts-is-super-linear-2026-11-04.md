# The first call of a predicate with thousands of clauses is slow and super-linear in time and memory

Filed 2026-11-04, found while building rule assert (ISO 8.9, operator
ruling 2026-11-03). Pre-existing: measured the same on main e1b23bfb.
Severity: high for any program that builds a fact table at run time (or
loads one): 4.5 s at 2,000 asserted facts, and at 10,000 the process
reached 14 GB and was killed.

## What / Repro

```prolog
:- dynamic(f/2).
fill(N) :- between(1, N, I), assertz(f(I, I)), fail.
fill(_).
first(L) :- findall(X, f(X, _), L0), length(L0, L).
```

`fill(N)` is linear (about 0.05 ms per fact). The FIRST `first(L)` after it
runs the lazy recompile (`Database.get_dispatch` ->
`_recompile_trampoline`), and that is what costs:

| clauses | e1b23bfb facts | branch facts | branch rules (`f(I, Y) :- Y is I + 1`) |
|---|---|---|---|
| 500 | 1.87 s, 121 MB RSS | 1.91 s, 121 MB | 2.02 s, 104 MB |
| 1,000 | 4.03 s, 305 MB | 4.11 s, 305 MB | 3.93 s, 171 MB |
| 2,000 | 8.95 s, 647 MB | 8.65 s, 647 MB | 8.63 s, 475 MB |
| 4,000 | 19.57 s, 2,166 MB | 20.79 s, 2,166 MB | 19.90 s, 1,032 MB |

(first-call time; peak RSS of the process.  "branch" is t3-assert-rules
0c0dccb0.)  Scaling exponent 500 -> 4,000: time 1.13, RSS 1.39; memory
retained by the compile (tracemalloc) 62.5 MB at 500, 236.8 MB at 1,000,
557.2 MB at 2,000: exponent 1.58, heading for 2.

A STATIC predicate has the same problem at load: a `.pl` file of 1,000
facts `f(I, I).` loaded in 5.44 s (211 MB), 2,000 in 11.0 s (658 MB), on
e1b23bfb.

## Profile (1,000 facts, cProfile + tracemalloc)

* 2,004 calls of `_build_predicate_trampoline_funcdef`: the fallback (all
  1,000 clauses in one function) plus one function per first-argument
  bucket and one per second-argument bucket (each key is distinct), about
  1 ms each, plus `mark_final_yields`, `fix_missing_locations`, the
  invariant walks: linear, but ~3 ms per clause.
* tracemalloc's top allocation: `codegen.functiondef_to_function`'s
  `ns = dict(globals_)`, 207.7 MB in 4,000 blocks: every one of those
  functions got its own COPY of the compile's `base_globals` (~100 KB).
* and `base_globals` grew with the clause count:
  `predicate._later_clauses_excluded` (the FINAL pass's "no later clause
  can match" test) built, for EACH arm i, a frozenset of every later
  arm's first-argument key and stored it as a global `$final_keys_i`:
  O(n^2) keys (24.9 MB at 1,000) and n globals, copied into each of the
  2n functions -- the quadratic memory.
