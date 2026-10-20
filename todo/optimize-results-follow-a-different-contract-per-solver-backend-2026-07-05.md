# Optimisation predicates answer under a different contract on each solver backend (A08-D005, A08-F018)

**Status: open, needs a ruling.** Design decision A08-D005 of the
2026-07-05 audit, split out of
todo/done/investigate-A08-parked-design-decisions.md on 2026-10-20. Full
statement: docs/superpowers/audits/2026-07-05-fable-partition/08-clpqr-z3/design-questions.md
(A08-D005); finding A08-F018 in the same folder's findings.md.

## What

The predicates named after `clpq`'s `maximize`/`minimize` do not keep its
contract (bind every variable to the optimal point; succeed only on a
proven optimum, fail on a supremum that is not attained):

- `or_minimize`/`or_maximize` (`clausal/logic/clportools.py:980-1013`)
  install the objective on the shared `CpModel` and never remove it, and
  accept `FEASIBLE` (a time-limited, possibly suboptimal answer) as the
  optimum.
- `maximize_z3` (`clausal/logic/clpz3.py`, `opt.upper(handle)` near :1028)
  binds only the objective value, never the variables, and `opt.upper()`
  reports a supremum even when a strict constraint keeps it from being
  attained.

Checked against the code 2026-10-20: unchanged. No test pins it (the
finding came from reading the code); the OR-Tools half needs ortools
installed to probe.

## Options (from the audit)

(a) one contract for the mirror-named predicates: bind the variables,
`OPTIMAL` only, fail otherwise (recommended); (b) a documented contract per
backend; (c) an options argument (attained or supremum, bind or not).
