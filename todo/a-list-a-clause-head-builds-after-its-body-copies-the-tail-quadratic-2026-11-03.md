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

## Benchmark: benchmarks/bench_head_list_build.py

Builds with `mk/3` (tails `[]`, unbound, `foo`) and `inc/2` (the
map `inc([H|T], [H1|T1]) :- H1 is H+1, inc(T, T1).` over the `[]` list),
then times every reader on the built lists, each inline in the clause body
with `statistics(cpu_time, _)`.  One process per row, capped at 8 GB of
address space and 300 s.  CPU seconds; one run each, on a shared 32-core
box at load ~20, so a reader under ~0.01 s is noise.

### Baseline, 2026-11-03 (main 4e352fe4)

`python benchmarks/bench_head_list_build.py 1000 4000 16000 64000 --mem 8 --budget 300`

| row | N=1k | 4k | 16k | 64k |
|---|---|---|---|---|
| nil: build | 0.016 | 0.145 | 1.93 | over 8 GB |
| nil: build_inc | 0.019 | 0.263 | 2.56 | -- |
| nil: peak RSS (MB) | 66 | 271 | 3 220 | -- |
| open: build | 0.229 | 3.24 | 54.5 | over 300 s |
| open: recurse (`walk([_|T])`) | 0.334 | 4.85 | 90.9 | -- |
| open: peak RSS (MB) | 64 | 267 | 3 202 | -- |
| improper: build | 0.013 | 0.051 | 0.254 | 1.19 |
| improper: peak RSS (MB) | 52 | 69 | 138 | 416 |

Memory is quadratic as well as time: every level keeps its own copy of the
rest, and all of them stay bound, so `mk(64000, [], L)` with its twin
passed 8 GB (an uncapped run reached 31 GB before it was stopped).  Every
other nil reader (length, nth1, member, append, msort, sum_list, findall,
`==`, `=`, compare, copy_term, term_to_atom, write_to_string, recursion)
took under 0.07 s at 16k, except one `compare/3` at 2.2 s (a garbage
collection over the 3 GB heap; it was 0.004 s at 4k).  The open list's
`walk([_|T])` recursion is quadratic on its own: each step takes the rest
of the one flat `SegList` the build made.

Profiles of the builds alone (`--profile TAIL N`), tottime:

* nil, 16k (2.6 s): `_head_list_unify_output` 1.30 s over 16 000 calls,
  `mk__3` 0.65 s (freeing and trailing the copies); nothing else over 0.11 s.
* open, 4k (6.4 s): `walk` 4.13 s over 8 001 999 calls, the generator in
  `SegList._walk_raw` feeding it 1.21 s, `list.extend` 0.74 s -- all under
  `_head_list_unify_output` (5.8 s cumulative).
* inc over nil, 16k (7.5 s): `_head_list_unify_output` 2.79 s over 32 000
  calls, `inc__2` 2.48 s.
* improper, 16k (0.87 s): nothing over 0.15 s; linear.

### Option 2, landed 2026-11-03

Operator ruling, 2026-11-03: "yeah 2 first, 1 after benchmarks. but use a
benchmark that actually hits it".

For a `SegList` star, `_head_list_unify_output` (C) and its Python twin read
the rest with `_walk_raw(False)` instead of `__walk__`: the elements are
spliced as they are, as a list star's always were, and whoever reads the
list reads them through their bindings (a `findall/3` copy walks them then,
so commit f60e3211's fix holds: tests/test_findall_partial_list_snapshot.py
and tests/iso/test_findall_partial_list_scryer.py pass).  A ground result is
still promoted to text by `maybe_promote_to_str`, as after the walk.
Pinned in tests/test_head_list_build_scaling.py (the calls a whole build
makes grow x4 for x4 the length on every tail; the open tail was x13 before;
answers, findall snapshots, chars, and the C and Python outputs agreeing on
every star shape).

Same command, after:

| row | N=1k | 4k | 16k | 64k |
|---|---|---|---|---|
| nil: build | 0.014 | 0.147 | 1.93 | over 8 GB |
| open: build | **0.020** | **0.139** | **2.02** | over 8 GB |
| open: recurse | 0.327 | 5.06 | 86.6 | -- |
| open: peak RSS (MB) | 64 | 260 | 3 124 | -- |
| improper: build | 0.011 | 0.047 | 0.260 | 1.20 |

The open build drops from 54.5 s to 2.0 s at 16k and now matches the `[]`
build: still quadratic, in C list copies and in memory (it now stops at the
8 GB cap at 64k instead of the 300 s one).  Every reader is within noise of
the baseline (the largest moves: open `==` at 16k 0.024 -> 0.003 s, nil
`compare` at 16k 2.2 -> 2.6 s, both a collection over the 3 GB heap; open
`=` at 16k is 1.35 s in both runs, also a collection).  The open list's
`walk([_|T])` recursion is still quadratic; that is a reader, untouched here.

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
