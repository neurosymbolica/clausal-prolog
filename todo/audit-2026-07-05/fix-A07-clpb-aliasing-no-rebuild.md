# fix-A07: CLP(B) var-var aliasing conjoins stale BDDs instead of rebuilding — missed failures/propagation

**Finding:** A07-F002.
**Severity:** correctness — `sat(X^Y), X is Y` succeeds although the store is
unsatisfiable (a floundering pseudo-solution escapes; labeling finds 0
solutions); `sat(X|Y), X is Y` fails to force X=1.

`_bool_hook` var-var arm (`clausal/logic/clpb.py:730-752`) conjoins
`state.bdd & other_state.bdd`, but after aliasing the two variables are ONE
logical variable occupying TWO distinct BDD levels — the conjunction cannot
express x_id == y_id. The design intent (module docstring "formula storage
for aliasing rebuild"; `BoolState.sat_expr`) was to re-run `_expr_to_bdd` on
the stored formula post-aliasing so `deref` merges the levels — that rebuild
was never implemented. Additional trap: `sat()` (clpb.py:500) overwrites
`sat_expr` with only the *latest* posted formula for the merged network, so a
correct rebuild must store the conjunction of all posted formulas (or a list).

**Fix sketch:**
1. In `sat()`, accumulate the network's formula set on the state (e.g.
   `sat_expr = (old_exprs..., expr)`).
2. In `_bool_hook`'s `is_var(bound_to)` arm, rebuild via
   `_expr_to_bdd(conjunction_of_formulas)` (deref makes the alias collapse to
   one level), fail on BDD_FALSE, re-store on all network vars, then
   `_propagate_forced`.
3. Alternative without formula storage: BDD-level exists/compose — replace
   level y_id by x_id via `apply('and', restrict(b, y, 0)|..., ...)`
   (compose is more code; formula rebuild matches the documented design).

**Test:** `test_A07_F002_alias_after_xor_must_fail`,
`test_A07_F002_alias_or_propagates_forced` (xfail strict=False).
