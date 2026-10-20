# Z3 and OR-Tools adapters register no attribute hooks, so a binding never reaches the solver (A08-F013, A08-D002)

**Status: open.** Triaged 2026-10-20, moved from the 2026-07-05 audit
folder (was `investigate-A08-solver-store-sync-hooks.md`). Both
`TestZ3StoreSync` tests in tests/audit_2026_07_05/test_08_clpqr_z3.py still
XFAIL (`test_binding_out_of_domain_fails`, `test_label_respects_bindings`).
The OR-Tools half could not be re-run here (ortools not installed); no hook
is registered for `OR_KEY`/`LP_KEY` in `clausal/logic/clportools.py` /
`clportools_lp.py`. Design decision A08-D002 (register hooks?) is still
unruled. The A04-D001 hook-protocol limit mentioned below is gone: since
2026-10-09 a hook may queue a goal that runs with every answer
(`clausal/logic/pending.py`).

The original audit text follows.

**Findings:** A08-F013 (high); related A08-F016; design question A08-D002 (parked)
**Tests:** `tests/audit_2026_07_05/test_08_clpqr_z3.py::TestZ3StoreSync` (2 xfails)

## Problem
`clpz3.py`, `clportools.py`, `clportools_lp.py` store `put_attr` metadata
under `Z3_KEY`/`OR_KEY`/`LP_KEY` but never `register_attr_hook`. Unifying a
registered var is therefore invisible to the backend:
- `in_z3(X, 1, 10); X is 99` succeeds and `z3_check` stays sat (CLP(FD)'s
  `in_domain` analog fails);
- after `z3_eq(A, B); A is 3`, `label_z3([B])` enumerates 1..10 — answers
  inconsistent with the substitution;
- same class for CP-SAT/LP (or_minimize binds stale vars, A08-F016).

## Direction (pending A08-D002)
Register hooks per key that, on unification with a numeric value, push a
scope and post `z3v == value` (Z3) / a guarded `cv == value` (CP-SAT) /
tag a `[v,v]` bound row (LP), failing on out-of-sort values. Var-var
unification posts equality of the two backend constants. Mind the A04-D001
hook-protocol limitation (boolean/semidet) and the docstring claim that these
predicates "follow the same Clausal syntax and semantics as the native CLP
predicates".

## Acceptance
`TestZ3StoreSync` xfails flip; label/backtrack guards stay green.
