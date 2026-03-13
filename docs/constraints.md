# Constraints

Clausal supports constraint logic programming through attributed variables. The C extension provides `AttVar` (attributed variable), `put_attr`/`get_attr`/`del_attr` (all trailed), `register_attr_hook`, and a wakeup queue in `do_unify_and_wake`. Constraint solvers register hooks that fire when a constrained variable is unified.

The implementation lives in `clausal.logic.constraints` (V2-5).

---

## dif/2 — Disequality constraint

`dif(X, Y)` constrains X and Y to be different. Unlike a point-in-time check, the constraint survives and is re-evaluated whenever either variable gets bound.

### Syntax

In `.clausal` files, `is not` has dif semantics:

```
safe_assign(X_, Y_) <- (
    X_ is not Y_
    and X_ is 1
    and Y_ is 2
)
```

This succeeds because X and Y end up with different values (1 and 2), even though at the time of `is not` they are both unbound.

The builtin `dif/2` can also be called explicitly:

```
constrained(X_, Y_) <- (
    dif(X_, Y_)
    and X_ is 1
    and Y_ is 2
)
```

### Semantics

| Clausal syntax | Semantics | Prolog equivalent |
|---|---|---|
| `X_ is not Y_` | Constraint: must end up different | `dif(X, Y)` |
| `not (X_ is Y_)` | Immediate: don't unify right now | `\=(X, Y)` |

The `is not` operator changed from Prolog `\=` (immediate) to Prolog `dif/2` (constraint) in V2-5. The old immediate-check semantics are still available as `not (X_ is Y_)` — negation-as-failure of unification — which already works via the existing `Not(Unify(...))` compilation path.

### Examples

**Constraint succeeds — terms stay different:**
```
X_ is not Y_, X_ is 1, Y_ is 2    # succeeds: 1 ≠ 2
```

**Constraint fails — terms become equal:**
```
X_ is not Y_, X_ is 1, Y_ is 1    # fails: dif violated when Y=1
```

**Multiple constraints:**
```
X_ is not 1, X_ is not 2, X_ is 3    # succeeds: 3 ≠ 1 and 3 ≠ 2
X_ is not 1, X_ is not 2, X_ is 1    # fails: dif(X, 1) violated
```

**Immediate check (old semantics):**
```
not (X_ is Y_)    # fails if X and Y are both unbound (they CAN unify)
```

---

## Design

### All Vars are AttVars

`clausal.logic.variables` aliases `Var = AttVar`. Every logic variable created with `Var()` is an attributed variable from birth. `AttVar` inherits from the C `Var` type via `tp_base`, so `is_var()`, `deref()`, and `unify()` work unchanged. The only overhead is 8 bytes per variable for a NULL attributes pointer (no dict is allocated until a constraint is actually attached).

The original `Var` type is available as `PlainVar` if needed.

### Constraint algorithm

When `dif(x, y, trail)` is called:

1. Deref both arguments.
2. Sandbox-unify with occurs check (`_structural_unify_oc`).
3. **Unify fails** → structurally incompatible (e.g. `dif(1, 2)`) → return True immediately.
4. **Unify succeeds, no trail growth** → terms already identical (e.g. `dif(X, X)`) → return False.
5. **Unify succeeds with trail growth** → terms could become equal → undo sandbox, collect all free variables in both terms, attach `(x, y)` constraint pair to each via `put_attr`, return True.

`_structural_unify_oc` extends the C extension's `unify_with_occurs_check` to handle `Compound`, `PredicateMeta` instances, and lists (which the C extension treats as opaque objects and compares with `==`).

### Attribute hook

When a constrained variable is unified, the `_dif_hook` fires:

1. For each `(x, y)` constraint pair on the variable:
   - Deref and sandbox-unify.
   - **Fails** → constraint satisfied, drop it.
   - **Succeeds, no trail growth** → terms now identical, constraint violated → return False (blocks unification).
   - **Succeeds with trail growth** → still pending → undo sandbox, re-attach to remaining free variables.
2. If all constraints survive, return True.

Constraint deduplication uses tuple identity (`is`) to avoid attaching the same pair to a variable twice during re-attachment.

### Backtracking

All `put_attr` calls go through the trail, so constraint attachment is automatically undone on `trail.undo(mark)`. No explicit cleanup is needed.

### Compiler integration

The `DoesNotUnify` goal node compiles to:

```python
if _dif(X, Y, trail):
    k_stmts
```

No mark/undo wrapper — `dif` handles its own sandboxing. `_dif` is injected into `base_globals` in both `compile_predicate` and `compile_predicate_trampoline`.

---

## Python API

```python
from clausal.logic.variables import Var, Trail, unify, deref
from clausal.logic.constraints import dif

trail = Trail()
x, y = Var(), Var()

# Post constraint
dif(x, y, trail)  # True — constraint posted

# Bind to different values: succeeds
unify(x, 1, trail)  # True
unify(y, 2, trail)  # True — dif satisfied

# Or bind to same value: fails
trail2 = Trail()
a, b = Var(), Var()
dif(a, b, trail2)   # True
unify(a, 1, trail2)  # True
unify(b, 1, trail2)  # False — dif violated
```

---

## Test coverage

Tests are in `tests/test_dif.py` (42 tests).

- **`_collect_free_vars`**: scalars, Vars, bound vars, tuples, lists, Compounds, nested structures, deduplication
- **Direct `dif`**: ground equal/different, same var, one var, both vars, compound terms
- **Occurs check**: `dif(X, f(X))` → succeed (can never be equal)
- **Constraint propagation**: same/different values, multiple constraints, compound args, transitive via shared var
- **Backtracking**: constraint undone on trail undo, binding failure doesn't corrupt trail
- **Compiled integration**: `is not` with later binding (succeed/fail), ground terms, same var, `not (X is Y)` still works, multiple constraints
- **Builtin `dif/2`**: callable from clausal code, with vars and ground terms
- **Import hook**: `.clausal` file with `is not` using proper dif semantics
