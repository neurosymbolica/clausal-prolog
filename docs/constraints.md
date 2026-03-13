# Constraints

Clausal supports constraint logic programming through attributed variables. The C extension provides `AttVar` (attributed variable), `put_attr`/`get_attr`/`del_attr` (all trailed), `register_attr_hook`, and a wakeup queue in `do_unify_and_wake`. Constraint solvers register hooks that fire when a constrained variable is unified.

Two constraint solvers are built in:

- **dif/2** — disequality constraint (`clausal.logic.constraints`, V2-5)
- **CLP(FD)** — finite-domain constraints (`clausal.logic.clpfd`, V2-6)

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

---

## CLP(FD) — Finite-domain constraints

CLP(FD) is built into the language as the default way to reason about integers (per Markus Triska's recommendation). The comparison operators `==`, `!=`, `<`, `>`, `<=`, `>=` are CLP(FD) constraint operators.

The implementation lives in `clausal.logic.clpfd` (V2-6).

### Operator semantics

| Operator | Meaning |
|---|---|
| `==` | CLP(FD) arithmetic equality |
| `!=` | CLP(FD) arithmetic disequality |
| `<` `>` `<=` `>=` | CLP(FD) comparison constraints |
| `is` | Unification (unchanged) |
| `is not` | dif/2 constraint (unchanged) |
| `:=` | Eager arithmetic eval + unify (unchanged) |

When both sides are ground (no unbound Vars), the operators fall back to direct Python comparison. When at least one side is an unbound Var, CLP(FD) constraints are posted.

The old structural-equality behaviour of `==` is available as the named builtin `equivalent/2`.

### Domain representation

Domains are sorted tuples of `(lo, hi)` inclusive integer intervals:

```python
Domain = tuple[tuple[int, int], ...]  # e.g., ((1, 5), (8, 10))
```

Most domains are contiguous `((lo, hi),)` — single-interval fast path is optimised throughout.

### FDVar — per-variable state

Each constrained variable stores an `FDVar` as an attributed-variable attribute under the key `"fd"`:

```python
class FDVar:
    __slots__ = ('domain', 'constraints')
    domain: Domain
    constraints: tuple[Constraint, ...]  # immutable for trail safety
```

**Trail safety**: every domain narrowing or constraint addition creates a new `FDVar` and calls `put_attr(var, "fd", new_state, trail)`. The old state is automatically restored on `trail.undo()`. Never mutate in place.

### Auto-domain

When a CLP(FD) operator encounters an unbound Var with no FD domain, it auto-creates a default domain of `(-2^63, 2^63)` — effectively unbounded for practical purposes, stored as a single interval.

### Constraint types

| Constraint | Description |
|---|---|
| `EqConstraint(lhs, rhs)` | X == Y — narrow both domains to intersection |
| `NeConstraint(lhs, rhs)` | X != Y — when one side is singleton, remove from other |
| `LtConstraint(lhs, rhs)` | X < Y — upper-bound X by max(Y)-1, lower-bound Y by min(X)+1 |
| `LeConstraint(lhs, rhs)` | X <= Y — upper-bound X by max(Y), lower-bound Y by min(X) |
| `AllDiffConstraint(vars)` | all_different — when one var is ground, remove from all others |

### Propagation (AC-3)

Constraints are propagated via an AC-3 fixpoint loop. When a propagator narrows a domain:

1. Create new `FDVar` with narrowed domain + same constraints.
2. `put_attr(var, "fd", new_state, trail)` — trailed.
3. If singleton `{v}`: `unify(var, v, trail)` → fires FD hook + dif hooks.
4. If empty: return False (wipeout → backtrack).
5. Add var to propagation queue.

### FD attribute hook

`_fd_hook` fires when an FD-constrained variable is unified:

- **Bound to integer**: check domain membership, propagate all constraints.
- **Bound to another Var**: intersect domains, merge constraints, check singleton, propagate.
- **Bound to non-integer/non-Var**: fail.

### Expression domain arithmetic

CLP(FD) constraint functions walk arithmetic expression trees (`Add`, `Sub`, `Mult`, `Negate`) to compute domain bounds:

```
[a,b] + [c,d] = [a+c, b+d]
[a,b] - [c,d] = [a-d, b-c]
[a,b] * [c,d] = [min(corners), max(corners)]
-[a,b]        = [-b, -a]
```

Ground arithmetic expressions are evaluated before comparison.

### Builtins

| Builtin | Arity | Description |
|---|---|---|
| `in_domain` | 3 | `in_domain(Var_or_list, Lo, Hi)` — post domain [Lo, Hi] |
| `label` | 1 | `label(Vars)` — enumerate values, first-fail strategy |
| `all_different` | 1 | `all_different(Vars)` — pairwise disequality constraint |
| `equivalent` | 2 | `equivalent(X, Y)` — structural equality (old `==` behavior) |

### Syntax examples

**Domain declaration and labeling:**
```
solve(X_) <- (
    in_domain(X_, 1, 10)
    and label([X_])
)
```

**Chained comparison (natural Python syntax):**
```
bounded(X_) <- (1 <= X_ and X_ <= 10 and label([X_]))
```

Since `<=` is CLP(FD), `1 <= X_` and `X_ <= 10` naturally constrain X's domain.

**N-Queens via all_different:**
```
queens(N_, Qs_) <- (
    in_domain(Qs_, 1, N_)
    and all_different(Qs_)
    and label(Qs_)
    and check_diagonals(Qs_)
)
```

**SEND + MORE = MONEY:**
```
sendmoney(S_, E_, N_, D_, M_, O_, R_, Y_) <- (
    in_domain([S_, E_, N_, D_, M_, O_, R_, Y_], 0, 9)
    and all_different([S_, E_, N_, D_, M_, O_, R_, Y_])
    and S_ != 0
    and M_ != 0
    and label([S_, E_, N_, D_, M_, O_, R_, Y_])
    and (Send_ := S_ * 1000 + E_ * 100 + N_ * 10 + D_)
    and (More_ := M_ * 1000 + O_ * 100 + R_ * 10 + E_)
    and (Money_ := M_ * 10000 + O_ * 1000 + N_ * 100 + E_ * 10 + Y_)
    and (Sum_ := Send_ + More_)
    and Sum_ == Money_
)
```

### Python API

```python
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.clpfd import in_domain, label, all_different, fd_eq, fd_ne, fd_lt

trail = Trail()
x, y = Var(), Var()

# Post domains
in_domain([x, y], 1, 10, trail)

# Post constraint: X < Y
fd_lt(x, y, trail)

# Label (enumerate solutions)
for _ in label([x, y], trail):
    print(deref(x), deref(y))
```

### Interaction with dif/2

CLP(FD) and dif/2 use independent attribute keys (`"fd"` and `"dif"`). Both hooks fire when a variable is bound. They do not interfere with each other. A variable can have both FD constraints and dif constraints simultaneously.

### Compiler integration

`StructuralEq`/`StructuralNeq` and `Lt`/`LtE`/`Gt`/`GtE` goal nodes compile to:

```python
if _fd_eq(l, r, trail):    # ==
    k_stmts
if _fd_ne(l, r, trail):    # !=
    k_stmts
if _fd_lt(l, r, trail):    # <
    k_stmts
```

Both sides are compiled with `eval_arith=False` so arithmetic expression trees survive as structural terms for CLP(FD) domain arithmetic. The `_fd_*` functions are injected into `base_globals` in both `compile_predicate` and `compile_predicate_trampoline`.

### Test coverage

Tests are in `tests/test_clpfd.py` (74 tests).

- **Domain operations**: from_range, contains, min/max, size, singleton, intersection, remove, remove_above/below, values
- **in_domain**: post domain, unify succeeds/fails, list, narrows existing, singleton binds, empty fails, ground int
- **label**: single var, two vars (cartesian product), backtracking restores, all ground
- **equivalent**: same/different atoms, compounds, vars, bound vars
- **fd_eq/ne/lt/le/gt/ge**: ground values, var-int, var-var, auto-domain, wipeout
- **Propagation**: lt chain, eq propagation, wipeout, backtracking restores domains
- **Compiler integration**: ground eq/ne/lt/le/gt/ge, var eq via solve, chained le, ne with label, evaluate unchanged, is unchanged, is-not unchanged
- **all_different**: basic permutations, ground ok/fail, via solve
- **N-Queens**: 4-queens (2 solutions), 8-queens (92 solutions)
- **SEND+MORE=MONEY**: unique solution (9567 + 1085 = 10652)
- **FD + dif interaction**: both constraints on same var, independent operation
