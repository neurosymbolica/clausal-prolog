# CLP(Q) implementation issues

Known doubts, inconsistencies, incomplete features, and potential improvements
in the CLP(Q) implementation (`clausal/logic/clpq.py` and supporting files).

---

## 1. `q_ne` is a stub for non-ground cases

**Severity:** functional gap

`q_ne` (`clpq.py:1001-1026`) correctly handles ground-ground disequalities but
does almost nothing for non-ground cases.  The code has a partial attempt to
store disequality pairs in `tableau.diseqs` but the key section is a `pass`
statement:

```python
if len(l_vars) == 1 and not r_vars:
    vid = next(iter(l_vars))
    if len(rk) == 0:
        tableau = _get_tableau(trail)
        _snapshot_tableau(trail)
        # Store disequality between vid and a value
        # For simplicity, store as pair and check later
        pass
```

**Consequence:** `q_lt(X, 5)` (which is `q_le + q_ne`) posts the inequality
but silently drops the disequality.  If the simplex later pins X to exactly 5,
this should fail but won't.

**Fix:** implement proper disequality storage in the Tableau.  For single-var
disequalities `X != c`, store `(var_id, value)` pairs.  For two-var `X != Y`,
store `(var_id_x, var_id_y)`.  Check these in `_check_diseqs` and in
`check_implied_bindings` when a variable becomes ground.

---

## 2. `_tableaux` dict leaks memory

**Severity:** resource leak (minor in practice)

`_tableaux` (`clpq.py:715`) is a module-level `dict[int, Tableau]` keyed by
`id(trail)`.  When a Trail object is garbage collected, its `id()` can be
reused by a new Trail, but the old Tableau entry is never removed.

In practice, Trails are long-lived (one per search context) and few in number,
so this rarely matters.  But in a long-running server or test suite that creates
many Trails, old entries accumulate.

**Fix:** use `weakref.ref(trail, cleanup_callback)` if Trail supports weak
references, or add explicit cleanup when a trail is destroyed.  Alternatively,
store the Tableau as an attribute on the Trail object itself (requires Trail API
extension).

---

## 3. Dual simplex `_restore_feasibility` has a confused entering-variable selection

**Severity:** correctness risk for complex multi-variable inequality systems

The `_restore_feasibility` method (`clpq.py:463-547`) has overly complicated
logic for choosing the entering variable.  The comments contradict the code in
places:

```python
# Simplified Bland's: pick first var with negative coeff
# (we'll pivot and the leaving var takes the entering's bound).
# Actually: for dual simplex below-lower-bound, the standard
# rule is to find entering with NEGATIVE coefficient (the
# ratio test is inverted in dual simplex).
# Let's try a simpler approach: just update the non-basic
# variable's bound directly.
```

The code then does something different from all three of these comments: it
checks both positive and negative coefficients with conditional bound checks.
This works for the tested cases but is not the standard dual simplex algorithm
and may produce incorrect results for degenerate systems or systems where
non-basic variables are at upper bounds rather than lower bounds.

**Fix:** implement the textbook dual simplex entering-variable rule: for a
below-lower-bound violation, compute the dual ratio for each non-basic variable
and pick the one with the smallest (most negative) ratio.  Apply Bland's rule
for tie-breaking.

---

## 4. `_snapshot_tableau` is called too often

**Severity:** performance

Every call to `q_eq`, `q_le`, `q_ne`, `_post_q_domain`, and `_q_hook` calls
`_snapshot_tableau`, which deep-copies the entire Tableau.  When a single
logical step triggers multiple internal operations (e.g., `q_eq` calls
`add_equality` which calls `_propagate_determined` which triggers
`check_implied_bindings` which calls `unify` which triggers `_q_hook` which
calls `_snapshot_tableau` again), the Tableau may be copied multiple times for
what should be a single undo step.

**Fix:** track whether a snapshot has already been taken for the current trail
mark.  Only copy if no snapshot exists since the last `trail.mark()`.
Alternatively, snapshot at the public API boundary only (in `q_eq`, `q_le`,
etc.) and not inside the hook.

---

## 5. `optimize` does not bind the variables to their optimal values

**Severity:** functional gap

After `maximize(30*X + 50*Y, OBJ)`, OBJ is bound to 310 but X and Y remain
unbound.  The SICStus `maximize/1` predicate binds the objective *and* all
constrained variables to their optimal values.

