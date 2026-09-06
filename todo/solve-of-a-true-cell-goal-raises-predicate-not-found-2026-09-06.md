# `solve(("true",), mod)` raises PredicateNotFoundError while `call("true")` succeeds

**Filed:** 2026-09-06 at the P3-3 final fix wave re-review (finding N3).

The fix wave (I-3) taught `_resolve_named_goal` (clausal/logic/builtins/higher_order.py)
that `true`/`!` succeed once and `fail`/`false` fail, so `call("true")` and `call(("!",))`
no longer fail silently. The other door — `solve("true", mod)`, `solve(("true",), mod)`
— still raises `PredicateNotFoundError: Predicate true/0 not found`, because `_term_to_goal`
(clausal/logic/solve.py) lowers a cell to a predicate lookup and the control constructs
have no dispatch entry (the compiler lowers them structurally). Same at BASE for the cell
form; loud, not silent, so not the I-3 failure mode — but the two doors now disagree on a
construct that is definitionally true.

**To close.** Give `_term_to_goal` the same four-construct table `_resolve_named_goal`
has (or share one helper), pin `solve(("true",), m)` → 1 solution, `solve(("fail",), m)`
→ 0, and keep `solve(("unknown_pred",), m)` raising. Consider the same for the qualified
form `(":", mod, ("true",))`.
