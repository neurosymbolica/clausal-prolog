# Posting a cyclic expression to CLP(Z) or CLP(B) loops forever or overflows the stack

**Status: FIXED 2026-11-05 (commit 10737fe8)** for CLP(Z). Posting a cyclic
expression is clpz's `domain_error(clpz_expression, Side)`, or
`domain_error(clpz_reifiable_expression, Operand)` for an operand of a
reified connective, as in Scryer, on `.pl`, `.clausal` and the seam. It is
detected on the way by the walks that already visit every node of a post,
and exactly where none does. Pinned in `tests/iso/test_clpz_cyclic_scryer.py`.

**Status: RESOLVED 2026-11-04 (operator ruling)** for CLP(B): "follow
Scryer, document it (comments are enough)". Scryer's clpb gives no answer
for a cyclic `sat/1`, `taut/2` or `labeling/1` argument, so no error term is
invented and the behaviour is unchanged (`resource_error(stack)`). Comments
at `clpb.sat`, `clpb.taut` and `clpb.bool_labeling` say so (commit 10737fe8).

Found 2026-11-04 while making the arithmetic evaluator refuse a cyclic term
(operator ruling 2026-11-04: "type_error if Scryer gives one";
`exact_arith.evaluate`, `tests/iso/test_cyclic_eval_scryer.py`). The CLP
posts walk the expression with their own walkers, not that evaluator, so the
fix there does not reach them. Severity: a HANG for the seam's arithmetic
comparisons.

## What / Repro

No occurs check, so `X = X+1` (seam `X is X + 1`) builds a cyclic term.

| goal | Clausal | Scryer |
|---|---|---|
| seam `X is X + 1, X == 1` | never returns (`clpfd._fd_int_term`'s iterative walk goes round the cycle) | (clpz) `domain_error(clpz_expression, ... +1)` |
| seam `X is X + 1, X < 1` | never returns (same) | as above |
| seam `X is X + 1, _ == X` | never returns (same) | as above |
| `.pl` `X = X+1, X #= 1` | `resource_error(stack)`, context unbound | `error(domain_error(clpz_expression,... +1),unknown(... +1)-1)` |
| `.pl` `X = 1+X, X #< 3` | `resource_error(stack)` | `domain_error(clpz_expression,1+ ... +1)` |
| `.pl` `X = f(X), X #= 1` | `domain_error(clpz_expression,f(...))-(#=)/2` | `domain_error(clpz_expression,f(...))` |
| seam `X is X & 1, sat(X)` (also `~X`, `X \| Y`) | `resource_error(stack)` | `X = X*1, sat(X)`: no answer in 30 s |
| `.pl` `X = X+1, {X = 1}` (CLP(Q)) | `type_error(evaluable,(+)/2)-(==)/2` | no answer in 30 s |

CLP(Q) already answers with a type error; CLP(Z) and CLP(B) do not.

## Options

- CLP(Z): refuse a cyclic expression at the post's entry
  (`clpfd._lifting_nonlinear_cells.wrapped`, before `_fd_int_term`) with
  clpz's `domain_error(clpz_expression, Expr)`, as Scryer does;
  `exact_arith._reentered_term` already finds the cycle. Every walker after
  it (`_lift_cells`, `_linearise`, `_eval_ground`) then sees acyclic terms
  only.
- CLP(B): the same check at `sat/1`, `taut/2` and `labeling/1`'s entry;
  Scryer has no answer to follow, so the error term needs a ruling
  (`type_error(boolean, ...)`? clpb's `domain_error(clpb_expr, ...)`?).
