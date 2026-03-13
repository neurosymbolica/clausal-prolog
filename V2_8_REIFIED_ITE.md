# V2-8 — Reified If-Then-Else (Pure Monotonic Branching)

**Status:** Planning
**Depends on:** V2-7 (WFS), V2-5 (dif/2), V2-6 (CLP(FD))
**Replaces:** The committed-choice `(->)/2` design previously in ROADMAP_V2.md

## Motivation

The original V2-8 plan compiled Python's ternary `if` as Prolog's committed-choice
`( Cond -> Then ; Else )`. We're abandoning that in favour of **reified conditionals**
based on Neumerkel & Kral's `if_/3` (["Indexing dif/2", arXiv:1607.01590][paper]).

**Why no committed-choice:**

- `(->)/2` is `once(Cond) -> Then ; Else` — it commits to the first solution of Cond
  and discards all alternatives. This is non-monotonic: adding constraints can lose
  solutions.
- `memberchk(X, [1,2]), X = 2` fails unexpectedly (paper §3). Goal reordering changes
  answers. This is exactly the kind of footgun we don't want in Clausal.
- Even "soft cut" `(*->)/2` has the same soundness problems as unsound negation (paper §2).
- Clausal already has no `!/0` (cut). Introducing committed-choice would be adding a
  less-visible version of the same problem.

**Why reified if_/3:**

- Monotonic: adding constraints can only restrict, never lose solutions.
- Deterministic where impure versions are: `memberd(1, [1,2,3])` → `true.` with no
  leftover choicepoint (paper §6).
- Sound under goal reordering.
- Fits naturally with Clausal's existing `dif/2` and CLP(FD) constraints.
- The paper shows expanded `if_/3` achieves 1.5-3x of impure `memberchk/2` on SICStus
  (Table 1). Good enough, and correct.

[paper]: https://arxiv.org/abs/1607.01590

---

## Core Insight: Reification

Traditional Prolog goals **succeed or fail** — the outcome is implicit in the execution
model. You can't store "the result of whether X = Y" and branch on it later.

**Reification** makes the outcome explicit as a data value (`true`/`false`). A reified
predicate always succeeds and produces a truth value:

```prolog
% Neumerkel's (=)/3 — reified equality (paper §5, Appendix):
=(X, Y, T) :-
    ( X == Y -> T = true      % already identical → deterministic
    ; X \= Y -> T = false     % not unifiable → deterministic
    ; T = true, X = Y         % undetermined → explore both via backtracking
    ; T = false, dif(X, Y)
    ).
```

The first two branches are **decidable ground checks** — `==` and `\=` always terminate
with a definite answer. The `(->)/2` there is harmless because it tests something
already fully determined. The real work is in branches 3 and 4: when the relationship
between X and Y is **undetermined**, ordinary backtracking explores both possibilities,
attaching the right constraints in each case.

