# The first call of a predicate with thousands of clauses is slow and super-linear in time and memory

**Status: FIXED 2026-11-04 (commit c6a9c830).** A predicate of 256+ clauses compiles to a clause table, an indexed compile's functions share their globals, and the FINAL exclusion test covers the last 64 arms only. Pinned in tests/test_clause_table.py::test_first_call_after_20000_asserted_facts, ::test_loading_10000_facts_compiles_no_fact and ::test_table_answers_as_the_compiled_predicate.

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

## Fix

Three changes; answers and their order are unchanged.

1. `_later_clauses_excluded` tests only a predicate's last 64 arms
   (`_FINAL_EXCLUSION_ARMS`); an earlier arm's answer just leaves its
   choice point open, as before the test existed.
2. The functions one indexed compile makes share its `base_globals`
   (`functiondef_to_function(..., share_globals=True)`, through
   `predicate._shared_fn`) instead of each copying it.  Checked over 26
   compiler/indexing/database test files with a plugin that snapshots the
   globals at each function's creation: no later rebinding of a key any
   function could read (only the compile-time counter `$final_keys_count`),
   no name collision.
3. From 256 clauses (`clause_table.CLAUSE_TABLE_THRESHOLD`) a predicate,
   static or dynamic, compiles to a clause TABLE
   (`clausal/logic/compiler/clause_table.py`): plain-data facts are kept
   as terms (what clause/2 reads) and unified with the call's arguments;
   every other clause is compiled as a one-clause function the driver
   delegates to; per-position dict indexes pick the candidates.

After (same machine): 1,000 facts 0.016 s, 4,000 0.058 s, 10,000 0.156 s,
20,000 0.318 s at 75 MB RSS; rules 1,000 1.30 s, 4,000 5.31 s at 59 MB
(each rule is still compiled once, ~1.3 ms); a 10,000-fact `.pl` file
loads in 3.35 s and 20,000 in 6.86 s (linear: the front end's reading and
lowering, ~0.33 ms per clause, not the compiler).

What differs from the one-function compile, where no answer shows it: one
fact's head binds the call's variables left to right (so goals those
bindings wake run in that order); a table predicate's rules get no
tail-recursion optimisation; and "this is the last answer" (the top
level's full stop) is detected per indexed argument, not per pair.

Steady state, a dynamic f/2 of 300 facts (scratch benchmark, min of runs):
an indexed call 2.52 -> 2.29 us per answer, a full scan 0.86 -> 0.49 us
per answer, a retract + assert + recompile 2,021 -> 3.1 ms.  Below the
threshold nothing moves (10 and 100 facts: first call 33.6 -> 33.6 ms and
356.7 -> 342.5 ms; indexed call 2.18 -> 2.14 and 1.99 -> 1.95 us; scan
0.62 -> 0.61 and 0.52 -> 0.50 us).  No workload in benchmarks/ asserts.

Forcing the table on every predicate of 2+ clauses (a scratch pytest
plugin) over 40 compiler/indexing/database/ISO test files: 2,734 pass;
the 26 failures all inspect generated code or index structures (codegen
golden text, `index_plans`, TRO activity, `$dispatch_at` in a dispatch's
globals), none an answer.

Pinned in tests/test_clause_table.py (scaling by compiler-call counts and
generous time bounds at 3,000-20,000 clauses; 26 goals answering the same
with the table and with the threshold out of reach -- indexing on either
argument, facts with variables, partial lists, strings, rules with cut and
errors, the logical update view through assertz/asserta/retract, clause/2,
once/1, freeze/2 -- and the known-last answers).
