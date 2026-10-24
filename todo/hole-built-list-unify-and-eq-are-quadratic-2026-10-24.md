# `=`/2 and `==`/2 on two hole-built lists are quadratic in their length

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

`solve(("p", DEEP), m)` from Python with a 100k-nested GROUND argument still
raises a raw `RecursionError` to the Python caller: the query compiler's
`_collect_vars(goal, include_bound=True)` recurses before the clause
rewrite (`compiler/deep_literals.py`) can see the goal.  A program's own
`call/1` lifts such an argument as a parameter and is fine; this is the
Python entry only.

The same holds for a CYCLIC term at the Python entry, and for the two
converters (checked 2026-10-24): with `X` bound by `cyc(X) :- X = f(X)`,
`solve(("acyclic_term", X), m)`, `solve(("=", X, X), m)`,
`to_python(X.value)` and `term_key(X.value)` each raise a raw
`RecursionError` (as they did before the rational-tree work; it is loud,
not silent).  Reading the answer with `Var.value` / `deref`, one step at a
time, is fine.  Under ruling 2026-10-24 the entry should raise
`resource_error(finite_memory)` for a known cycle and
`resource_error(stack)` for depth, as the engine does inside a program.
