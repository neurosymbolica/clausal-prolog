# Move dif/2 and constraint helpers to C

## Context

`clausal/logic/constraints.py` (244 lines) implements the core disequality
constraint `dif/2` and related helpers.  `dif/2` is fundamental to constraint
logic programming — it asserts that two terms must never become equal.

The implementation uses attributed variables: when `dif(X, Y)` is posted, an
attribute hook is registered that fires when X or Y is unified.  The hook
re-checks the disequality and either succeeds (terms still different), fails
(terms became equal), or re-posts (still partially unbound).

## What to move

```python
# clausal/logic/constraints.py

dif(x, y, trail)                         # post disequality constraint
_dif_hook(attr_value, bound_to, trail)   # attribute hook (fires on unify)
_collect_free_vars(term)                 # collect unbound Vars in term
_structural_unify_oc(t1, t2, trail)      # unify with occurs check
reify_eq(x, y, trail)                    # three-valued equality
```

## Why C

`_dif_hook` is called on EVERY unification of a dif-constrained variable.  In
programs with many disequality constraints (e.g., Sudoku, graph colouring),
this fires thousands of times.  The hook does:
1. `_collect_free_vars` — recursive term walk
2. Trial unification to check if terms became equal
3. Trail mark/undo around the trial unification
4. Re-post dif if still unresolved

Each of these steps involves Python function calls and term walks.

## Gotchas

1. **`_dif_hook` is registered via `register_attr_hook`** in `_variables.c`.
   The C version needs to be registered as a C callback, not a Python callable.
   This requires extending the hook mechanism in `_variables.c` to support
   C function pointers alongside Python callables.

2. **`_collect_free_vars` is recursive** — same pattern as `_is_ground`,
   `_deref_walk`, etc.  Can share implementation infrastructure.

3. **`_structural_unify_oc` with occurs check** is similar to the regular
   `unify` in `_variables.c` but checks for cycles.  The C `unify` already
   has an occurs-check variant (`unify_with_occurs_check`).

4. **Trail manipulation**: the hook does `mark = trail.mark()` → trial unify →
   `trail.undo(mark)`.  The C code must call Trail methods directly.

## Overlaps

- `C_predicate_helpers.md` — `_collect_free_vars` is similar to `_is_ground`
  and `term_variables/2`.  Share the recursive term-walk infrastructure.
- `C_clpfd_domains_and_propagation.md` — CLP(FD) also uses attributed variables
  and hooks.  The hook mechanism extension benefits both.

## How to verify

```bash
python -m pytest tests/ -k "dif or disequality or constraint" -x -q
python -m pytest tests/ --ignore=tests/test_trealla_backend.py -x -q
```
