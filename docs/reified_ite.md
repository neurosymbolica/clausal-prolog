# Clausal — Reified If-Then-Else

## Overview

Clausal provides a **reified if-then-else** based on Neumerkel & Kral's `if_/3` ([arXiv:1607.01590](https://arxiv.org/abs/1607.01590)). Unlike Prolog's committed-choice `(->)/2`, reified ITE is **monotonic**: adding constraints can only restrict, never lose solutions. This is the same philosophy behind Clausal's use of [`dif/2`](constraints.md) instead of `\=`, and [CLP(ℤ)](constraints.md#clp-integer-constraints) (`==`) instead of ISO `'is'/2` arithmetic (see [Arithmetic](arithmetic.md)).

Clausal has no `!/0` (cut), no `(->)/2` (committed choice), and no `(*->)/2` (soft cut). The reified ITE is the only branching construct.

---

## Syntax

In `.clausal` files, use the `if_` function call:

```seam
--8<-- "tests/fixtures/docs/misc_phase7_sigs.txt:if_signature"
```

`if_` is library(reif)'s `if_/3` (Scryer's): the condition must be
**reifiable** -- something that answers *true* or *false* (or both, each under
a constraint), never a plain goal that merely succeeds or fails.  A reifiable
condition is one of:

- a **reified comparison** -- `X is Y`, `X is not Y` (reif's `=/3`, `dif/3`),
  `==`, `!=`, `<`, `<=`, `>`, `>=` (CLP(ℤ) reification) -- compiled to the
  three-way branch below;
- a **conjunction** `(A, B)` / `A and B` or **disjunction** `A or B` of
  reifiable conditions (reif's `','/3` and `;/3`):
  `if_(A, if_(B, Then, Else), Else)` and `if_(A, Then, if_(B, Then, Else))`;
- a **closure** called with one more argument, the truth value: `p_t(X)`
  when `p_t/2` exists (it binds its last argument to `True` or `False`),
  `memberd_t(E, Es)`, `'='(X, Y)`, `call(C, X)`, or a variable bound to a
  closure at run time.  It runs as reif's own body,
  `p_t(X, T), must_be(boolean, T), if_(T is True, Then, Else)`, so every way
  the closure answers is a solution:

```seam
-import_from(clausal.stdlib.reif, [memberd_t])
-private([a, b, yes, no])
q(X, R) <- if_(memberd_t(X, [a, b]), R is yes, R is no)
# X = a, R = yes ; X = b, R = yes ; dif(X, a), dif(X, b), R = no
```

Anything else -- a plain goal `p(X)` with no `p/2`, `not G`, `X in L`,
`once(G)`, a type test such as `atom(X)`, a literal `True` -- is refused when
the file loads, with a `SyntaxError` naming the predicate and line and the
reified form to write instead.  (Until 2026-10-01 the seam ran such a
condition as a soft cut: every solution of the condition, the else branch
only when there were none.  That is not monotone, and it is gone.)  When the
plain goal is semidet, write it as two exclusive alternatives,
`(atom(X), R is yes) or (not atom(X), R is no)`, or define the reified
`p_t/2`.

A unification with a partial list, `if_(X is [a, *T], ...)` (in a `.pl`
file, `if_(X = [a|T], ...)`), is reif's `=/3`: with `X = [a, b]` it answers
the then branch (`T = [b]`) and the else branch (`dif(T, [b])`), as Scryer
does.

In a DCG or EDCG body the condition must be a `{Goal}` block (it consumes no
input), with `Goal` reifiable: `if_({V == 1}, [y], [z])`.  A grammar body as
the condition (`if_([x], ...)`) is refused for the same reason.

All three arguments are required.

### In a `.pl` file: library(reif)'s `if_/3`

A `.pl` file on the native front end (`CLAUSAL_PL_FRONTEND=native`) that
imports `library(reif)` gets Scryer's `if_(If_1, Then_0, Else_0)`: `If_1` is
a CLOSURE called with one more argument, the truth value, and the branch
follows it (`instantiation_error` when it is unbound,
`type_error(boolean, T)` when it is neither `true` nor `false`).
`if_(X = Y, ...)` and `if_(dif(X, Y), ...)` compile to the reified branch
above, and `if_((A, B), ...)`/`if_((A ; B), ...)` are unfolded as reif's
`','/3` and `;/3`. Without the import `if_` is an ordinary (undefined) call,
as in Scryer. The seam's `if_` has the same meaning (see above): a .pl
`if_(memberd_t(X, [a, b]), R = yes, R = no)` and the seam
`if_(memberd_t(X, [a, b]), R is yes, R is no)` give the same three answers.

### The old spelling, `If/3`

`if_` was once spelled `If`.  That spelling is TitleCase, which has no role in
Clausal code, so a file carrying it no longer loads: the TitleCase lint raises
a located `SyntaxError` at the first `If(...)` naming the rewrite
(`If` -> `if_`).  Nothing in the library emits it: the
[reifier](reflection.md)'s renderer writes `if_`, so a round-trip through
`reify_source`/`render_source` migrates a clause for you.

### Examples

**Ground branching — deterministic:**
```seam
classify(X, L) <- if_(X >= 0, L is 'positive', L is 'negative')
```

**Undetermined branching — explores both paths:**
```seam
check(X, R) <- if_(X is 1, R is 'equal', R is 'different')
```

when `X` is unbound, this produces two solutions: `X=1, R='equal'` and `dif(X,1), R='different'`:

```python
# in a .seam file
[R for R in --check(_, R)]      # ['equal', 'different']
```

(Exporting `X` too would raise `ResidualConstraints` on the second answer: a
seam export must be a value, and there `X` is unbound under `dif`.)

**Nested ITE:**
```seam
grade(S, G) <- if_(S >= 90, G is 'A', if_(S >= 80, G is 'B', G is 'C'))
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

### Reified comparisons

A reified comparison gets the three-way check:

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

A closure condition compiles to the closure call with the truth value
appended, `must_be(boolean, T)`, and this three-way check on `T is True`.
There is no other kind: a non-reifiable condition does not load.

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

Handles `Var`, scalars (an atom is a `str`), cells (compound terms are plain tuples), and lists.

### `reify_fd(op, x, y, trail) -> bool | None`

Three-valued CLP(ℤ) comparison in `clausal.logic.clpfd`:

- `op` is one of `"eq"`, `"ne"`, `"lt"`, `"le"`, `"gt"`, `"ge"`.
- If both sides are ground (no unbound Vars after resolving arithmetic): evaluate and return `True`/`False`.
- Otherwise: return `None` (undetermined — needs FD constraints).

---

## Compiler Integration

The `if_(condition, then, else)` call syntax is parsed into an `IfExpr` AST node, which is handled in both `compile_goal` and `compile_goal_trampoline` in the [compiler](compiler.md).

### Generated code (reifiable equality condition)

For `if_(X is 1, R is 'yes', R is 'no')`:

```python
_reif_0 = _reify_eq(X_, 1, trail)
if _reif_0 is True:
    # then branch: R_ is 'yes'
    _m_0 = trail.mark()
    if unify(R_, "yes", trail):
        yield None  # solution
    trail.undo(_m_0)
elif _reif_0 is False:
    # else branch: R_ is 'no'
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

### Generated code (closure condition)

For `if_(memberd_t(X, Es), then_goal, else_goal)` the compiler emits the code
for `memberd_t(X, Es, T), must_be(boolean, T), if_(T is True, then_goal,
else_goal)`: the reified equality branch above, once per answer of the
closure.

### Trampoline mode

Both strategies compile the same reified branch; the then/else branches
compile in the enclosing strategy.

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

- **`if_` requires a reifiable condition**: ground cases are deterministic (no choicepoints), undetermined cases explore both branches with proper constraints, and a closure's every answer is explored.
- **A plain goal is not a condition**: it is refused at load time rather than run as a soft cut.
- **Users who want first-solution commitment** use `once()` explicitly.

The result is a system where goal reordering is always safe and adding constraints never loses solutions.

---

## `once()` — First-Solution Commitment

`once(goal)` is a builtin meta-predicate that commits to the first solution of `goal`. It compiles to a sub-generator with a `break` after the first yield:

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
- **Bindings escape**: unlike `not`, bindings from the once'd goal are visible to the continuation.
- **Continuation backtracks normally**: `(once(in_(X, [1, 2])), in_(Y, ['a', 'b']))` produces `(1, 'a'), (1, 'b')` — only `X` is committed, `Y` still backtracks.
- **Failing goal = no solutions**: if the inner goal has no solutions, the continuation is never reached.
- **Works in both simple and trampoline modes**: inner goal always compiles in simple mode (sub-generator pattern).

`once()` is the explicit escape hatch for users who want first-solution commitment. It is ISO's `once/1`. It is not an `if_` condition (it is a plain goal); commit inside a reified closure instead. See also [Control](control.md) for other control-flow predicates.

---

??? info "Test coverage"

    Tests are in `tests/test_reified_ite.py`.

    - **`reify_eq` unit tests** (20): identical var, ground equal/incompatible (int, str, type mismatch), undetermined (var-int, int-var, two vars), bound var equal/inequal, cells (same/different/different functor/with var), lists (same/different/with var), no side effects
    - **`reify_fd` unit tests** (10): ground eq/ne/lt/ge true/false, undetermined with vars
    - **Reified ITE equality** (6): ground true/false, undetermined explores both — simple + trampoline modes
    - **Reified ITE dif** (3): ground dif true/false, undetermined with swapped branches
    - **Reified ITE FD** (4): ground lt/eq true/false
    - **Non-reifiable conditions** : refused at load time (`tests/iso_l3/test_seam_if_requires_reifiable.py`)
    - **Control flow** (6): no-else (conjunction), nested ITE, binding preservation, conjunction body
    - **dif interaction** (2): pre-existing dif constraint, undetermined with compatible dif
    - **Import integration** (5): `.clausal` file with ITE, memberd ground/absent/unbound/no-duplicates
    - **`once()` tests** (12): first solution only, failing goal, continuation backtracking, binding preservation, once-inside-if_, `.clausal` file integration — simple + trampoline modes
    - **`once()` .clausal integration** (1): `once_member.seam` fixture

---

*See also: [Constraints](constraints.md) — `dif/2` and CLP(ℤ) constraints used by reified ITE · [Tabling](tabling.md) — WFS negation for tabled predicates · [Lambdas](lambdas.md) — closures that can appear as ITE conditions.*
