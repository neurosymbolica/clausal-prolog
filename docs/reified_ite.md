# Clausal — Reified If-Then-Else (V2-8)

## Overview

Clausal provides a **reified if-then-else** based on Neumerkel & Kral's `if_/3` ([arXiv:1607.01590](https://arxiv.org/abs/1607.01590)). Unlike Prolog's committed-choice `(->)/2`, reified ITE is **monotonic**: adding constraints can only restrict, never lose solutions. This is the same philosophy behind Clausal's use of `dif/2` instead of `\=`, and CLP(FD) instead of `is`-based arithmetic.

Clausal has no `!/0` (cut), no `(->)/2` (committed choice), and no `(*->)/2` (soft cut). The reified ITE is the only branching construct.

---

## Syntax

In `.clausal` files, use Python's ternary expression:

```
then_goal if condition else else_goal
```

This compiles to a reified three-way branch when the condition is a built-in reifiable operation, or a sound double-evaluation fallback otherwise.

### Examples

**Ground branching — deterministic:**
```
classify(X_, L_) <- (L_ is "positive" if X_ >= 0 else L_ is "negative")
```

**Undetermined branching — explores both paths:**
```
check(X_, R_) <- (R_ is "equal" if X_ is 1 else R_ is "different")
```

When `X_` is unbound, this produces two solutions: `X_=1, R_="equal"` and `dif(X_,1), R_="different"`.

**Nested ITE:**
```
grade(S_, G_) <- (
    G_ is "A" if S_ >= 90
    else (G_ is "B" if S_ >= 80 else G_ is "C")
)
```

**ITE without else — conjunction:**

When the else branch is omitted (not possible in ternary syntax, but available via the compiler API), the ITE degenerates to conjunction: `If(cond, then, None)` is equivalent to `cond and then`.

---

## How It Works

### The three-valued decision

The core insight is **reification**: instead of a goal simply succeeding or failing, the compiler first asks "is the outcome already determined?" This produces three possible answers:

| Result | Meaning | Action |
|---|---|---|
| `True` | Condition is ground-satisfied | Run then branch (deterministic) |
| `False` | Condition is ground-violated | Run else branch (deterministic) |
| `None` | Undetermined (has unbound variables) | Explore both branches with constraints |

For ground cases, this is as efficient as a simple `if`. For undetermined cases, both paths are explored via backtracking with the appropriate constraints attached:

- **Then path**: unify/constrain the condition to hold, then run the then branch
- **Else path**: constrain the condition to *not* hold (via `dif/2` or negated FD constraint), then run the else branch

This is a direct translation of Neumerkel's `(=)/3` and `if_/3`.

### Reifiable vs general conditions

The compiler distinguishes two kinds of conditions:

**Reifiable conditions** get the fast three-way check:

| Condition | Reified via | Undetermined: then path | Undetermined: else path |
|---|---|---|---|
| `X_ is Y_` | `reify_eq` | `unify(X, Y)` | `dif(X, Y)` |
| `X_ is not Y_` | `reify_eq` (inverted) | `dif(X, Y)` | `unify(X, Y)` |
| `X_ == Y_` | `reify_fd("eq")` | `fd_eq(X, Y)` | `fd_ne(X, Y)` |
| `X_ != Y_` | `reify_fd("ne")` | `fd_ne(X, Y)` | `fd_eq(X, Y)` |
| `X_ < Y_` | `reify_fd("lt")` | `fd_lt(X, Y)` | `fd_ge(X, Y)` |
| `X_ <= Y_` | `reify_fd("le")` | `fd_le(X, Y)` | `fd_gt(X, Y)` |
| `X_ > Y_` | `reify_fd("gt")` | `fd_gt(X, Y)` | `fd_le(X, Y)` |
| `X_ >= Y_` | `reify_fd("ge")` | `fd_ge(X, Y)` | `fd_lt(X, Y)` |

**Non-reifiable conditions** (arbitrary predicate calls, `in`, etc.) use a sound double-evaluation pattern:

1. Run the condition as a sub-generator. For each solution, run the then branch.
2. Run NAF of the condition. If no solutions exist, run the else branch.

This evaluates the condition twice but is always correct. For tabled predicates, the false path uses `_naf_tabled` instead of inline NAF.

---

## Reification Primitives

### `reify_eq(x, y, trail) -> bool | None`

Three-valued equality decision procedure in `clausal.logic.constraints`:

1. Deref both sides.
2. If `x is y` (identical objects) → `True`.
3. Sandbox-unify with occurs check (`_structural_unify_oc`).
4. If unification fails → `False` (structurally incompatible).
5. If unification succeeds with no trail growth → `True` (ground-equal).
6. If unification succeeds with trail growth → `None` (undetermined). Undo and return.

No side effects — the trail is always restored to its original state.

Handles `Var`, scalars, tuples, lists, `Compound`, and `PredicateMeta` instances.

### `reify_fd(op, x, y, trail) -> bool | None`

