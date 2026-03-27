# Clausal — Reified If-Then-Else

## Overview

Clausal provides a **reified if-then-else** based on Neumerkel & Kral's `if_/3` ([arXiv:1607.01590](https://arxiv.org/abs/1607.01590)). Unlike Prolog's committed-choice `(->)/2`, reified ITE is **monotonic**: adding constraints can only restrict, never lose solutions. This is the same philosophy behind Clausal's use of `Dif/2` instead of `\=`, and CLP(ℤ) instead of `is`-based arithmetic.

Clausal has no `!/0` (cut), no `(->)/2` (committed choice), and no `(*->)/2` (soft cut). The reified ITE is the only branching construct.

---

## Syntax

In `.clausal` files, use the `If` function call:

```clausal
# skip
If(condition, then_goal, else_goal)
```

This compiles to a reified three-way branch when the condition is a built-in reifiable operation, or a sound double-evaluation fallback otherwise.

All three arguments are required.

### Examples

**Ground branching — deterministic:**
```clausal
classify(X, L) <- If(X >= 0, L is "positive", L is "negative")
```

**Undetermined branching — explores both paths:**
```clausal
check(X, R) <- If(X is 1, R is "equal", R is "different")
```

When `X` is unbound, this produces two solutions: `X=1, R="equal"` and `dif(X,1), R="different"`.

**Nested ITE:**
```clausal
grade(S, G) <- If(S >= 90, G is "A", If(S >= 80, G is "B", G is "C"))
```

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
| `X is Y` | `reify_eq` | `unify(X, Y)` | `dif(X, Y)` |
| `X is not Y` | `reify_eq` (inverted) | `dif(X, Y)` | `unify(X, Y)` |
| `X == Y` | `reify_fd("eq")` | `fd_eq(X, Y)` | `fd_ne(X, Y)` |
| `X != Y` | `reify_fd("ne")` | `fd_ne(X, Y)` | `fd_eq(X, Y)` |
| `X < Y` | `reify_fd("lt")` | `fd_lt(X, Y)` | `fd_ge(X, Y)` |
| `X <= Y` | `reify_fd("le")` | `fd_le(X, Y)` | `fd_gt(X, Y)` |
| `X > Y` | `reify_fd("gt")` | `fd_gt(X, Y)` | `fd_le(X, Y)` |
| `X >= Y` | `reify_fd("ge")` | `fd_ge(X, Y)` | `fd_lt(X, Y)` |

**Non-reifiable conditions** (arbitrary predicate calls, `in`, etc.) use a single-evaluation pattern with a `_found` flag:

1. Run the condition as a sub-generator. For each solution, set `_found = True` and run the then branch.
2. After exhaustion, if `_found` is false, run the else branch.

This evaluates the condition only once. For tabled predicates, the false path uses `_naf_tabled` instead (WFS requires separate tabled negation).

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

Three-valued CLP(ℤ) comparison in `clausal.logic.clpfd`:

- `op` is one of `"eq"`, `"ne"`, `"lt"`, `"le"`, `"gt"`, `"ge"`.
- If both sides are ground (no unbound Vars after resolving arithmetic): evaluate and return `True`/`False`.
- Otherwise: return `None` (undetermined — needs FD constraints).

---

## Compiler Integration

The `If(condition, then, else)` call syntax is parsed into an `IfExpr` AST node, which is handled in both `compile_goal` and `compile_goal_trampoline` in `clausal.logic.compiler`.

### Generated code (reifiable equality condition)

For `If(X is 1, R is "yes", R is "no")`:

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

For `If(member(X, Xs), then_goal, else_goal)`:

```python
def _ite_cond_0():
    # compiled member(X, Xs) with yield None as k_stmts
    ...
    return; yield

# Single evaluation with _found flag
_found_0 = False
_m_0 = trail.mark()
for _ in _ite_cond_0():
    _found_0 = True
    <compiled then_goal>
trail.undo(_m_0)
if not _found_0:
    <compiled else_goal>
```

