# CLP(Q): unifying two constrained variables can split one into two

After a var-var unification, later constraints on the surviving variable
can land on a separate tableau variable, so the store accepts what it
should reject:

    {2*Y1 =< -1}, Y1 = Y0, {-Y0 =< 0}       % succeeds; no solution exists

When the variable bound to has no Q attribute, `_q_hook` copies the old
`QVar` across, carrying the other variable's `tab_id`.  But `_linearize`
keys a variable by its own `expr._id`, not by the attribute's `tab_id`.  So
the two names stop referring to the same tableau column.  The hook's
var-var branch and `_linearize` need to agree on one id, for example
by always resolving through the attribute.

Found by a review fuzz (2026-10-11) that mixed var-var unifications into
`<` stores: every infeasible store it saw accepted after a binding came
from this bug.  It reproduces on 9bb5a6d3 too.

Cost notes from the same review, for the strict-bound entailment check
(todo/clpq-strict-bounds-closed-by-inequalities-2026-10-11.md):
- Dense strict sets cost the most.  With all-pairs `X_i < X_j` over
  `in_q` bounds, binding the variables one at a time takes 3.5 s for 20
  variables (2,299 LPs) and 114 s for 40.
- Binding a basic or parametric variable runs the check twice: once
  inside `add_equality` and again in `fix_variable`.

**Done 2026-10-11.** `_q_hook` now gives the unconstrained variable a
column of its own, with the same bounds, linked by an equality, so every
tableau id is again a variable's own id.  Test:
tests/test_clpq_undo_on_backtracking.py
(test_unifying_with_an_unconstrained_variable_keeps_one_column).  On a
z3 undo fuzz with var-var unifications, every wrong accept left is now
the strict-bounds gap (todo/clpq-strict-bounds-closed-by-inequalities).
On 9bb5a6d3, 17 of 35 had no other explanation.  The cost notes above
still stand.
