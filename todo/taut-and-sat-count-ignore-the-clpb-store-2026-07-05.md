# taut/2 and sat_count/2 ignore the posted CLP(B) store (A07-D001, A07-F003, A07-F004)

**Status: open, needs a ruling.** Design decision A07-D001 of the
2026-07-05 audit, split out of
todo/done/investigate-A07-parked-design-decisions.md on 2026-10-20. Full
statement: docs/superpowers/audits/2026-07-05-fable-partition/07-clpb-sat/design-questions.md.

## Repro

The module docstring of `clausal/logic/clpb.py` claims Triska's design, in
which `taut(Expr, T)` is entailment by the posted store and `sat_count`
counts the store's admissible assignments. Clausal evaluates the formula
alone:

- `sat(X =< Y)` (BoolImpl), then `taut(~X | Y, T)` fails; Triska: `T = 1`.
- `sat(X =:= Y)` (BoolEq), then `sat_count(X | Y, N)` gives `N = 3`;
  Triska: `N = 1`.

Pinned as XFAIL (re-run 2026-10-20, still failing):
tests/audit_2026_07_05/test_07_clpb_sat.py::TestSuspectedBugs::test_A07_F003_taut_entailed_by_store
and ::test_A07_F004_sat_count_respects_store.

## Options (from the audit)

(a) store-aware Triska semantics (recommended; the A07-F001 collection fix
it needed has landed); (b) keep the standalone semantics and say so in the
docstring and docs/clpb.md; (c) both, under different names.
