# fix(A12-F002): `X == <non-numeric ground term>` succeeds vacuously with an inverted-semantics FD var

**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/12-seams/findings.md` A12-F002
**Tests:** `tests/audit_2026_07_05/test_12_seams.py::TestF002EqNonNumericOperand` (2 xfail — flip to pass; 1 pinned-wrongness guard to update)

## Bug

`badeq(X) <- (X == myatom)` (a `-private` atom; same with a str literal):

- succeeds once, leaving X an FD var with domain `((-inf, inf),)`;
- afterwards `unify(X, 42)` SUCCEEDS while `unify(X, myatom)` FAILS —
  the goal that claimed "X equals myatom" produced a var that equals
  anything *except* atoms/strs. Fully inverted semantics.

`==` is *arithmetic* equality by the standing contract; the CLP(Z) entry
accepts the non-numeric ground operand without a type check and posts an
unconstrained eq. The cheat-sheet already warns users ("binding an atom
with `==` yields a broken FD var") — i.e. this is known-unintended and the
corpus repeatedly trips on it.

## Fix direction

Type-check ground operands at the `==`/CLP(Z) constraint entry (the same
place A06-F015's `arith_plus` fix goes): a ground non-numeric operand
raises a catchable type error (per the A09-D002 error-protocol direction);
unbound vars keep posting constraints. Silent failure is NOT acceptable —
in a cut-free language silent no-ops are indistinguishable from "no
solution" (A06-D002 principle).

Extends A06-D002 (op-string vocabulary) and A06-F015 (plus type check);
same acceptance style.

## Acceptance

- `X == myatom` / `X == "s"` raise a catchable type error (or fail, per
  design call) — never succeed.
- Numeric paths unaffected: `X == 3 + 4` still posts and solves.
- The pinned-wrongness guard `test_eq_atom_current_behaviour_is_inverted`
  is deleted/updated with the fix.