For tabled predicates, the false path uses `_naf_tabled` instead of the `_found` flag (required for WFS soundness with conditional answers).

### Trampoline mode

Both reifiable and general ITE work in trampoline mode. The then/else branches compile in trampoline mode. For general ITE, the condition sub-generator is compiled in simple mode (same pattern as NAF in trampoline).

---

??? example "Python API"

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
    
    # CLP(ℤ) reification
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
memberchk(X, [1,2]), X = 2.   % fails! memberchk commits to X=1 (Prolog)
```

Goal reordering changes answers — a fundamental soundness problem. Even "soft cut" `(*->)/2` has the same issues.

Clausal avoids this entirely:

- **Reifiable conditions** get a three-way check: ground cases are deterministic (no choicepoints), undetermined cases explore both branches with proper constraints.
- **Non-reifiable conditions** use single evaluation with a `_found` flag.
- **Users who want first-solution commitment** use `Once()` explicitly.

The result is a system where goal reordering is always safe and adding constraints never loses solutions.

---

## `Once()` — First-Solution Commitment

`Once(goal)` is a builtin meta-predicate that commits to the first solution of `goal`. It compiles to a sub-generator with a `break` after the first yield:

```python
def _once_gen_0():
    <compiled goal with yield None as k_stmts>
    return; yield

_m_0 = trail.mark()
for _ in _once_gen_0():
    <k_stmts>        # bindings from goal are visible here
    break             # stop after first solution
trail.undo(_m_0)
```

Key properties:
- **Bindings escape**: unlike `Not`, bindings from the once'd goal are visible to the continuation.
- **Continuation backtracks normally**: `Once(X in [1,2]) and Y in [a,b]` produces `(1,a), (1,b)` — only `X` is committed, `Y` still backtracks.
- **Failing goal = no solutions**: if the inner goal has no solutions, the continuation is never reached.
- **Works in both simple and trampoline modes**: inner goal always compiles in simple mode (sub-generator pattern).

`Once()` is the explicit escape hatch for users who want first-solution commitment. It replaces Prolog's `once/1` and is the building block for committed-choice patterns like `If(Once(goal), then, else)`.

---

??? info "Test coverage"

    Tests are in `tests/test_reified_ite.py` (99 tests).

    - **`reify_eq` unit tests** (20): identical var, ground equal/incompatible (int, str, type mismatch), undetermined (var-int, int-var, two vars), bound var equal/inequal, Compound (same/different/different functor/with var), PredicateMeta (same/different), lists (same/different/with var), no side effects
    - **`reify_fd` unit tests** (10): ground eq/ne/lt/ge true/false, undetermined with vars
    - **Reified ITE equality** (6): ground true/false, undetermined explores both — simple + trampoline modes
    - **Reified ITE dif** (3): ground dif true/false, undetermined with swapped branches
    - **Reified ITE FD** (4): ground lt/eq true/false
    - **General ITE** (4): succeeding/failing condition — simple + trampoline modes
    - **Control flow** (6): no-else (conjunction), nested ITE, binding preservation, conjunction body
    - **Multi-solution ITE** (2): multi-solution condition, binding preservation
    - **dif interaction** (2): pre-existing dif constraint, undetermined with compatible dif
    - **Tabled ITE** (2): tabled condition with true/false paths
    - **Import integration** (5): `.clausal` file with ITE, memberd ground/absent/unbound/no-duplicates
    - **`once()` tests** (12): first solution only, failing goal, continuation backtracking, binding preservation, once-inside-If, `.clausal` file integration — simple + trampoline modes
    - **`once()` .clausal integration** (1): `once_member.clausal` fixture

---

*See also: [Constraints](constraints.md) — `Dif/2` and CLP(ℤ) constraints used by reified ITE · [Tabling](tabling.md) — WFS negation for tabled predicates · [Lambdas](lambdas.md) — closures that can appear as ITE conditions.*
