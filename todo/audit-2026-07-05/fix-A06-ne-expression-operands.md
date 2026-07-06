# fix(A06-F001): != never evaluates expression operands — unsound accept

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/06-clpfd/findings.md A06-F001
**Tests:** tests/audit_2026_07_05/test_06_clpfd.py::TestNeExpressionBlindness (3 xfail — flip to pass)

## Bug

`NeConstraint.propagate` (clpfd.py:728-759), `_ne_propagate_bignum`
(clpfd.py:464-494) and C `ne_propagate` (_clpfd_propagate.c:994-1227) only
handle int/Var operand shapes. An arithmetic-expression operand
(Add/Sub/Mult/Negate — exactly what the compiler passes for `X + 1 != Y`,
eval_arith=False) falls into the "both ground" branch once its vars are
bound, where `lhs != rhs` compares the *expression node* to the int
**structurally** — always "different", so the constraint is permanently
satisfied:

    Bad(X, Y) <- (X + 1 != Y, X is 1, Y is 2)   # succeeds; 2 != 2 is false
    in_domain([X,Y],1,3), X+1 != Y, label(...)   # labels (1,2) and (2,3)

Only ground-at-post expressions are safe (`_resolve` pre-evaluates).

## Fix direction

In all three propagators: before the ground-ground compare, evaluate
expression operands with `_eval_ground` (None → still unbound → keep
pending). Better: give NeConstraint the same `_expr_domain`-based treatment
as Lt/Le — when one side's domain is a singleton, remove that value from
the other side's domain (works for expressions too and adds pruning).
Alternative structural fix: normalise `expr != rhs` at post time into
`T == expr, T != rhs` (linearise like fd_eq); keeps the propagators simple.

## Acceptance

- The three xfail tests pass; `test_ne_ground_expr_at_post_ok` stays green.
- Differential test extended to include `ne` with expressions stays clean.
- No regression in nqueens perf path (fd_ne is the hottest FD call).