This means `(=)/3` doesn't need general committed-choice — it needs:
1. Deterministic ground identity/non-unifiability checks (Python `is` / match-case)
2. Ordinary disjunction (Clausal's `or`)
3. `dif/2` constraints (V2-5, already done)

**`if_/3`** then branches on the ground truth value:

```prolog
if_(If_1, Then_0, Else_0) :-
    call(If_1, T),
    ( T == true  -> call(Then_0)    % ground match — harmless
    ; T == false -> call(Else_0)
    ; nonvar(T)  -> throw(type_error)
    ; throw(instantiation_error)
    ).
```

Again, the `(->)/2` inside `if_/3` only tests the **ground atom** T. There's nothing to
cut away. In Clausal, this is just `match T: case True: ... case False: ...`.

---

## Design for Clausal

### Phase A: Reified Equality and Core if_/3 (compiler-expanded)

No lambdas or `call/N` needed. The compiler recognizes built-in reifiable conditions
and generates the four-branch reification inline.

#### A.1: `reify_eq(x, y, trail)` — Reified Equality

New function in `clausal/logic/constraints.py` (alongside `dif`):

```python
def reify_eq(x: Any, y: Any, trail: Trail) -> bool | None:
    """Reified equality: returns True, False, or None (undetermined).

    - True:  x and y are already identical (no bindings needed)
    - False: x and y are structurally incompatible (cannot unify)
    - None:  undetermined — unification possible but requires bindings
    """
    x = deref(x)
    y = deref(y)

    # Fast path: identical objects (includes same Var)
    if x is y:
        return True

    # Ground non-unifiability check
    mark = trail.mark()
    unified = _structural_unify_oc(x, y, trail)
    trail_grew = (len(trail) != mark) if unified else False
    trail.undo(mark)

    if not unified:
        return False        # structurally incompatible
    if not trail_grew:
        return True         # ground-equal, no bindings needed
    return None             # undetermined — needs exploration
```

This is the decision procedure that `(=)/3`'s first two branches implement. The
undetermined case is handled by the caller (the compiler-generated code).

#### A.2: Compiler-expanded `If(cond, then, else)` for reifiable conditions

When the compiler sees `IfExpr(test=Unify(X, Y), body=then, orelse=else)` — i.e.
the condition is `X_ is Y_` (equality) — it generates inline reified code:

```python
# If(X_ is Y_, then_goal, else_goal) compiles to:

_reif = _reify_eq(X_, Y_, trail)         # True / False / None
if _reif is True:                         # already identical
    <compiled then_goal with k_stmts>
elif _reif is False:                      # structurally incompatible
    <compiled else_goal with k_stmts>
else:                                     # undetermined → explore both
    _m = trail.mark()
    if unify(X_, Y_, trail):              # T = true, X = Y
        <compiled then_goal with k_stmts>
    trail.undo(_m)
    if _dif(X_, Y_, trail):              # T = false, dif(X, Y)
        <compiled else_goal with k_stmts>
    trail.undo(_m)                        # (dif doesn't need undo, but clean)
```

**This is a direct translation of Neumerkel's `(=)/3` + `if_/3`, expanded inline.**
No higher-order calls. No committed choice. The `else` in the undetermined branch
explores both possibilities via backtracking — exactly like the paper's 3rd and 4th
clauses of `(=)/3`.

#### A.3: Reifiable condition registry

The compiler needs to know which conditions can be reified. Initial set:

| Condition syntax | Reified via | Notes |
|---|---|---|
| `X_ is Y_` (Unify) | `reify_eq` + `unify`/`dif` | Paper's `(=)/3` |
| `X_ is not Y_` (DoesNotUnify) | `reify_eq` (inverted) | Paper's `dif/3` |
| `X_ == Y_` (StructuralEq) | CLP(FD) reify | Three outcomes: ground-true, ground-false, constrain |
| `X_ != Y_` (StructuralNeq) | CLP(FD) reify (inverted) | Same |
| `X_ < Y_`, etc. | CLP(FD) reify | Same pattern |

For non-reifiable conditions (arbitrary predicate calls), see Phase A.4.

#### A.4: Non-reifiable conditions — WFS-backed fallback

When the condition is an arbitrary goal (e.g. `If(father(X_), then, else)`), the
compiler can't reify it automatically. Two options:

**Option 1: Exhaustive exploration (sound but potentially expensive)**

```python
# If(some_goal, then_goal, else_goal) with non-reifiable condition:

_m = trail.mark()
_found = False
def _if_cond():
    <compiled some_goal with k_stmts = [yield None]>
    return; yield

for _ in _if_cond():
    _found = True
    # DON'T break — but we only need one solution for the "true" path
    <compiled then_goal with k_stmts>
trail.undo(_m)

# Now explore the "false" path via NAF
_m2 = trail.mark()
_naf_flag = True
for _ in _if_cond():
    _naf_flag = False
    break
trail.undo(_m2)
if _naf_flag:
    <compiled else_goal with k_stmts>
```

This is sound but explores the condition twice. For the common case where the
condition is deterministic (one solution or none), this is fine.

**Option 2: Committed-choice fallback (pragmatic, clearly marked)**

For users who explicitly want first-solution commitment for performance, provide
`once()` as a builtin. Then `If(once(goal), then, else)` is the explicit "I know
what I'm doing" escape hatch.

**Recommendation:** Start with Option 1 (sound). Add `once()` later if needed.
The compiler could optimise specific patterns (e.g., ground conditions → no
double-evaluation).

#### A.5: No 2-arg form

`If` always requires three arguments: `If(cond, then, else)`. There is no 2-arg
`If(cond, then)` — that would just be conjunction (`cond and then`), which doesn't
involve reification and can be written directly.

#### A.6: `IfExpr` node reuse

The existing `IfExpr(test, body, orelse)` AST node works perfectly. No new node
needed. The compiler adds a case for `IfExpr` in `compile_goal`:

```python
case IfExpr(test=test, body=then, orelse=else_):
    if else_ is None:
        # If without else → conjunction
        return compile_goal(And(left=test, right=then), db, var_context, trail_name, k_stmts)
    if _is_reifiable(test):
        return _compile_reified_ite(test, then, else_, db, var_context, trail_name, k_stmts)
    else:
        return _compile_general_ite(test, then, else_, db, var_context, trail_name, k_stmts)
```

---

### Phase B: Reified Builtins Library

Once Phase A works, ship reified versions of common predicates as builtins.

#### B.1: `eq/3` — Reified equality (user-callable)

```python
# In clausal/logic/reif.py (new file):
def eq(x, y, t, trail):
    """Reified equality: eq(X_, Y_, T_) — T_ is True if X_=Y_, False if dif(X_,Y_)."""
    result = reify_eq(x, y, trail)
    if result is True:
        return unify(t, True, trail)
    elif result is False:
        return unify(t, False, trail)
    else:
        # Undetermined: explore both
        # ... (generator that yields for T=True,X=Y and T=False,dif(X,Y))
```

Register as builtin `eq/3`. This is Neumerkel's `(=)/3`.

#### B.2: `dif_t/3` — Reified disequality

Inverse of `eq/3`. `dif_t(X_, Y_, T_)` — T_ is True if dif(X_,Y_), False if X_=Y_.

#### B.3: `memberd_t/3` — Reified membership

From the paper §7:

```
memberd_t(X_, Es_, T_) <- l_memberd_t(Es_, X_, T_)

l_memberd_t([], _, False),
l_memberd_t([E_ | Es_], X_, T_) <- If(X_ is E_, T_ is True, l_memberd_t(Es_, X_, T_))
```

This is a `.clausal` file, not a builtin — it exercises Phase A's `If` compilation.

#### B.4: Reified connectives

```python
# Reified conjunction: and_t(A_1, B_1, T)
# and_t(A, B, T) :- if_(A, call(B, T), T = false).

# Reified disjunction: or_t(A_1, B_1, T)
# or_t(A, B, T) :- if_(A, T = true, call(B, T)).
```

These depend on `call/N` (V2-9). Defer to Phase C.

---

### Phase C: General `if_/3` (post-V2-9)

Once lambdas and `call/N` exist (V2-9), implement the full `if_/3` as a library
predicate. Users can write their own `_t` reified predicates and use them as
conditions:

```python
# In a .clausal file:
memberd(X_, [E_ | Es_]) <- if_(X_ >> lambda T_: eq(X_, E_, T_),
                                True,
                                memberd(X_, Es_))
```

The `_t` suffix convention: a predicate whose last argument is a reified truth value.

Also ship:
- `tfilter/3` — filter with reified condition
- `tpartition/4` — partition with reified condition
- `tmember/2` — select elements satisfying reified condition

---

## Implementation Layers

The reified ITE has two distinct parts with different implementation constraints:

**Part 1: The three-way decision** — "are these terms identical, incompatible, or
undetermined?" Pure computation: `deref` both sides, sandbox-unify, check trail
growth, undo. No goal execution, no backtracking, no continuation passing.

**Part 2: The branching** — "given the decision, execute then/else/explore-both."
Involves executing goal terms as continuations with backtracking.

### Why this layering matters

Part 1 is a **runtime function** — it can be a C extension, a Python function, or
both (C with Python fallback). It takes data in and returns a three-valued result.
Same calling convention as `unify()` or `dif()`.

Part 2 **must be compiler-inlined**. Clausal compiles goals via continuation-passing:
`k_stmts` is a list of AST statements, not a callable. The then/else branches
aren't first-class objects — they're code that gets spliced into the generated
function. This is the same reason `Not`, `Or`, and `And` are all compiler-inlined
rather than runtime functions.

Full `if_/3` as a user-callable predicate (where Then/Else are passed as goal
arguments) requires `call/N` and goal closures (V2-9). That's Phase C.

| Component | Implementation level | Why |
|---|---|---|
| `reify_eq(x, y, trail) → True/False/None` | **C extension** (+ Python fallback) | Hot path, pure computation, all primitives already in C |
| `reify_dif(x, y, trail) → True/False/None` | **C extension** (+ Python fallback) | Same — just inverted result |
| `reify_fd(op, x, y, trail) → True/False/None` | **Python** in `clpfd.py` | FD domain checks are Python-level already |
| Three-way branch + undetermined exploration | **Compiler-inlined** | Goals are continuation-passed AST, not callables |
| Full `if_/3(Cond_1, Then_0, Else_0)` | **Python builtin** (Phase C) | Needs `call/N` from V2-9 |

---

## Implementation Plan

### Phase A — Reification primitives + compiler-expanded ITE

#### Step 1: `reify_eq` — C extension with Python fallback

**C extension** (`clausal/logic/variables/_variables.c` or new `_reif.c`):

```c
/* reify_eq(x, y, trail) → True / False / None
 *
 * All operations already exist in C:
 *   - deref()        — follow Var chain
 *   - trail.mark()   — snapshot trail length
 *   - unify()        — structural unification (or unify_with_occurs_check)
 *   - trail.undo()   — restore to snapshot
 *   - trail length   — check for growth
 *
 * Algorithm:
 *   1. deref both sides
 *   2. if x is y → return True (identity)
 *   3. mark = trail.mark()
 *   4. unified = structural_unify(x, y, trail)
 *   5. grew = (trail.length != mark) if unified else false
 *   6. trail.undo(mark)
 *   7. if !unified → return False (incompatible)
 *   8. if !grew   → return True  (ground-equal)
 *   9. return None (undetermined)
 */
```

This is a single C function that calls existing C primitives. The sandbox
unify+undo pattern is the same one `dif()` already uses in Python — moving it
to C eliminates the Python overhead on every reified conditional.

**Python fallback** (`clausal/logic/constraints.py`):

```python
def reify_eq(x: Any, y: Any, trail: Trail) -> bool | None:
    x, y = deref(x), deref(y)
    if x is y:
        return True
    mark = trail.mark()
    unified = _structural_unify_oc(x, y, trail)
    grew = (len(trail) != mark) if unified else False
    trail.undo(mark)
    if not unified:
        return False
    if not grew:
        return True
    return None
```

**Import pattern** (same as `Var`/`unify`/`deref`):
```python
try:
    from clausal.logic.variables._variables import reify_eq
except ImportError:
    from clausal.logic.constraints import reify_eq  # pure-Python fallback
```

**Note on `_structural_unify_oc` in C:** The existing C `unify` falls through to
`==` for Compound/PredicateMeta, which is why `_structural_unify_oc` exists in
Python. For `reify_eq` in C, we need structural recursion in C too. Options:
1. Use the Python `_structural_unify_oc` for the fallback, C `unify` for the
   extension (slightly less precise for nested Compound, but correct for the
   common cases: scalars, Vars, tuples, lists)
2. Port `_structural_unify_oc` to C (more work, full correctness)
3. Call back into Python's `_structural_unify_oc` from C (ugly but works)

**Recommendation:** Start with option 1 — C `unify` handles the vast majority of
cases correctly (Var-Var, Var-scalar, scalar-scalar, list, tuple). The Python
fallback handles Compound/PredicateMeta edge cases. Port to C later if profiling
shows it matters.

#### Step 2: `_compile_reified_ite` in compiler.py (simple mode)

New function `_compile_reified_ite(test, then, else_, db, var_context, trail_name, k_stmts)`.

For `test = Unify(left, right)` (the equality case):

```
Generated code structure:

_reif_N = _reify_eq(<left_expr>, <right_expr>, trail)
if _reif_N is True:
    <compiled then with k_stmts>
elif _reif_N is False:
    <compiled else with k_stmts>
else:
    _m_N = trail.mark()
    if unify(<left_expr>, <right_expr>, trail):
        <compiled then with k_stmts>
    trail.undo(_m_N)
    if _dif(<left_expr>, <right_expr>, trail):
        <compiled else with k_stmts>
    trail.undo(_m_N)
```

The three branches map directly to Neumerkel's `(=)/3`:
- `True` → paper's `X == Y -> T = true` (already identical, deterministic)
- `False` → paper's `X \= Y -> T = false` (not unifiable, deterministic)
- `None` → paper's 3rd+4th clauses (undetermined, explore both with backtracking)

For `test = DoesNotUnify(left, right)` (dif case): same structure but swap
then/else in the True/False branches (reified dif is the inverse of reified eq).

Inject `_reify_eq` into `base_globals`.

#### Step 3: `_compile_general_ite` in compiler.py (simple mode)

For non-reifiable conditions (arbitrary predicate calls). Uses the sub-generator
+ NAF pattern from Phase A.4 Option 1.

```
Generated code structure:

# "True" path: run condition, on each solution run then
_m_N = trail.mark()
def _if_cond_N():
    <compiled test with k_stmts = [yield None]>
    return; yield
for _ in _if_cond_N():
    <compiled then with k_stmts>
trail.undo(_m_N)

# "False" path: NAF of condition → run else
_m2_N = trail.mark()
_naf_N = True
for _ in _if_cond_N():
    _naf_N = False
    break
trail.undo(_m2_N)
if _naf_N:
    <compiled else with k_stmts>
```

This is sound — explores the condition twice. For the common case where the
condition is deterministic (one solution or none), the cost is negligible.

**Tabled conditions:** If the condition is a call to a tabled predicate
(`_is_tabled_naf` check), the "false" path should use `_naf_tabled` instead of
inline NAF. Same logic as existing tabled NAF in `Not` compilation.

#### Step 4: Wire into compile_goal dispatch

Add `case IfExpr(...)` to `compile_goal` (simple mode) after the `Not` case:

```python
case IfExpr(test=test, body=then, orelse=else_):
    if _is_reifiable(test):
        return _compile_reified_ite(test, then, else_, ...)
    else:
        return _compile_general_ite(test, then, else_, ...)
```

`_is_reifiable(test)` checks if `test` is `Unify`, `DoesNotUnify`, `StructuralEq`,
`StructuralNeq`, `Lt`, `LtE`, `Gt`, or `GtE`.

#### Step 5: Trampoline mode

Mirror Steps 2-4 for `compile_goal_trampoline`. The condition sub-generator is
always simple mode (same pattern as NAF in trampoline). Then/else branches
compile in trampoline mode with normal `k_stmts`.

#### Step 6: Inject into base_globals

Add `_reify_eq` to both simple and trampoline `base_globals` dicts. Same
injection pattern as `_dif`, `_fd_eq`, etc.

#### Step 7: CLP(FD) reification

Extend `_compile_reified_ite` to handle `StructuralEq`, `Lt`, `LtE`, `Gt`, `GtE`.

New function `reify_fd(op, x, y, trail) -> bool | None` in `clpfd.py`:

```python
def reify_fd(op: str, x: Any, y: Any, trail: Trail) -> bool | None:
    """Reified FD comparison.

    op is one of "eq", "ne", "lt", "le", "gt", "ge".
    Returns True (ground-satisfies), False (ground-violates), None (has FD vars).
    """
    x, y = deref(x), deref(y)
    x_ground = not is_var(x) and not _has_fd(x)
    y_ground = not is_var(y) and not _has_fd(y)
    if x_ground and y_ground:
        x_val, y_val = _resolve(x), _resolve(y)
        return _PYTHON_OPS[op](x_val, y_val)  # deterministic
    return None  # has vars or FD vars → undetermined
```

The undetermined branch posts the FD constraint (via existing `_fd_eq`/`_fd_lt`/etc.)
for the then path, and posts the negated constraint for the else path. Both
branches explored via backtracking.

Stays in Python — FD domain operations are already Python-level. No C extension
needed here.

#### Step 8: Tests (`tests/test_reified_ite.py`)

Core tests (~25):

**`reify_eq` unit tests:**
- identical Var → True
- ground equal (1, 1) → True
- ground incompatible (1, 2) → False
- undetermined (Var, 1) → None
- Compound: same functor/args → True, different → False
- PredicateMeta: same type/fields → True, different → False
- nested undetermined: Compound with Var inside → None

**Reified ITE with equality condition:**
- ground true: `If(1 is 1, then, else)` → then path
- ground false: `If(1 is 2, then, else)` → else path
- undetermined: `If(X_ is 1, then, else)` → explores both branches
- undetermined produces correct bindings: then has X_=1, else has dif(X_,1)

**Reified ITE with dif condition:**
- ground dif true: `If(1 is not 2, then, else)` → then path
- ground dif false: `If(1 is not 1, then, else)` → else path
- undetermined dif

**General ITE with predicate call:**
- deterministic predicate: `If(member(1, [1,2]), then, else)` → then
- failing predicate: `If(member(3, [1,2]), then, else)` → else
- multi-solution predicate: runs then for each solution

**Control flow:**
- ITE without else (orelse=None → conjunction)
- nested ITE: `If(c1, If(c2, a, b), c)`
- ITE preserves bindings in then path, undoes in else path

**Integration:**
- simple and trampoline modes both work
- `memberd` using ITE: deterministic for ground cases (the paper's key example)
- ITE + dif/2 constraints interact correctly
- ITE + CLP(FD) constraints interact correctly
- `.clausal` file with ITE imported and queried

---

## What This Replaces in the Roadmap

| Old V2-8 | New V2-8 |
|---|---|
| Committed-choice `(->)/2` semantics | Reified `if_/3` semantics |
| Python ternary `x if c else y` as primary syntax | `If(cond, then, else)` as canonical goal node |
| No consideration of undetermined case | Three-valued: true/false/undetermined |
| `once(Cond)` implicit in the semantics | No implicit commitment; `once()` is explicit |
| Single compilation path | Reifiable fast-path + general fallback |

**V2-9 (lambdas) dependency is removed for Phase A.** The compiler expands known
reifiable conditions inline — no `call/N` needed.

**V2-9 remains needed for Phase C** (general `if_/3` as a user-callable predicate
with arbitrary reified conditions via `call/N`).

---

## Syntax Decision

We considered Python's ternary if-expression (`then if cond else else_`) but
rejected it:

1. **Backwards reading order**: Then-Cond-Else vs natural Cond-Then-Else
2. **Nesting is unreadable**: `a if x else (b if y else c)`
3. **Expression semantics mismatch**: ternary returns values, not controls flow

**Decision:** `If(cond, then, else)` as a callable goal constructor — Cond-Then-Else
order, clean nesting, explicit.

The `IfExpr` AST node is reused internally. The `TermTransformer` rejects Python
ternary syntax with a `SyntaxError` directing users to `If(...)` instead.

**Question for later**: Do we want `If` as a user-facing name imported from `clausal`,
or do we keep it compiler-internal and only expose it through `.clausal` file syntax
(where TermTransformer produces IfExpr nodes)? Suggest: expose `If` from `clausal`
for the Python API, keep IfExpr internal.

---

## Key Design Invariants

**Invariant 1: Undetermined conditions explore both branches with correct
constraints.** When `reify_eq` returns `None` (undetermined), the generated code
MUST explore both the true path (with `unify(X, Y)` in effect) AND the false
path (with `dif(X, Y)` in effect), via backtracking. This is the core property
from Neumerkel's `(=)/3` — it's what makes queries work in all modes (ground,
partial, unbound) and what eliminates leftover choicepoints for ground cases.
Losing this property (e.g. by only exploring one branch, or by not attaching
the right constraints) would defeat the entire purpose of reification.

The same invariant applies to CLP(FD) reification: undetermined FD comparisons
must explore both the satisfying and violating branches with appropriate domain
constraints posted in each.

**Invariant 2: No committed-choice anywhere in Clausal.** The reified approach means:

- Built-in reifiable conditions get the fast three-way check (deterministic for
  ground cases, exploration for undetermined)
- Arbitrary conditions get double-evaluation (sound NAF-based)
- Users who want first-solution commitment use `once()` explicitly
- The `_t` convention (Phase C) lets users write efficient reified predicates

This is the pure path from the start. No `(->)/2` to deprecate later.

---

## Files Modified/Created

### Phase A

| File | Change |
|---|---|
| `clausal/logic/variables/_variables.c` | Add `reify_eq()` C implementation (or new `_reif.c`) |
| `clausal/logic/constraints.py` | Add `reify_eq()` Python fallback |
| `clausal/logic/variables/__init__.py` | Export `reify_eq` (C-first, Python fallback) |
| `clausal/logic/compiler.py` | Add `IfExpr` case to `compile_goal` + `compile_goal_trampoline`; add `_compile_reified_ite`, `_compile_general_ite` and trampoline variants; add `_is_reifiable()`; inject `_reify_eq` into `base_globals` |
| `clausal/logic/clpfd.py` | Add `reify_fd()` for CLP(FD) three-way check |
| `tests/test_reified_ite.py` (new) | ~25 tests |
| `tests/fixtures/reified_memberd.clausal` (new) | `memberd` using `If` — integration test |
| `ROADMAP_V2.md` | Update V2-8 section |

### Phase B

| File | Change |
|---|---|
| `clausal/logic/reif.py` (new) | `eq/3`, `dif_t/3` as generator-based builtins |
| `clausal/logic/builtins.py` | Register `eq/3`, `dif_t/3` in `_BUILTINS` |
| `clausal/stdlib/reif.clausal` (new) | `memberd_t/3`, `l_memberd_t/3` in Clausal |

### Phase C (post V2-9)

| File | Change |
|---|---|
| `clausal/logic/builtins.py` | Register `if_/3` as builtin |
| `clausal/stdlib/reif.clausal` | Add `tfilter/3`, `tpartition/4`, `tmember/2` |

---

## Open Questions

1. **CLP(FD) reification (Step 8)**: How far do we go? Just equality/inequality, or
   all comparison operators? The pattern is the same for all — check ground, then
   explore both with constraints. Suggest: do them all in Phase A since the pattern
   is uniform.

2. **General ITE double-evaluation cost**: For non-reifiable conditions, we evaluate
   the condition twice (once for true path, once for NAF). This is correct but
   potentially expensive. Optimisation: cache the first evaluation's result? Or just
   document the cost and point users toward writing `_t` predicates for hot paths.

3. **`once()` builtin**: Should we ship this in Phase A as the explicit commitment
   escape hatch? It's trivial to implement (sub-generator + break after first yield).
   Suggest: yes, it's useful independent of ITE and good to have.

4. **WFS interaction**: For tabled predicates as ITE conditions, should the "false"
   path use `_naf_tabled` instead of inline NAF? Probably yes — same logic as the
   existing tabled NAF in `Not` compilation.