Three-valued CLP(FD) comparison in `clausal.logic.clpfd`:

- `op` is one of `"eq"`, `"ne"`, `"lt"`, `"le"`, `"gt"`, `"ge"`.
- If both sides are ground (no unbound Vars after resolving arithmetic): evaluate and return `True`/`False`.
- Otherwise: return `None` (undetermined — needs FD constraints).

---

## Compiler Integration

The `IfExpr` AST node (Python's ternary `body if test else orelse`) is handled in both `compile_goal` and `compile_goal_trampoline` in `clausal.logic.compiler`.

### Generated code (reifiable equality condition)

For `R_ is "yes" if X_ is 1 else R_ is "no"`:

```python
_reif_0 = _reify_eq(X_, 1, trail)
if _reif_0 is True:
    # then branch: R_ is "yes"
    _m_0 = trail.mark()
    if unify(R_, "yes", trail):
        yield None  # solution
    trail.undo(_m_0)
elif _reif_0 is False:
    # else branch: R_ is "no"
    _m_1 = trail.mark()
    if unify(R_, "no", trail):
        yield None
    trail.undo(_m_1)
else:
    # undetermined: explore both with constraints
    _m_2 = trail.mark()
    if unify(X_, 1, trail):        # then path: X = 1
        _m_3 = trail.mark()
        if unify(R_, "yes", trail):
            yield None
        trail.undo(_m_3)
    trail.undo(_m_2)
    if _dif(X_, 1, trail):         # else path: dif(X, 1)
        _m_4 = trail.mark()
        if unify(R_, "no", trail):
            yield None
        trail.undo(_m_4)
```

### Generated code (general non-reifiable condition)

For `then_goal if member(X, Xs) else else_goal`:

```python
def _ite_cond_0():
    # compiled member(X, Xs) with yield None as k_stmts
    ...
    return; yield

# True path: for each solution of condition, run then
_m_0 = trail.mark()
for _ in _ite_cond_0():
    <compiled then_goal>
trail.undo(_m_0)

# False path: NAF of condition → run else
_naf_0 = True
_m_1 = trail.mark()
for _ in _ite_cond_0():
    _naf_0 = False
    break
trail.undo(_m_1)
if _naf_0:
    <compiled else_goal>
```

### Trampoline mode

Both reifiable and general ITE work in trampoline mode. The then/else branches compile in trampoline mode. For general ITE, the condition sub-generator is compiled in simple mode (same pattern as NAF in trampoline).

---

## Python API

```python
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.constraints import reify_eq
from clausal.logic.clpfd import reify_fd

trail = Trail()

# Ground cases — deterministic
assert reify_eq(1, 1, trail) is True
assert reify_eq(1, 2, trail) is False

# Undetermined — no bindings left behind
x = Var()
assert reify_eq(x, 42, trail) is None
assert deref(x) is x  # x still unbound

# CLP(FD) reification
assert reify_fd("lt", 3, 5, trail) is True
assert reify_fd("lt", 5, 3, trail) is False

y = Var()
assert reify_fd("eq", y, 3, trail) is None
```

---

## Why Not Committed Choice

Prolog's `( Cond -> Then ; Else )` is `once(Cond) -> Then ; Else` — it commits to the first solution of `Cond` and discards all alternatives. This is non-monotonic: adding constraints can lose solutions.

Classic example from the paper:

```prolog
memberchk(X, [1,2]), X = 2.   % fails! memberchk commits to X=1
```

Goal reordering changes answers — a fundamental soundness problem. Even "soft cut" `(*->)/2` has the same issues.

Clausal avoids this entirely:

- **Reifiable conditions** get a three-way check: ground cases are deterministic (no choicepoints), undetermined cases explore both branches with proper constraints.
- **Non-reifiable conditions** use double evaluation (sound NAF-based).
- **Users who want first-solution commitment** can use `once()` explicitly (future builtin).

The result is a system where goal reordering is always safe and adding constraints never loses solutions.

---

## Test Coverage

Tests are in `tests/test_reified_ite.py` (54 tests).

- **`reify_eq` unit tests** (20): identical var, ground equal/incompatible (int, str, type mismatch), undetermined (var-int, int-var, two vars), bound var equal/inequal, Compound (same/different/different functor/with var), PredicateMeta (same/different), lists (same/different/with var), no side effects
- **`reify_fd` unit tests** (10): ground eq/ne/lt/ge true/false, undetermined with vars
- **Reified ITE equality** (6): ground true/false, undetermined explores both — simple + trampoline modes
- **Reified ITE dif** (3): ground dif true/false, undetermined with swapped branches
- **Reified ITE FD** (4): ground lt/eq true/false
- **General ITE** (4): succeeding/failing condition — simple + trampoline modes
- **Control flow** (6): no-else (conjunction), nested ITE, binding preservation, conjunction body
- **Import integration** (1): `.clausal` file with ITE imported and queried via `solve` API
