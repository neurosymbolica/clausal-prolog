# A list a clause head builds after its body copies the tail: quadratic

Found 2026-11-03 while measuring
todo/done/hole-built-list-unify-and-eq-are-quadratic-2026-10-24.md, whose
timings were this cost, not `=`/2 or `==`/2.

## Repro

```prolog
mk(0, L, L).
mk(N, L, [N|T]) :- N > 0, N1 is N-1, mk(N1, L, T).
b(N, Z) :- mk(N, Z, L), mk(N, Z, L2).
```

`clausal rep.clausal -g "b(N, Z)"`, wall time including about 0.7 s of
start-up, 2026-11-03 (main 4e352fe4):

| N | `Z = []` | `Z = foo` | `Z` unbound |
|---|---|---|---|
| 1 000 | 0.8 s | 0.8 s | |
| 2 000 | | | 2.8 s |
| 4 000 | 1.1 s | | 8.3 s |
| 8 000 | 2.2 s | 1.2 s | |
| 16 000 | 7.3 s | 1.5 s | |
| 100 000 | | 6.0 s | |

Adding `L = L2` or `L == L2` (or `compare/3`) to `b/2` changes none of
these by more than noise.

## Cause

`[N|T]` in the head of `mk/3` meets an unbound third argument, so the head
match defers it (`_head_list_unify_input` returns None) and builds the list
at the solution, after the body has bound `T`
(`_head_list_unify_output`, clausal/logic/runtime/_list_unify.c, Python
twin in clausal/logic/runtime/list_unify.py).  It builds a NEW flat list
`[N, *T]`:

* `T` a list (`Z = []`): the C code appends every element of `T`, so level
  k copies N-k elements -- N^2/2 pointer copies in all (cProfile at
  N = 16 000: `_head_list_unify_output` 2.4 s over 32 000 calls), plus the
  trail undo and frees of the intermediate lists.
* `T` a partial list (`Z` unbound): the star is a `SegList`, read through
  `__walk__`, which walks (and `walk`s every element of) the whole rest at
  every level: 4 000 000 `walk` calls at N = 2 000.
* `T` an improper list (`Z = foo`): `_improper_star` builds cons cells, which
  share the tail; linear.

A list built forward in the body (`X = [N|T], ..., mk(N1, L, T)`) is a chain
of `SegList` links and builds in linear time; so do `=`/2 and `==`/2 on it
(tests/test_hole_list_unify_scaling.py).

## Options (need a ruling: they change the representation a head builds)

1. Build `SegList([ConcreteSeg(before), VarSeg(star)])` instead of copying
   when the star is long (as `list_rest`/`SegListView` do for the rest of a
   list past `LIST_VIEW_MIN`).  Linear to build, but every consumer then
   meets a chain where it met a flat list: a later head match `[H|T]` on it
   walks the chain to take one element, so a consumer of the list may turn
   quadratic instead.  Needs measuring on the list-heavy benchmarks.
2. For a `SegList` star only (the unbound-tail column, by far the worst):
   splice the walked segments shallowly (`_walk_raw(False)` once, no
   per-element `walk`) -- still a copy per level, so still quadratic, but in
   C-speed list copies as the `[]` column is, not Python `walk` calls.
   No representation change, but check it keeps what commit f60e3211 fixed
   (an element left unwalked held a bound variable that `findall/3`'s copy
   then kept live: `[[a,c(_),d]]`).
3. Leave it: Scryer and other WAM systems build `[N|T]` in the head as one
   cell sharing `T`; Python lists cannot share a tail, so some copy is
   inherent to the flat-list representation.

Recommendation: 2 first (no representation change), 1 only with benchmark
evidence.
