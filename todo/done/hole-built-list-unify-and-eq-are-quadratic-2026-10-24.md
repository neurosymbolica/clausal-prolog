# `=`/2 and `==`/2 on two hole-built lists are quadratic in their length

**Status: RESOLVED 2026-11-03 (already linear at 4e352fe4; no fixing commit).** `=`/2 and `==`/2 on two
hole-built lists are linear, and were not the cost measured below: the
timings are those of BUILDING the lists with `mk/3`, whose head builds
`[N|T]` after its body and copies `T` at every level -- filed as
todo/a-list-a-clause-head-builds-after-its-body-copies-the-tail-quadratic-2026-11-03.md.
No code change.  Pinned in tests/test_hole_list_unify_scaling.py, which
counts the calls one `=` or `==` makes on two chains of 500 and of 2 000
links (the shape `X = [N|T]` builds, one `SegList` per element; tails `[]`,
`foo` and one shared unbound variable; equal, and differing only at the
last element): the count grows x4.0 for x4 the length (a deliberately
quadratic walk, tried and reverted, made it x15.7 and failed every row).

Measured 2026-11-03 (main 4e352fe4), `mk/3`'s repro with and without the
goal (`-g`, wall time including ~0.7 s start-up): `b(16000)` (build only)
7.3 s, `u(16000)` (`=`) 7.3 s, `t(16000)` (`==`) 6.8 s; cProfile puts `==`
at 0.04 s of it and `=` lower, and `_head_list_unify_output` at 2.4 s.
Chains built forward (`mkf(N, L, X) :- N > 0, X = [N|T], ...`), timed from
Python on the live chain:

| N | `=` (tail `[]`) | `==` (tail `[]`) | `=` (tail `foo`) | `==` (tail `foo`) |
|---|---|---|---|---|
| 1 000 | 0.001 s | 0.002 s | 0.002 s | 0.010 s |
| 10 000 | 0.015 s | 0.018 s | 0.020 s | 0.111 s |
| 100 000 | 0.28 s | 0.29 s | 0.34 s | 1.76 s |

The mechanism suspected under "Where to look" does not occur:
`SegList.__unify__` against a `SegList` walks each chain once
(`_walk_raw`, iterative) and unifies the two flat results, so the C unify
never meets an inner link; `_iso_identical` reads each chain once
(`_seg_list_parts`).  `==` on an improper (`foo`) tail walks each side a
few times over (`_seg_term`, `_rational_eq`): linear, about 5x the calls
of the proper case.

Filed 2026-10-24 while pinning the deep-term rows of
`tests/iso/test_cyclic_terms_scryer.py` (the cyclic/deep walkers work,
todo/done/deep-and-cyclic-terms-overflow-the-recursive-walkers-2026-10-22.md);
not a RecursionError, so left open there.

## Repro

```prolog
mk(0, L, L).
mk(N, L, [N|T]) :- N > 0, N1 is N-1, mk(N1, L, T).
t(N) :- mk(N, [], L), mk(N, [], L2), L == L2.
u(N) :- mk(N, [], L), mk(N, [], L2), L = L2.
```

Measured on the native front end (`-g "t(N)"`, `-g "u(N)"`), 2026-10-24:

| N | `=`/2 | `==`/2 |
|---|---|---|
| 8 000 | 1.3 s | 1.3 s |
| 16 000 | 4.8 s | 4.9 s |
| 32 000 | 23.5 s | 21.7 s |

Four times the time for twice the length: quadratic.  `numlist(1, 100000,
L)` builds one flat list and the same goals take milliseconds, so the cost
is in the SHAPE `mk/3` builds -- a chain of partial lists, one `SegList`
link per element (`[N|T]` with `T` the next link) -- not in the walkers.
Scryer answers both for N = 100 000 in well under a second.

## Where to look

`SegList.__unify__` / `_iso_identical` read a chain through `_walk_raw`
(iterative since the chain fix, one pass) -- but a pair of chains is read
again at every link the recursion reaches through the C unify's
`__unify__` hook (each link is a SegList whose hole is the next link), so
the whole remaining chain is re-walked per link.  A walk cached per
SegList for the duration of one unification (the pair memo
`_SEG_UNIFY_ACTIVE` already scopes one), or unifying two chains link by
link without walking past the current link, would make it linear.

## Related

**The Python-entry part is FIXED 2026-10-24** (pinned by
`tests/test_python_entry_cyclic_deep.py`): a cyclic or 100k-deep argument
handed to `solve`/`once`/`call`/`query` from Python is passed as a run-time
parameter when the query compiler's recursive walks overflow on it, as a
program's `call/1` passes it, so `solve(("acyclic_term", X), m)` fails,
`solve(("=", X, X), m)` and `solve(("=", DEEP, V), m)` succeed.  A goal that
is itself cyclic (`G = (G, true)`) or too deep to compile raises
`error(resource_error(stack), _)`.  `to_python` and `term_key` raise
`error(resource_error(finite_memory), _)` on a cycle and
`error(resource_error(stack), _)` on a term too deep to convert, as a
`LogicException` (ruling 2026-10-24).

Still open, outside this file's subject: a Python exception raised DURING a
search started from Python (not at the compile) still reaches the Python
caller raw -- `solve(("call", G), m)` with `G = (G, true)` raises
`RecursionError` out of the drive loop, where a program's `catch/3` sees
`resource_error(stack)`.  That is the general top-level policy for an
uncaught Python exception, not a cyclic-term walker.
