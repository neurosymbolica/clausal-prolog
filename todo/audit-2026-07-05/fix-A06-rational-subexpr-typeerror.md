# fix(A06-F006): rational subexpression posts as CLP(Z), later binding raises TypeError

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/06-clpfd/findings.md A06-F006
**Tests:** tests/audit_2026_07_05/test_06_clpfd.py::TestRationalSubexpression::test_rational_subexpr_no_crash (xfail — flip to pass)

## Bug

`X == Y + 1/2` with Y unbound: `_is_rational_arg` (clpfd.py:1460-1483)
walks the Add tree but only detects LITERAL Fractions/Q-vars — `Div(1, 2)`
is int/int so no rational dispatch. The constraint posts as CLP(Z). When Y
is later bound, `_expr_domain` evaluates `Div(1,2)` via `_eval_ground` →
Fraction(1,2) becomes a DOMAIN BOUND, and the C domain ops
(`unpack_interval`, _clpfd_domain_ops.h:28-63; `has_bignum_bound` treats
non-int as "float inf — fits") blow up:

    fd_eq(X, Add(Y, Div(1,2)), t)  # True (posted as FD)
    unify(Y, 1, t)                 # TypeError: 'Fraction' object cannot be
                                   # interpreted as an integer  (escapes unify!)

Seam note: exceptions escaping through unify break the bool-returning
contract callers assume (A12).

## Fix direction

Two layers:
1. Dispatch: make `_is_rational_arg` treat `Div` nodes as rational when both
   subtrees are integral-or-var (Div is TRUE division in Clausal → CLP(Q)
   territory), so `X == Y + 1/2` goes to q_eq up front.
2. Hardening: `_expr_domain` must never emit non-int, non-inf bounds — if
   `_eval_ground` returns a non-integer, return the full domain (unknown) or
   fail the propagator cleanly; and `unpack_interval` should raise a clear
   TypeError listing the offending bound rather than the raw conversion error.

## Acceptance

- xfail passes with CLP(Q) semantics (X = 3/2) — or, if the design call is
  "fail cleanly", update the test expectation with the decision recorded.
- `test_rational_literal_dispatches_to_clpq` stays green.
