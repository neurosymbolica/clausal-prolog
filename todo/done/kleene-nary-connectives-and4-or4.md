# `and4/or4` and higher — n-ary strong-Kleene connectives in the kleene stdlib

**Part of:** [kleene-unknown-builtin-and-stdlib.md](kleene-unknown-builtin-and-stdlib.md) · **Order:** 2
**Assignee:** Opus. Self-contained; decisions below are settled — implement, don't relitigate.

## STATUS: DONE 2026-07-17 — implemented + tested
Built `clausal/stdlib/kleene.clausal`: 9-row disjoint `and3/or3` tables + 3-row `not3`, fixed
arities `and4..and9`/`or4..or9` (each one left-fold chaining clause through fresh intermediates),
and `and3_list`/`or3_list` folds with unit `True`/`False`. `unknown` is a module-scoped exported
bare atom (the `Unknown` builtin has NOT landed; parent todo owns migration). NOTE: predicates
are exported in the `pred(A,B,R)` Call form, not bare names — a bare name in `-module` mints a
zero-arity atom that collides with the multi-arg clauses (`arg_0` TypeError). Tests in
`tests/test_kleene_stdlib.py` (19 passing): ground forward, 19-solution backward enumeration for
`and4(A,B,C,False)`/`or4(...,True)`, 1 for all-True, list folds + mid-chain solve, ground-query
determinism across every arity. Full `tests/` suite: 9337 passed, 2 skipped, 44 xfailed, 0 new
failures (9318 without this file + 19 = 9337).

## Goal
Fixed-arity strong-Kleene conjunction/disjunction over 3-8 operands, plus list folds for
arbitrary chains, in `clausal/stdlib/kleene.clausal` (create the file if the parent todo's
module doesn't exist yet). Pure `.clausal` — **no Python builtins, no compiler changes**.

Naming convention (SETTLED): the numeral is the TOTAL ARITY, result last.
`and4(A, B, C, R)` means R = A ∧ B ∧ C in strong-Kleene; `and3(A, B, R)` is the binary
connective. (This matches how the corpus already uses `and3/3`. It is NOT Belnap four-valued
logic — the truth values stay `True`/`False`/`unknown`; only the operand count grows.)

## What to build
1. **Binary ground truth** — the 9-row `and3/3` and `or3/3` fact tables plus `not3/2`
   (3 rows), copied from a downstream rulebase corpus's own three-valued-logic vocabulary module.
   Keep them full 9-row, pairwise-disjoint, first-argument-indexed. Do NOT add wildcard
   short-circuit rows like `and3(False, _, False)` — overlapping clauses break disjointness
   and make ground queries nondeterministic.
2. **Fixed arities 4-9** — `and4/4 ... and9/9`, `or4/4 ... or9/9`, each ONE chaining clause
   folding the binary table left-to-right through fresh intermediates (Kleene ∧/∨ are
   associative, so this is semantically exact):
   ```
   and4(A, B, C, R) <- (
       and3(A, B, AB),
       and3(AB, C, R)
   )
   ```
   8 operands (`and9`) covers the widest current corpus limb; going higher is what the
   list folds are for.
3. **List folds** — `and3_list(LIST, R)` and `or3_list(LIST, R)`:
   ```
   and3_list([], True),
   and3_list([X, *XS], R) <- (
       and3_list(XS, R1),
       and3(X, R1, R)
   )
   ```
   (list-pattern syntax precedent: `clausal/stdlib/reif.clausal` `LMemberdT([_e, *_es], ...)`).
   Empty chain = the unit: `True` for and, `False` for or.
4. **Third truth value**: check whether the `Unknown` builtin from the parent todo has landed
   (look for `predicate_builtins["Unknown"]` in `clausal/import_hook.py`). If yes, use it.
   If not, use a bare atom `unknown` EXPORTED from the module's `-module(...)` list so importers
   unify on the same object (module-scoped-atom rule); the parent todo owns the later migration.
5. **Exports**: `-module(kleene, [...])` listing every predicate above (and `unknown` if atom-based).

## Semantics notes (document these in the module header)
- Fully relational: any argument may be unbound. Backward queries enumerate, e.g.
  `and4(A, B, C, False)` yields exactly **19** assignments (27 total - 1 all-True - 7
  no-False-with-some-unknown); `or4(A, B, C, True)` dually yields 19.
- Partially-bound absorption does NOT short-circuit: `and4(False, B, C, R)` gives `R = False`
  in every solution but still enumerates B/C bindings (9 solutions), because the tables are
  disjoint. A non-binding short-circuit variant is a parked design question in the parent todo —
  do not build it here.

## Where
- Module: `/workspace/clausal-bug-fix/clausal/stdlib/kleene.clausal` (sibling of `reif.clausal`).
- Tests: new `tests/test_kleene_stdlib.py`, modeled on `tests/test_reif_builtins.py:373-440`
  (`TestMemberdT._load_stdlib_reif` shows how to load a stdlib `.clausal` by path and run goals
  built from `Call`/`LoadName` nodes).

## Running tests (this clone's venv quirk)
The shared `/workspace/clausal/venv` lacks pytest and its editable install can shadow the clone.
Always use pyenv 3.13.3 with PYTHONPATH:
```
cd /workspace/clausal-bug-fix && PYTHONPATH=/workspace/clausal-bug-fix \
  /home/node/.pyenv/versions/3.13.3/bin/python -m pytest tests/test_kleene_stdlib.py -q -p no:cacheprovider
```
Run the full suite once at the end the same way; it must stay at baseline (no new failures).

## Acceptance
- Ground forward: `and4(True, True, False, R)` → one solution, `R = False`;
  `and4(True, unknown, True, R)` → `R = unknown`; `or5(False, False, unknown, False, R)` → `R = unknown`.
- Backward enumeration: `and4(A, B, C, False)` → exactly 19 solutions, no duplicates;
  `and4(A, B, C, True)` → exactly 1 (all True).
- List folds: `and3_list([], R)` → `R = True`; `and3_list([True, unknown, X], False)` → `X = False`
  as one of the solutions; `or3_list([], R)` → `R = False`.
- Determinism: all-ground queries of every arity leave no choicepoints (one solution).
- Full pytest suite passes at baseline.