Currently the Tableau's `assign` dict holds the optimal assignments after
`optimize`, but these are never propagated back to the logic variables.

**Fix:** after `optimize` returns, iterate `_var_map` and `unify` each variable
with its assignment from the optimal solution.  This must be done carefully to
avoid infinite recursion (the hook calls `fix_variable` which modifies the
Tableau that `optimize` just computed).

---

## 6. No projection (Fourier-Motzkin elimination)

**Severity:** missing feature

There is no `dump_q` or constraint projection.  When a Q-constrained variable
is printed at the top level, the user sees the raw `QVar` attribute rather than
a human-readable constraint representation like `{X + Y =< 10}`.

This is the exact bug that plagues SWI-Prolog's CLP(Q) (internal variables
leak into answers).

**Fix:** implement Fourier-Motzkin elimination to project away internal
variables.  This is complex but essential for usability.  Defer to a later
phase.

---

## 7. `_is_rational_arg` walks expression trees — performance concern

**Severity:** performance (minor)

`_is_rational_arg` (`clpfd.py:1149`) was fixed to walk inside expression trees
to detect Q-declared variables.  This is correct but means every `fd_eq` call
with an expression tree recurses into the tree before deciding whether to
dispatch to CLP(Q).  For pure CLP(Z) programs with expression trees, this adds
overhead.

**Fix:** cache the result per-expression, or check only the top-level types and
fall back to CLP(Q) dispatch inside the CLP(Z) linearization path if a
Q-variable is encountered.

---

## 8. `_eval_ground` import of `Fraction` on every call

**Severity:** performance (minor)

`_eval_ground` (`clpfd.py:961`) now imports `Fraction` at the top of the
function body.  This is a module-level `from fractions import Fraction` on every
call.  Python caches module imports so the cost is minimal, but it would be
cleaner to import once at module level or use a cached local.

**Fix:** move the import to module level or use the existing `_Fraction` pattern.

---

## 9. `float` bound_to in `_q_hook` is rejected

**Severity:** design decision (may need revisiting)

When a Q-constrained variable is unified with a float (e.g., via CLP(R)
interaction), the `_q_hook` (`clpq.py:903-941`) falls through to `return False`
because there's no `isinstance(bound_to, float)` branch.

This means mixing CLP(Q) and CLP(R) on the same variable silently fails.
Whether this is correct depends on the desired semantics: SICStus raises a type
error for Q/R mixing.

**Fix:** either add an explicit `float` branch that converts via
`Fraction.from_float()` (lossy but pragmatic), or raise a clear `TypeError`
explaining that Q and R domains cannot be mixed on the same variable.

---

## 10. `maximize`/`minimize` mutate the Tableau without snapshotting

**Severity:** correctness risk

`maximize` and `minimize` (`clpq.py:1076-1103`) call `tableau.optimize` which
mutates `self.assign` (and potentially pivots rows) to find the optimal
solution.  This mutation is not snapshotted.

If the user calls `maximize` inside a branch that later backtracks, the Tableau
is restored to the pre-`maximize` state via the snapshot taken by the enclosing
`q_le` call, so this is usually safe.  But if `maximize` is called without any
preceding constraint in the same trail segment, there's no snapshot to restore.

**Fix:** add `_snapshot_tableau(trail)` at the top of `maximize` and `minimize`.

---

## 11. No `entailed/1` or `sup/1`/`inf/1` predicates

**Severity:** missing feature

SICStus CLP(Q) provides `entailed(Constraint)` to test whether a constraint is
logically implied by the current store, and `sup(Expr, Sup)` / `inf(Expr, Inf)`
to compute bounds without committing to the optimum.  These are not implemented.

**Fix:** `sup`/`inf` can be implemented by calling `optimize` on a copy of the
Tableau (to avoid mutating the working copy).  `entailed` requires checking
whether the negation of the constraint is infeasible.

---

## 12. No `bb_inf` (branch-and-bound for mixed-integer)

**Severity:** missing feature

SICStus provides `bb_inf(Ints, Expr, Inf)` for mixed-integer optimization
(rational LP relaxation + branch-and-bound on integer variables).  This is not
implemented.

**Fix:** implement as a meta-predicate that calls `optimize` at each node and
branches on the fractional integer variable closest to 0.5.

---

## 13. Pivot always puts leaving variable at lower bound

**Severity:** correctness risk

In `_pivot` (`clpq.py:409-459`), the leaving variable is always set to its
lower bound after the pivot:

```python
lo = self.lo.get(leaving)
if lo is not None:
    self.assign[leaving] = lo
else:
    self.assign[leaving] = ZERO
```

This is correct for the primal simplex (where the leaving variable hits its
lower bound), but in the dual simplex the leaving variable may need to be set to
its upper bound (when it was above its upper bound).  The
`_restore_feasibility` method sets `self.assign[leaving]` before calling
`_pivot`, but `_pivot` then overwrites it.

**Fix:** pass the target bound to `_pivot` as a parameter, or have `_pivot`
check which bound was violated and set accordingly.

---

## 14. C extension `_any_rational` dispatch does not walk expression trees

**Severity:** correctness gap (partially mitigated)

The C extension (`_clpfd_propagate.c`) calls the Python `_any_rational` function
which now walks expression trees.  However, the C `fd_eq` may take the
linearization fast path before reaching the `_any_rational` check in some code
paths.  The Python fallback `fd_eq` has the rational check in the right place,
so this only affects the C-accelerated path.

**Fix:** verify that the C `fd_eq` always calls `_any_rational` before
attempting CLP(Z) linearization.  If not, reorder the C dispatch.

---

---

# Phased remediation plan

## Effort estimates

| # | Issue | Effort | Risk if deferred |
|---|---|---|---|
| 10 | `maximize`/`minimize` missing snapshot | 5 min | High — silent corruption on backtrack |
| 8 | `Fraction` import in hot path | 5 min | None — pure cleanup |
| 13 | Pivot always targets lower bound | 15 min | High — wrong answers on upper-bound dual pivots |
| 3 | Dual simplex entering-variable rule | 1-2 hr | High — wrong answers on complex inequality systems |
| 1 | `q_ne` stub | 30 min | Medium — strict inequalities silently unsound |
| 9 | `float` in Q hook rejected silently | 10 min | Medium — confusing silent failure |
| 5 | `optimize` doesn't bind variables | 30 min | Medium — user surprise, differs from SICStus |
| 4 | Redundant tableau snapshots | 30 min | None — performance only |
| 2 | `_tableaux` memory leak | 20 min | Low — only matters for long-running processes |
| 7 | `_is_rational_arg` tree walk overhead | 20 min | Low — only matters for large CLP(Z) expression trees |
| 14 | C extension dispatch ordering | 30 min | Low — Python fallback covers it |
| 11 | No `entailed`/`sup`/`inf` | 2-3 hr | None — missing feature, not broken |
| 6 | No projection (Fourier-Motzkin) | 4-6 hr | None — missing feature, not broken |
| 12 | No `bb_inf` | 3-4 hr | None — missing feature, not broken |

---

## Phase A: correctness fixes (must-do before any production use)

**Estimated total: 2-3 hours**

These issues can produce wrong answers or corrupt state. Fix all of them before
advertising CLP(Q) as usable.

### A1. Snapshot `maximize`/`minimize` (#10) — 5 min

Add `_snapshot_tableau(trail)` as the first line of both `maximize` and
`minimize`.  Trivial, zero risk.

```python
def maximize(expr, result_var, trail):
    ...
    tableau = _get_tableau(trail)
    _snapshot_tableau(trail)          # ADD THIS
    opt = tableau.optimize(coeffs, 'max')
```

Test: call `maximize` inside a branch, backtrack, verify tableau is restored.

### A2. Fix pivot bound direction (#13) — 15 min

Add a `leaving_bound` parameter to `_pivot`:

```python
def _pivot(self, leaving, entering, leaving_bound=None):
    ...
    # At end:
    if leaving_bound is not None:
        self.assign[leaving] = leaving_bound
    elif lo is not None:
        self.assign[leaving] = lo
    else:
        self.assign[leaving] = ZERO
```

Update `_restore_feasibility` to pass the correct bound:
- Below lower → `leaving_bound = lo`
- Above upper → `leaving_bound = hi`

Update `optimize` to always pass `leaving_bound = lo` (primal simplex).

Test: construct a system where a non-basic variable is at its upper bound and
a dual pivot must set the leaving var to its upper bound.

### A3. Rewrite dual simplex (#3) — 1-2 hr

Replace the current `_restore_feasibility` with the textbook dual simplex:

```
while any basic variable violates its bounds:
    leaving = most infeasible basic variable
    if leaving < lo:  direction = +1 (need to increase)
    else:             direction = -1 (need to decrease)

    # Dual ratio test: for each non-basic var j in the leaving row
    #   if direction * row[leaving][j] < 0:
    #     ratio_j = obj_reduced_cost[j] / row[leaving][j]
    #   pick j with largest (least negative) ratio (Bland's for ties)

    if no eligible j: return False  # infeasible

    pivot(leaving, j, leaving_bound)
```

Since we don't track reduced costs during feasibility restoration (no
objective), use a simpler variant: pick the first eligible non-basic variable
(by Bland's index ordering) whose pivot would move the leaving variable toward
feasibility.  The key fix over the current code: correctly handle non-basic
variables at upper bounds (they can *decrease* to help).

Tests: add cases where non-basic vars are at upper bounds. Construct a system
that requires an upper-bound departure during dual simplex.

### A4. Implement `q_ne` properly (#1) — 30 min

Replace the stub with working disequality storage.  Two cases:

**Var != ground value:**
```python
tableau.diseqs.append(('val', var_id, Fraction(value)))
```

**Var != Var:**
```python
tableau.diseqs.append(('var', var_id_l, var_id_r))
```

Update `_check_diseqs` to handle both forms.  Update `check_implied_bindings`
to call `_check_diseqs` after each binding.

Tests: `q_lt(X, 5)` where X is later fixed to 5 must fail.  `q_ne(X, Y)` where
both later become equal must fail.

### A5. Raise `TypeError` for float in Q hook (#9) — 10 min

Add explicit branch in `_q_hook`:

```python
if isinstance(bound_to, float):
    raise TypeError(
        f"Cannot unify CLP(Q) variable with float {bound_to!r}. "
        "Use Fraction or declare the variable with in_real instead."
    )
```

Test: `in_q(X, 0, 10), X == 1.5` should raise `TypeError`, not silently fail.

---

## Phase B: functional completeness (needed for SICStus parity)

**Estimated total: 3-4 hours**

These issues don't produce wrong answers but cause user-facing behaviour to
differ from expectations.

### B1. `optimize` binds variables (#5) — 30 min

After `tableau.optimize` returns a value, iterate `_var_map` and bind each
variable to its optimal assignment:

```python
for vid, var in tableau._var_map.items():
    var = deref(var)
    if is_var(var):
        val = tableau.assign.get(vid)
        if val is not None:
            unify(var, val, trail)
```

Care needed: `unify` triggers `_q_hook` which calls `fix_variable`.  Since
the Tableau already holds the optimal solution, `fix_variable` should be a
no-op (the value matches).  But verify there's no infinite recursion.

Test: after `maximize(30*X + 50*Y, OBJ)`, verify `X == 7` and `Y == 2`.

### B2. Implement `sup`/`inf` (#11, partial) — 1 hr

```python
def sup(expr, trail):
    """Compute supremum (upper bound) of expr without committing."""
    tableau = _get_tableau(trail)
    tab_copy = tableau.copy()  # don't mutate working tableau
    return tab_copy.optimize(coeffs, 'max')

def inf(expr, trail):
    """Compute infimum (lower bound) of expr without committing."""
    tableau = _get_tableau(trail)
    tab_copy = tableau.copy()
    return tab_copy.optimize(coeffs, 'min')
```

Register as builtins `sup/2` and `inf/2`.

Test: `sup(X + Y)` subject to `X <= 4, Y <= 6, X + Y <= 8` → 8.

### B3. Implement `entailed` (#11, partial) — 1 hr

`entailed(Constraint)` succeeds if the constraint is implied by the current
store.  Implementation: check whether the negation is infeasible.

For `entailed(X =< 5)`:
- Negate: `X > 5`, i.e., `X >= 5 + epsilon`.  In rationals there's no
  epsilon, so this is `NOT(X =< 5)` = `X > 5`.  Since we can't represent open
  bounds, check `X >= 5` infeasibility after setting `X_lo = 5 + 1`... this
  is tricky in exact arithmetic.

Simpler approach for `entailed(X =< C)`: check if `sup(X) <= C`.  For
`entailed(X =:= C)`: check if `inf(X) == sup(X) == C`.

Test: `{X =< 4}, entailed(X =< 5)` → true.  `{X =< 4}, entailed(X =< 3)` → false.

### B4. Reduce snapshot overhead (#4) — 30 min

Add a `_last_snapshot_mark` field to the module-level state.  In
`_snapshot_tableau`, check if we've already snapshotted at this trail length:

```python
_last_snapshot: dict[int, int] = {}  # trail_id → trail length at last snapshot

def _snapshot_tableau(trail):
    tid = id(trail)
    current_len = len(trail)
    if _last_snapshot.get(tid) == current_len:
        return  # already snapshotted at this point
    _last_snapshot[tid] = current_len
    old = _tableaux[tid].copy()
    trail.record(lambda: (_tableaux.__setitem__(tid, old),
                          _last_snapshot.__setitem__(tid, 0)))
```

Test: verify a multi-constraint step (e.g., `q_eq` that triggers
`check_implied_bindings` which triggers `_q_hook`) creates only one snapshot.

---

## Phase C: cleanup and hardening

**Estimated total: 1-2 hours**

Non-urgent improvements. Do these when convenient, not blocking anything.

### C1. Fix `Fraction` import in `_eval_ground` (#8) — 5 min

Move `from fractions import Fraction` to the top of `clpfd.py` (it's already
imported in other functions via `_is_rational_arg`).  Remove the per-call
import.

### C2. Fix `_tableaux` memory leak (#2) — 20 min

Check if `Trail` supports `weakref`.  If yes, use
`weakref.finalize(trail, cleanup)`.  If not, add a `__del__` or explicit
`close()` method.  Alternatively, use a `WeakValueDictionary` keyed by a
weak-referenceable wrapper.

### C3. Optimize `_is_rational_arg` tree walk (#7) — 20 min

Instead of walking the tree in `_is_rational_arg`, walk it lazily: check
top-level types first, then let the CLP(Z) linearization path detect Q-vars
and re-dispatch.  This avoids the tree walk for pure CLP(Z) programs.

Alternatively, cache the result on the expression node (if nodes are mutable)
or use a small LRU cache keyed by `id(expr)`.

### C4. Audit C extension dispatch ordering (#14) — 30 min

Read through `_clpfd_propagate.c` and verify that `_any_rational` is called
before the linearization fast path in every C `fd_*` function.  If not, move
the `_any_rational` check earlier.

Write a test that exercises the specific code path: an expression tree with
Q-declared variables going through the C `fd_eq`.  The existing
`TestClausalIntegration` tests already cover this, so this is mainly an audit.

---

## Phase D: feature parity with SICStus (longer-term)

**Estimated total: 7-10 hours**

These are substantial features that extend CLP(Q) beyond the current scope.
Not blocking for initial release.

### D1. Constraint projection via Fourier-Motzkin (#6) — 4-6 hr

Implement `dump_q(Vars, NewVars, Constraints)` that projects the constraint
store onto `Vars`, eliminating all internal/slack variables.

Algorithm: for each variable to eliminate, replace it in all inequalities
using Fourier-Motzkin elimination (combine each upper-bound inequality with
each lower-bound inequality for that variable).  The result may have redundant
constraints; remove them by LP feasibility checks.

This is the feature that SWI-Prolog's CLP(Q) gets wrong (broken projection).
Getting it right is important for answer presentation.

### D2. Branch-and-bound mixed-integer optimization (#12) — 3-4 hr

Implement `bb_inf(IntVars, Expr, Inf)`:

```
1. Solve LP relaxation: inf = optimize(Expr, 'min')
2. If all IntVars are integer-valued: done
3. Pick most fractional IntVar X (closest to 0.5)
4. Branch:
   a. Add X <= floor(X_val), recurse
   b. Add X >= ceil(X_val), recurse
5. Return best feasible integer solution
```

Uses Tableau.copy() for each branch node.  Needs careful trail integration
(each branch is a choice point).

---

## Summary

| Phase | Issues | Effort | When |
|---|---|---|---|
| **A** | #10, #13, #3, #1, #9 | 2-3 hr | Before any production use |
| **B** | #5, #11, #4 | 3-4 hr | Before advertising SICStus parity |
| **C** | #8, #2, #7, #14 | 1-2 hr | When convenient |
| **D** | #6, #12 | 7-10 hr | Longer-term |

---

## IMPORTANT: Python fallback requirement

All C extensions MUST keep the Python reference implementation as a fallback.
Pattern:

```python
# Python reference implementation
def _foo_py(...):
    ...

# C-accelerated version with fallback
_foo = _foo_py
try:
    from clausal.logic._c_module import _foo
except ImportError:
    pass
```

Do NOT delete the Python originals when adding C versions. The codebase must
work correctly (just slower) if C extensions fail to build.
