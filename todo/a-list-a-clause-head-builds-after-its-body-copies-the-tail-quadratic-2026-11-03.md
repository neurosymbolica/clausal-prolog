# A list a clause head builds after its body copies the tail: quadratic

**Status: PARTLY FIXED 2026-11-03 (commit f4248cbb).** Option 2 landed: the
unbound-tail build no longer walks every element at every level (54.5 s to
2.0 s at 16k; pinned in tests/test_head_list_build_scaling.py).  Option 1
was prototyped, measured and left out (below): it makes the build linear
but makes every read of the list pay a walk of the chain.  Still open: the
`[]`- and unbound-tailed builds copy the rest at every level, quadratic in
time and memory (over 8 GB at 64k); and, separately, recursing down an
open-tailed list with `[_|T]` is quadratic whichever way it was built.

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
still promoted to text, as after the walk -- through one dereference of
each element (`maybe_promote_to_str_deref` in C, `_promote_through_deref`
in Python), since the shallow read leaves a variable bound to a char in
place.  Without that (f4248cbb as first committed, found by review),
`mk2([X|R], X, R). mk(T, [a|T]). p(L) :- mk2(T, X, R), X = b, R = [],
mk(T, L).` gave `L` as the list `[a, X]` where it had been the text
`"ab"`: Prolog's `==`, `=` and `atom_chars/2` agreed, but `copy_term/2`,
`findall/3` and `L = [_|T]` handed back `[a,b]` and `[b]` where they had
handed back `"ab"` and `"b"`; fixed in the commit after it.  One shape
difference remains, below the top level: an element `f(Y)` whose `Y` was
bound after the build keeps `Y` as the bound variable inside `f/1`, where
the walk made `f(1)` -- as a list star (`T = [f(Y)]`) always has.
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

### Option 1, prototyped 2026-11-03 and left out

The prototype (C only, behind an environment switch, not committed): when
the star is a list of at least `LIST_VIEW_MIN` (64) elements or a
`SegList`, and nothing follows it, the output is the link
`SegList([ConcreteSeg(before), VarSeg(star)])` sharing the star's variable
instead of a copy -- so `mk/3` builds a chain of links, as `X = [N|T]` in a
body does.  Same benchmark, `--repeat 3` (minimum of three runs), the
prototype against option 2 alone, nil tail:

| row | 1k off | 1k on | 4k off | 4k on | 16k off | 16k on | 64k on |
|---|---|---|---|---|---|---|---|
| build | 0.0158 | 0.0109 | 0.141 | 0.0459 | 1.875 | **0.218** | 1.111 |
| build_inc | 0.0179 | 0.0134 | 0.247 | 0.0545 | 2.308 | 0.305 | 1.600 |
| peak RSS (MB) | 65 | 54 | 271 | 81 | 3 218 | 185 | 606 |
| length | 0.0000 | 0.0016 | 0.0000 | 0.0069 | 0.0000 | **0.1538** | 0.602 |
| nth1 | 0.0000 | 0.0016 | 0.0000 | 0.0065 | 0.0000 | **0.0315** | 0.132 |
| member | 0.0001 | 0.0017 | 0.0004 | 0.0073 | 0.0014 | 0.0294 | 0.143 |
| append | 0.0000 | 0.0015 | 0.0000 | 0.0066 | 0.0002 | 0.0273 | 0.132 |
| msort | 0.0001 | 0.0016 | 0.0002 | 0.0067 | 0.0008 | 0.0280 | 0.135 |
| sum_list | 0.0003 | 0.0018 | 0.0012 | 0.0077 | 0.0045 | 0.0320 | 0.150 |
| findall_member | 0.0008 | 0.0024 | 0.0032 | 0.0099 | 0.0132 | 0.0408 | 0.185 |
| findall_copy | 0.0000 | 0.0014 | 0.0001 | 0.0059 | 0.0004 | 0.0246 | 0.589 |
| `==` | 0.0004 | 0.0016 | 0.0038 | 0.0070 | 0.0073 | 0.0301 | 0.135 |
| `=` | 0.0001 | 0.0014 | 0.0002 | 0.0061 | 0.0009 | 0.0282 | 0.129 |
| compare | 0.0025 | 0.0038 | 0.0040 | 0.0156 | 2.289 | 0.192 | 0.298 |
| copy_term | 0.0000 | 0.0014 | 0.0000 | 0.0059 | 0.0002 | 0.0289 | 0.591 |
| term_to_atom | 0.0008 | 0.0021 | 0.0024 | 0.0084 | 0.0091 | 0.0363 | 0.153 |
| write_to_string | 0.0006 | 0.0020 | 0.0022 | 0.0083 | 0.0089 | 0.0338 | 0.154 |
| recurse | 0.0042 | 0.0069 | 0.0425 | 0.0261 | 0.0671 | 0.1031 | 0.451 |

Open tail, prototype on (one run): build 0.011 / 0.046 / 0.227 s at
1k / 4k / 16k (2.0 s with option 2 alone), peak 1 166 MB at 16k; the
readers 2-10 times slower as above (`=` 0.12 s, `write_to_string` 0.13 s
at 16k); `walk([_|T])` 87.5 s at 16k, quadratic as before.  The improper
tail is unchanged (its build already shares the tail as cons cells).

The build is linear (x5 per x4 of N, against x13) and its memory with it.
But the ruling's second condition fails: every reader regresses well past
noise, because every read of a chain walks all of it in Python
(`SegList._walk_raw`, about 2 microseconds a link) where a flat list was
read in C or not at all -- `length/2` and `nth1/3` go from O(1) to O(N)
per call, so a program that reads the list once per element (an `nth1/3`
loop) turns quadratic instead of its build.  Left out.  Making it pay
would need the readers to read a chain without flattening it (or to
flatten it once, in place, on first read); that is a change to every list
reader, not to this output.

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
evidence.  Ruled 2026-11-03 as recommended; 2 landed, 1 measured and left
out (above).
