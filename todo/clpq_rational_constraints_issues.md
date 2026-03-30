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
