# A non-numeric leaf *inside* an expr tree still posts silently

**Filed** 2026-08-01, the deliberately-unfixed residue of
todo/nonnumeric-operand-vs-var-inside-expr-tree-unguarded.md (fixed for the
operand-vs-tree case). **Status:** reproduced, not fixed.

## The behaviour

The guards now catch a ground non-numeric on the *other side* of a
var-containing tree (`X + 1 == "banana"` raises). But garbage as a *leaf of
the tree itself* still slips through:

```python
fd_eq(Add(left=X, right="a"), 5, trail)   # True — posts
```

`_linearise` fails on the string leaf, execution falls to
`EqConstraint(Add(X, "a"), 5)`, and the `_expr_domain` catch-all treats the
string as an unconstrained integer (the A06-F014 note) — silently wrong
answers. Same for `!=` and the orderings.

## Why it was not fixed alongside the operand case

Rejecting every ground non-`numbers.Real` leaf during the guard's tree walk
was considered and deliberately not done: it is not established that all
non-Real leaves in constraint-position trees are illegal (e.g. Quantity
leaves in units arithmetic — `X == Amount * 2` with a ground Quantity — have
no test coverage either way, and `_eval_ground`/Quantity `__mul__` do handle
them outside constraint position). Blanket leaf rejection could outlaw
currently-working tree shapes. The safer fix shape is option 2 from the
parent todo: type-check `_expr_domain`'s catch-all (and the equivalent C-side
path) so an unknown leaf raises instead of becoming an unconstrained integer
— that is enforcement at the point where the "unconstrained integer"
assumption is actually made. Decide leaf legality (esp. Quantity/Decimal
leaves) before implementing; A06-F014's sum_/scalar_product precedent
(`_is_fd_sum_element`) rejects non-integer elements up front.

## Repro

Unit-level, as above — verified against clone main 2026-08-01 (with the
operand-vs-tree guards in place).

## Fixed (2026-08-31)

Option 2 from the parent todo, as sanctioned above: enforcement at the two
points where the wrong assumption was actually made, not blanket leaf
rejection during the guard's tree walk.

- `_expr_domain` (clausal/logic/clpfd.py): the catch-all now only keeps its
  eval-if-ground-else-default behaviour for *expression nodes* (any
  `pythonic_ast.nodes.Node` — Div/FloorDiv/Mod/Pow etc., preserving the
  A06-F006 Fraction/float-result rule and the ground-Pow path exactly).  An
  unrecognized LEAF — not an int, not a Var, not a node — raises the
  catchable `LogicException(type_error("integer", Leaf, "clpfd expression"))`
  instead of becoming an unconstrained integer.  The C side delegates all
  tree/leaf domains to this function (`expr_domain_with_trail` fast-paths
  only ints and Vars), so both builds are covered by the one guard.
- `_eval_ground` (same file): the `!=` half of the defect.  Its final
  `return None` meant "still has unbound vars" to every caller, so
  NeConstraint kept `X + "a" != 5` pending forever (it could never fail) and
  `_resolve` left garbage trees unevaluated.  A leaf that is not a number,
  Var, or node now raises the same error (bool keeps its old None —
  deliberately not an FD number, not newly outlawed).  The C `ne_propagate`
  and comparator wrappers call `fn_eval_ground`/`fn_resolve`, so covered.

Leaf legality decided as: int / Var / expression node legal; Fraction leaves
in trees keep dispatching to CLP(Q) *before* any FD walker runs
(`_is_rational_arg` walks trees), so they never hit the guard; bare
Decimal/Quantity/str/date/None/compound leaves raise, and a float leaf
raises when it sits beside an FD *Var* (via `_expr_domain`) — a FULLY-GROUND
tree with a float leaf instead folds numerically in `_eval_ground` and
dispatches to CLP(R), the pre-existing FD/R boundary (`2 + 0.5 == 2.5` is
True and stays so; roborev job 14 corrected this note's original blanket
"float raises" claim, and the ground-float fold is pinned in the same test
class) — verified that
`X == Quantity(2,m) * 2` previously posted, left X unconstrained, and then
accepted `unify(X, 42)` (silently wrong), so rejecting Quantity leaves fixes
a wrong verdict rather than outlawing a working shape.  The units+CLP(FD)
pattern (tests/fixtures/units_clpfd.clausal) keeps Quantities out of
constraint position via `eval_`/`is`, consistent with this.

Tests: tests/audit_2026_07_05/test_12_seams.py
`TestNonNumericLeafInsideExprTree` — ==/!=/</=</> repros, None/Quantity/
float/ground-tree/ground-Quantity-tree leaves, reification route,
`_expr_domain` directly, compiled repro through solve, catch/3 catchability
with full ground-term shape assertion, and 8 controls (int leaves, nested
arith, non-ground FloorDiv node, ground Pow, Fraction→CLP(Q), var-tree `!=`
still enforcing).  Collateral: test_date_time_ordering.py
`test_var_lt_expr_tree_still_legal` built `Add(y, 1)` positionally, which is
`Add(position=y, left=1, right=None)` (Node's first dataclass field is
`position`) — a malformed node that only "posted" through the old fall-
through; fixed to keyword construction, intent preserved.
